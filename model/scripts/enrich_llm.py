"""LLM Chunk Semantic Enrichment — 三层语义分类器。

为规则无法置信的 chunk 补充语义标签, 修复规则错标(如高压氧 chunk 标 imaging
但内容属于治疗):

  Layer 1  规则高置信: 命中多个不同关键词(subtopic/decision_node) → confidence=0.95, 跳过 LLM
  Layer 2  LLM 分类:   无命中或仅单个关键词弱命中 → qwen-plus 输出
           {domain, subtopic, clinical_intent, medical_entity, question_type,
            condition, confidence}
  Layer 3  人工抽检:   最终 confidence<0.6 的样本写入 report 供人工复核

新增 metadata 字段: domain / clinical_intent / medical_entity / question_type
/ condition / confidence。

使用链路:
  存量库: enrich_llm(补 LLM 标签) → enrich_metadata(按 domain 重分桶)
  重建:   build_multi_collection_vectorstores 之后需重跑 enrich_llm 再
          enrich_metadata, 否则新建 chunks 无 LLM 标签(仅规则标签)。

用法(容器内):
    python -m scripts.enrich_llm [--persist-dir PATH] [--dry-run] [--max-chunks N]
"""
import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.rag.data_loader import (  # noqa: E402
    SUBTOPIC_RULES,
    DECISION_NODE_RULES,
)
from app.rag.retrievers import (  # noqa: E402
    CONFIG,
    DashScopeEmbeddings,
    COLLECTION_KEYS,
    COLLECTION_NAMES,
)

logger = logging.getLogger("enrich_llm")

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 规则置信: 命中 ≥2 个不同关键词 → 高置信跳过 LLM
RULE_CONFIDENT_MIN_KEYWORDS = 2
RULE_CONFIDENT_CONFIDENCE = 0.95
# LLM 结果覆盖的字段
LLM_FIELDS = ("domain", "subtopic", "clinical_intent", "medical_entity",
              "question_type", "condition", "confidence")
# 人工抽检阈值
MANUAL_REVIEW_THRESHOLD = 0.6

CLASSIFY_PROMPT = """你是卒中领域指南专家。分析以下医学文本片段，输出结构化分类 JSON。

只输出 JSON（不要额外文字）：
{
  "domain": "etiology | treatment | prevention | anatomy | diagnosis | rehabilitation | general",
  "subtopic": "toast_classification | iv_thrombolysis | mechanical_thrombectomy | bp_management | anticoagulation | antiplatelet | lipid_management | secondary_prevention | lvo_assessment | imaging | stroke_identification | rehabilitation | general",
  "clinical_intent": "classification | treatment | diagnosis | prevention | localization | assessment | general",
  "medical_entity": "核心医学实体(如 TOAST / alteplase / hyperbaric oxygen), 无则 null",
  "question_type": "该片段可能回答的问题类型(如 classification / intervention / prognosis)",
  "condition": "适用疾病或场景(如 ischemic stroke / stroke rehabilitation)",
  "confidence": 0到1的置信度
}

【文本片段】
{text}"""


def _count_rule_keyword_hits(text: str) -> int:
    """统计文本命中的规则关键词总数(跨 subtopic/decision_node 词表)。"""
    lower = text.lower()
    hits = 0
    for _, kws in list(SUBTOPIC_RULES) + list(DECISION_NODE_RULES):
        if any(str(kw).lower() in lower for kw in kws):
            hits += 1
    return hits


