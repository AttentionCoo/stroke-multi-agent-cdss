"""存量向量库 metadata 增强脚本。

为 5 个 collection 的既有 chunk 补充 `intervention`(具体药物/操作)字段,
供 Medical Evidence Score 的干预级匹配使用。

关键点:
- 使用 chromadb Collection.update 只更新 metadatas, 不动 embeddings/documents,
  零 API 成本、不改变向量。
- chromadb update 对 metadata 是合并(merge)语义: 只写入提供的键,
  其余字段(source/subtopic/year 等)保持不变, 已实测验证。
- 提取规则与运行时 enrich_metadata 共用 data_loader.INTERVENTION_RULES,
  保证与重建结果一致。
- 幂等 + dry-run。

用法(在 model 目录或容器内):
    python -m scripts.enrich_metadata [--persist-dir PATH] [--dry-run]
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma  # noqa: E402

from app.rag.data_loader import INTERVENTION_RULES  # noqa: E402
from app.rag.retrievers import (  # noqa: E402
    CONFIG,
    DashScopeEmbeddings,
    COLLECTION_KEYS,
    COLLECTION_NAMES,
)

logger = logging.getLogger("enrich_metadata")


def extract_interventions(content: str, source: str = "") -> str:
    """按关键词从内容(兜底文件名)提取 intervention 标签, 逗号分隔前 2 个。"""
    lower_text = (content or "").lower()
    matched = []
    for label, kws in INTERVENTION_RULES:
        if any(str(kw).lower() in lower_text for kw in kws):
            matched.append(label)
    if not matched and source:
        lower_file = str(source).lower()
        for label, kws in INTERVENTION_RULES:
            if any(str(kw).lower() in lower_file for kw in kws):
                matched.append(label)
    return ",".join(list(dict.fromkeys(matched))[:2]) if matched else ""


def main():
    parser = argparse.ArgumentParser(description="为存量向量库补充 intervention 元数据")
    parser.add_argument("--persist-dir", default=CONFIG["persist_dir"],
                        help="Chroma 持久化目录(默认取 CONFIG['persist_dir'])")
    parser.add_argument("--dry-run", action="store_true", help="只统计待更新数量, 不写入")
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
    total_updated = 0
    for key in COLLECTION_KEYS:
        name = COLLECTION_NAMES[key]
        coll = Chroma(persist_directory=persist_dir, embedding_function=embeddings,
                      collection_name=name)
        count = coll._collection.count()
        if count == 0:
            logger.info(f"  ➖ {name}: 空 collection, 跳过")
            continue

        data = coll._collection.get(include=["documents", "metadatas"])
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])

        update_ids, update_metas = [], []
        for doc_id, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            old = str(meta.get("intervention", "") or "")
            new = extract_interventions(doc, meta.get("source", ""))
            if old != new:
                update_ids.append(doc_id)
                update_metas.append({"intervention": new})

        if not update_ids:
            logger.info(f"  ✅ {name}: {count} 条均已有 intervention, 无需更新")
            continue

        logger.info(f"  ✏️  {name}: {len(update_ids)}/{count} 条需要补充 intervention")
        total_updated += len(update_ids)
        if args.dry_run:
            continue

        # 分批 update(只更新 metadatas, 不重新 embedding)
        batch_size = 200
        for i in range(0, len(update_ids), batch_size):
            b_ids = update_ids[i:i + batch_size]
            b_metas = update_metas[i:i + batch_size]
            coll._collection.update(ids=b_ids, metadatas=b_metas)
        logger.info(f"    ✅ {name} 更新完成")

    logger.info(f"合计待更新/已更新: {total_updated} 条" +
                ("(dry-run, 未写入)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
