"""存量向量库 metadata 增强脚本。

对 5 个 collection 的既有 chunk 做 Chunk-level enrichment:
- 用 chunk 文本重算内容级标签(subtopic/decision_node/intervention/
  time_window/evidence_level/phase), 覆盖页面级继承的宽松标签
  (修复"整页含TOAST → 所有chunk都标toast"的误标传播)
- 删除垃圾 chunk: 参考文献页(引用密度高)与过短碎片

关键点:
- 使用 chromadb Collection.update/delete 只动 metadata/ids,
  不重新 embedding, 零 API 成本。
- 规则与运行时 data_loader(split_documents) 一致, 保证与重建结果相同。
- 幂等 + dry-run(先看统计)。

用法(在 model 目录或容器内):
    python -m scripts.enrich_metadata [--persist-dir PATH] [--dry-run]
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from app.rag.data_loader import (  # noqa: E402
    MIN_CHUNK_CHARS,
    _recompute_chunk_metadata,
    is_reference_chunk,
)
from app.rag.retrievers import (  # noqa: E402
    CONFIG,
    DashScopeEmbeddings,
    COLLECTION_KEYS,
    COLLECTION_NAMES,
    route_collection,
)

logger = logging.getLogger("enrich_metadata")

# 内容级字段(Chunk-level enrichment 重算范围)
CONTENT_FIELDS = ("subtopic", "decision_node", "intervention",
                  "time_window", "evidence_level", "phase")


def main():
    parser = argparse.ArgumentParser(description="存量库 Chunk-level enrichment + 重分桶 + 垃圾过滤")
    parser.add_argument("--persist-dir", default=CONFIG["persist_dir"],
                        help="Chroma 持久化目录(默认取 CONFIG['persist_dir'])")
    parser.add_argument("--dry-run", action="store_true", help="只统计, 不写入/不删除/不移动")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    persist_dir = args.persist_dir
    if not os.path.isdir(persist_dir):
        logger.error(f"❌ 持久化目录不存在: {persist_dir}")
        sys.exit(1)

    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    stores = {}
    for key in COLLECTION_KEYS:
        stores[key] = Chroma(persist_directory=persist_dir, embedding_function=embeddings,
                             collection_name=COLLECTION_NAMES[key])

    # 第一遍: 扫描各 collection, 收集 更新/删除/移动 操作
    updates = {key: {"ids": [], "metas": []} for key in COLLECTION_KEYS}
    deletes = {key: [] for key in COLLECTION_KEYS}
    moves = {key: {"ids": [], "docs": [], "metas": [], "embs": []} for key in COLLECTION_KEYS}

    for key in COLLECTION_KEYS:
        coll = stores[key]
        count = coll._collection.count()
        if count == 0:
            continue
        data = coll._collection.get(include=["documents", "metadatas", "embeddings"])
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])
        embs = data.get("embeddings", [])

        for doc_id, doc, meta, emb_vec in zip(ids, docs, metas, embs):
            meta = meta or {}
            text = str(doc or "").strip()

            # QA 对(doc_type=qa_generated_batch)跳过重分桶/重算:
            # 运行时 QA 对 subtopic 来自批次并集, 文本级重算会泛化失真
            if str(meta.get("doc_type", "") or "") == "qa_generated_batch":
                continue

            # 垃圾过滤: 过短碎片 / 参考文献页
            if len(text) < MIN_CHUNK_CHARS or is_reference_chunk(text):
                deletes[key].append(doc_id)
                continue

            # Chunk-level enrichment: 重算内容级标签
            tmp = Document(page_content=text, metadata=dict(meta))
            _recompute_chunk_metadata(tmp)
            new_key = route_collection(tmp.metadata, text)

            if new_key != key:
                # 重分桶: 移到正确 collection(带原 embedding, 零 API 成本)
                moves[new_key]["ids"].append(doc_id)
                moves[new_key]["docs"].append(doc)
                moves[new_key]["metas"].append(dict(tmp.metadata))
                moves[new_key]["embs"].append(emb_vec)
                deletes[key].append(doc_id)
                continue

            patch = {
                k: tmp.metadata[k] for k in CONTENT_FIELDS
                if str(meta.get(k, "") or "") != str(tmp.metadata.get(k, "") or "")
            }
            if patch:
                updates[key]["ids"].append(doc_id)
                updates[key]["metas"].append(patch)

    # 统计
    total_upd = sum(len(v["ids"]) for v in updates.values())
    total_del = sum(len(v) for v in deletes.values())
    total_move = sum(len(v["ids"]) for v in moves.values())
    logger.info("=== 统计 ===")
    for key in COLLECTION_KEYS:
        logger.info(f"  {COLLECTION_NAMES[key]:<24} 更新 {len(updates[key]['ids']):>5} | "
                    f"删除 {len(deletes[key]):>4} | 移入 {len(moves[key]['ids']):>5}")
    logger.info(f"  合计: 更新 {total_upd}, 删除 {total_del}, 移动 {total_move}")
    if args.dry_run:
        logger.info("dry-run 模式, 未执行")
        return

    # 执行: 先移入(目标 collection add 带 embedding), 再更新, 最后删除旧桶
    for key in COLLECTION_KEYS:
        mv = moves[key]
        if mv["ids"]:
            failed_ids = []
            try:
                stores[key]._collection.add(
                    ids=mv["ids"], documents=mv["docs"],
                    metadatas=mv["metas"], embeddings=mv["embs"],
                )
                logger.info(f"  ➡️  {COLLECTION_NAMES[key]}: 移入 {len(mv['ids'])} 条(带原 embedding)")
            except Exception as e:
                # 幂等容错: 重复运行时可能已存在部分 id, 逐个重试失败的
                logger.warning(f"  ⚠️  {COLLECTION_NAMES[key]} 批量移入失败({e}), 逐个重试...")
                for i, (did, dd, dm, de) in enumerate(zip(mv["ids"], mv["docs"],
                                                          mv["metas"], mv["embs"])):
                    try:
                        stores[key]._collection.add(ids=[did], documents=[dd],
                                                    metadatas=[dm], embeddings=[de])
                    except Exception as e2:
                        failed_ids.append(did)
                        logger.error(f"  ❌ 移入失败 id={did}: {e2}")
            if failed_ids:
                # 移入失败的文档回撤源桶删除, 避免文档永久丢失
                logger.warning(f"  🔙 回撤 {len(failed_ids)} 条失败文档的源桶删除")
                for src_key in COLLECTION_KEYS:
                    if src_key == key:
                        continue
                    deletes[src_key] = [d for d in deletes[src_key] if d not in set(failed_ids)]
    for key in COLLECTION_KEYS:
        up = updates[key]
        for i in range(0, len(up["ids"]), 200):
            b_ids = up["ids"][i:i + 200]
            b_metas = up["metas"][i:i + 200]
            try:
                stores[key]._collection.update(ids=b_ids, metadatas=b_metas)
            except Exception as e:
                logger.error(f"  ❌ {COLLECTION_NAMES[key]} 更新失败: {e}")
        dl = deletes[key]
        if dl:
            try:
                stores[key]._collection.delete(ids=dl)
                logger.info(f"  🗑️  {COLLECTION_NAMES[key]}: 删除 {len(dl)} 条(垃圾/已移动)")
            except Exception as e:
                logger.error(f"  ❌ {COLLECTION_NAMES[key]} 删除失败: {e}")

    logger.info("✅ 完成: 重分桶 + 标签重算 + 垃圾过滤")


if __name__ == "__main__":
    main()