def classify_with_llm(llm, text: str) -> dict | None:
    """qwen-plus 分类单个 chunk, 失败返回 None。"""
    try:
        # 用 replace 而非 str.format: prompt 内含 JSON 花括号, format 会误解析
        prompt = CLASSIFY_PROMPT.replace("{text}", text[:1800])
        resp = llm.invoke([
            SystemMessage(content="你是严谨的卒中医学文本分类器, 只输出合法 JSON。"),
            HumanMessage(content=prompt),
        ])
        content = str(getattr(resp, "content", "") or "").strip()
        # 提取 JSON 对象(容错前后杂讯)
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        # 规范化
        for f in ("domain", "subtopic", "clinical_intent", "medical_entity",
                  "question_type", "condition"):
            v = data.get(f)
            data[f] = str(v).strip() if v is not None else ""
        conf = data.get("confidence")
        data["confidence"] = round(float(conf), 2) if isinstance(conf, (int, float)) else 0.5
        return data
    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="LLM Chunk Semantic Enrichment")
    parser.add_argument("--persist-dir", default=CONFIG["persist_dir"])
    parser.add_argument("--dry-run", action="store_true", help="只统计待分类数量")
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="最多 LLM 分类条数(0=不限), 用于小规模试跑")
    parser.add_argument("--workers", type=int, default=4, help="LLM 并发数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s",
                        stream=sys.stdout)
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY 未设置")
        sys.exit(1)

    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    # 收集需要 LLM 分类的 chunk(规则低置信)
    targets = []  # (collection_key, id, text, meta)
    for key in COLLECTION_KEYS:
        coll = Chroma(persist_directory=args.persist_dir, embedding_function=embeddings,
                      collection_name=COLLECTION_NAMES[key])
        data = coll._collection.get(include=["documents", "metadatas"], limit=8000)
        for doc_id, doc, meta in zip(data.get("ids", []), data.get("documents", []),
                                     data.get("metadatas", [])):
            meta = meta or {}
            if str(meta.get("doc_type", "") or "") == "qa_generated_batch":
                continue  # QA 对跳过
            text = str(doc or "").strip()
            # 已有高置信 LLM 标签则跳过(容错解析 confidence 字符串/None)
            try:
                conf = float(meta.get("confidence") or 0)
            except (TypeError, ValueError):
                conf = 0.0
            if conf >= 0.8:
                continue
            if _count_rule_keyword_hits(text) >= RULE_CONFIDENT_MIN_KEYWORDS:
                continue  # Layer 1: 规则高置信
            targets.append((key, doc_id, text, meta))

    logger.info(f"Layer 1 规则过滤后, 待 LLM 分类 chunk: {len(targets)}")
    if args.max_chunks:
        targets = targets[:args.max_chunks]
        logger.info(f"  限制为 {len(targets)} 条(--max-chunks)")
    if args.dry_run:
        logger.info("dry-run 模式, 未调用 LLM")
        return

    llm = ChatOpenAI(model="qwen-plus", api_key=api_key,
                     base_url=DASHSCOPE_BASE, temperature=0.1)
    results = {}  # (key, id) -> llm_result
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(classify_with_llm, llm, text): (key, doc_id, text)
                for key, doc_id, text, _ in targets}
        for fut in as_completed(futs):
            key, doc_id, text = futs[fut]
            result = fut.result()
            done += 1
            if result:
                results[(key, doc_id)] = result
            if done % 20 == 0:
                logger.info(f"  LLM 分类进度: {done}/{len(targets)}")

    logger.info(f"LLM 分类完成: {len(results)}/{len(targets)} 成功")

    # 写回 metadata + 收集低置信样本
    stores = {key: Chroma(persist_directory=args.persist_dir, embedding_function=embeddings,
                          collection_name=COLLECTION_NAMES[key]) for key in COLLECTION_KEYS}
    review_samples = []
    by_collection = {key: {"ids": [], "metas": []} for key in COLLECTION_KEYS}
    for (key, doc_id), res in results.items():
        patch = {f: res.get(f, "") for f in LLM_FIELDS}
        by_collection[key]["ids"].append(doc_id)
        by_collection[key]["metas"].append(patch)
        if float(res.get("confidence", 0)) < MANUAL_REVIEW_THRESHOLD:
            review_samples.append({"collection": key, "id": doc_id,
                                   "text": next(t for k, i, t, _ in targets if (k, i) == (key, doc_id))[:200],
                                   "llm": res})
    for key in COLLECTION_KEYS:
        b = by_collection[key]
        for i in range(0, len(b["ids"]), 200):
            stores[key]._collection.update(ids=b["ids"][i:i + 200],
                                           metadatas=b["metas"][i:i + 200])
        if b["ids"]:
            logger.info(f"  ✅ {COLLECTION_NAMES[key]}: 更新 {len(b['ids'])} 条 LLM 标签")

    # Layer 3: 人工抽检报告
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "llm_review_samples.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(review_samples, f, ensure_ascii=False, indent=2)
    logger.info(f"低置信样本(confidence<{MANUAL_REVIEW_THRESHOLD}): "
                f"{len(review_samples)} 条, 已写入 {report_path} 供人工抽检")


if __name__ == "__main__":
    main()
