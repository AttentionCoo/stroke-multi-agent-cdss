"""存量向量库 metadata 增强脚本。

为 5 个 collection 的既有 chunk 补充结构化证据元数据:
- intervention  具体药物/操作
- decision_node 临床决策节点(IV thrombolysis 等)
- evidence_level 推荐等级(A/B/C)
- time_window   治疗时间窗(0-4.5h 等)

关键点:
- 使用 chromadb Collection.update 只更新 metadatas, 不动 embeddings/documents,
  零 API 成本、不改变向量。
- chromadb update 对 metadata 是合并(merge)语义: 只写入提供的键,
  其余字段(source/subtopic/year 等)保持不变, 已实测验证。
- 提取规则与运行时 enrich_metadata 共用 data_loader 的词表,
  保证与重建结果一致。
- 只补漏不清空: 已存在的字段(页面级继承)不因 chunk 文本未命中而清空。
- 幂等 + dry-run。

用法(在 model 目录或容器内):
    python -m scripts.enrich_metadata [--persist-dir PATH] [--dry-run]
"""
import argparse
import logging
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma  # noqa: E402

from app.rag.data_loader import (  # noqa: E402
    INTERVENTION_RULES,
    DECISION_NODE_RULES,
    EVIDENCE_LEVEL_RULES,
    TIME_WINDOW_RULES,
)
from app.rag.retrievers import (  # noqa: E402
    CONFIG,
    DashScopeEmbeddings,
    COLLECTION_KEYS,
    COLLECTION_NAMES,
)

logger = logging.getLogger("enrich_metadata")

# 本次要补充的字段
TARGET_FIELDS = ("intervention", "decision_node", "time_window", "evidence_level")


def _match_labels(rules, lower: str) -> List[str]:
    """按关键词命中规则标签(保序去重)。"""
    return [label for label, kws in rules
            if any(str(kw).lower() in lower for kw in kws)]


def extract_new_metadata(content: str, source: str = "") -> Dict:
    """从内容(兜底文件名)提取 4 个结构化字段。"""
    lower_text = (content or "").lower()
    lower_file = str(source or "").lower()

    interventions = _match_labels(INTERVENTION_RULES, lower_text)
    if not interventions:
        interventions = _match_labels(INTERVENTION_RULES, lower_file)
    decision_nodes = _match_labels(DECISION_NODE_RULES, lower_text)
    if not decision_nodes:
        decision_nodes = _match_labels(DECISION_NODE_RULES, lower_file)
    # time_window: 数字边界判断(避免 "13小时" 误中 "3小时")
    from app.rag.data_loader import time_window_hit
    time_windows = [label for label, kws in TIME_WINDOW_RULES
                    if time_window_hit(lower_text, kws)]
    if not time_windows:
        time_windows = [label for label, kws in TIME_WINDOW_RULES
                        if time_window_hit(lower_file, kws)]

    evidence_level = "NA"
    for label, kws in EVIDENCE_LEVEL_RULES:
        if any(str(kw).lower() in lower_text for kw in kws):
            evidence_level = label
            break

    return {
        "intervention": ",".join(list(dict.fromkeys(interventions))[:2]),
        "decision_node": ",".join(list(dict.fromkeys(decision_nodes))[:2]),
        "time_window": ",".join(list(dict.fromkeys(time_windows))[:2]),
        "evidence_level": evidence_level,
    }


def main():
    parser = argparse.ArgumentParser(description="为存量向量库补充结构化证据元数据")
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
            new_meta = extract_new_metadata(doc, meta.get("source", ""))
            # 只补漏: 已存在的字段(页面级继承)不因 chunk 文本未命中关键词而清空
            patch = {}
            for field in TARGET_FIELDS:
                old = str(meta.get(field, "") or "")
                new = new_meta[field]
                if field == "evidence_level":
                    # 内容级提取(无页面继承), 直接覆盖以修正旧规则错标
                    if new != old:
                        patch[field] = new
                elif new and old != new:
                    patch[field] = new
            if patch:
                update_ids.append(doc_id)
                update_metas.append(patch)

        if not update_ids:
            logger.info(f"  ✅ {name}: {count} 条均已有目标字段, 无需更新")
            continue

        logger.info(f"  ✏️  {name}: {len(update_ids)}/{count} 条需要补充元数据")
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
