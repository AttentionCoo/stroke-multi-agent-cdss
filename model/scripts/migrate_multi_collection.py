"""Multi-Collection 迁移脚本。

将旧的单 Chroma collection(`langchain`, 含全部文档)按归属规则分发写入
5 个主题隔离的 collection:

    anatomy_collection / guideline_collection / etiology_collection
    / treatment_collection / prevention_collection

关键点:
- 复用旧库已算好的 embedding(从旧库 get 出来原样写入), 无需重新调用
  DashScope embedding API, 零额外成本。
- 归属规则与运行时构建(build_multi_collection_vectorstores)共用
  route_collection, 原文 chunk 的迁移结果与重建一致; 旧库 QA 对因
  未记录批次 subtopic, 迁移时从内容关键词提取归属, 可能与重建略有差异。
- 幂等: 目标 collection 已有数据则跳过, 可重复运行。
- 默认不删除旧库(langchain), 确认无误后可手动清理。

用法(在 model 目录或容器内):
    python -m scripts.migrate_multi_collection [--persist-dir PATH] [--dry-run]
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma  # noqa: E402

from app.rag.retrievers import (  # noqa: E402
    CONFIG,
    DashScopeEmbeddings,
    COLLECTION_KEYS,
    COLLECTION_NAMES,
    route_collection,
)

logger = logging.getLogger("migrate_multi_collection")
LEGACY_COLLECTION = "langchain"


def main():
    parser = argparse.ArgumentParser(description="迁移单 collection 到 Multi-Collection 架构")
    parser.add_argument("--persist-dir", default=CONFIG["persist_dir"],
                        help="Chroma 持久化目录(默认取 CONFIG['persist_dir'])")
    parser.add_argument("--dry-run", action="store_true", help="只统计各 collection 归属数量, 不写入")
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

    logger.info(f"🔌 读取旧库: {persist_dir} collection={LEGACY_COLLECTION}")
    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    legacy = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
        collection_name=LEGACY_COLLECTION,
    )
    data = legacy._collection.get(include=["documents", "metadatas", "embeddings"])
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])
    embeddings_list = data.get("embeddings", [])

    if not ids:
        logger.warning("⚠️ 旧库为空, 无需迁移")
        return

    logger.info(f"📦 旧库共 {len(ids)} 条, 开始按归属规则分桶...")

    # 分桶
    buckets = {
        name: {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        for name in COLLECTION_NAMES.values()
    }
    stats = {name: 0 for name in COLLECTION_NAMES.values()}
    for i, (doc_id, doc, meta, emb) in enumerate(zip(ids, documents, metadatas, embeddings_list)):
        key = route_collection(meta or {}, doc)
        name = COLLECTION_NAMES[key]
        bucket = buckets[name]
        bucket["ids"].append(doc_id)
        bucket["documents"].append(doc)
        bucket["metadatas"].append(meta or {})
        bucket["embeddings"].append(emb)
        stats[name] += 1

    logger.info("=== 归属统计 ===")
    for name in COLLECTION_NAMES.values():
        logger.info(f"  {name:<24} {stats[name]:>6} 条")
    logger.info(f"  合计 {len(ids)} 条")

    if args.dry_run:
        logger.info("🔍 dry-run 模式, 未写入任何数据")
        return

    # 写入各 collection(幂等)
    for key in COLLECTION_KEYS:
        name = COLLECTION_NAMES[key]
        bucket = buckets[name]
        if not bucket["ids"]:
            logger.info(f"  ➖ {name}: 无数据, 跳过")
            continue

        coll = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name=name,
        )
        existing = coll._collection.count()
        if existing > 0:
            logger.info(f"  ⏭️  {name}: 已有 {existing} 条, 跳过(如需重建请先清空该 collection)")
            continue

        try:
            coll._collection.add(
                ids=bucket["ids"],
                documents=bucket["documents"],
                metadatas=bucket["metadatas"],
                embeddings=bucket["embeddings"],
            )
            logger.info(f"  ✅ {name}: 写入 {len(bucket['ids'])} 条")
        except Exception as e:
            logger.error(f"  ❌ {name} 写入失败: {e}")

    logger.info("✅ 迁移完成。旧库(langchain)保留未删除, 确认无误后可手动清理。")
    logger.info("   清理命令示例(容器内): rm -rf /app/chroma_db_unified/langchain.sqlite3 "
                "或删除旧 collection 后 vacuum")


if __name__ == "__main__":
    main()
