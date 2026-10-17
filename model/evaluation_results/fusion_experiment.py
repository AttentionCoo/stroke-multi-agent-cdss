"""隔离的加权融合实验：缓存真实候选，只调用项目规则回退重排。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ["BM25_TOKENIZER"] = "jieba"
os.environ["ENABLE_QA_GENERATION"] = "false"
EXPERIMENT_ROOT = Path(__file__).resolve().parent
MODEL_ROOT = EXPERIMENT_ROOT.parents[1]
sys.path.insert(0, str(MODEL_ROOT))

from langchain_core.documents import Document

from app.agents.services.query_translator import translate_query
from app.agents.services.retrieval_service import route_collections
from app.evaluation.retrieval_metrics import retrieval_metrics, source_ids
from app.rag.retrievers import (
    COLLECTION_KEYS,
    DashScopeEmbeddings,
    UnifiedSearchEngine,
    _clean_bm25_query,
)
from app.rag.reranker import BGEReranker


METRICS = ("recall_at_3", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10")
LIMITATION = (
    "仅评估真实向量召回、jieba BM25、融合和规则回退重排的来源覆盖。"
    "不调用 gte-rerank 或答案生成/评分，不是 RAGAS 生成指标。"
    "额外题目来自同一资料库的外部扩展题集，按问题文本排除了原30题；"
    "它不是专家盲评或独立临床数据，且可能仍与原题语义近似。"
    "来源命中不保证片段直接回答问题。"
)
FROZEN_QUERIES = json.loads((EXPERIMENT_ROOT / "fusion_queries_old.json").read_text(encoding="utf-8"))


def fingerprint(value) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def serialize(doc: Document) -> dict:
    return {"page_content": doc.page_content, "metadata": copy.deepcopy(doc.metadata)}


def deserialize(data: dict) -> Document:
    return Document(page_content=data["page_content"], metadata=copy.deepcopy(data["metadata"]))


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_datasets(include_secondary: bool, deduplicate_secondary: bool = False) -> list[tuple[str, list, dict]]:
    primary_path = MODEL_ROOT / "evaluation" / "stroke_ragas.json"
    primary = json.loads(primary_path.read_text(encoding="utf-8-sig"))
    datasets = [("primary30", primary, {"path": str(primary_path), "sha256": file_hash(primary_path)})]
    if include_secondary:
        secondary_path = Path("D:/CompetitionProject/rag-project/evaluation/stroke_ragas_100.json")
        external = json.loads(secondary_path.read_text(encoding="utf-8-sig"))
        primary_questions = {case["question"].strip() for case in primary}
        secondary, seen, duplicate_groups = [], set(primary_questions), {}
        required = {"id", "question", "evidence_type", "expected_source", "ground_truth"}
        for case in external:
            if not required.issubset(case):
                raise ValueError("扩展题集字段不兼容")
            question = case["question"].strip()
            if question not in primary_questions and (not deduplicate_secondary or question not in seen):
                secondary.append(case)
                seen.add(question)
            if question not in primary_questions:
                duplicate_groups.setdefault(question, []).append(case["id"])
        datasets.append((f"secondary{len(secondary)}", secondary, {
            "path": str(secondary_path), "sha256": file_hash(secondary_path),
            "original_count": len(external), "removed_count": len(external) - len(secondary),
            "deduplication": "question.strip() 精确匹配，不做语义去重",
            "deduplicated_within_secondary": deduplicate_secondary,
            "duplicate_question_groups": [ids for ids in duplicate_groups.values() if len(ids) > 1],
        }))
    return datasets


def cache_signature(engine) -> tuple[dict, set]:
    corpus = {
        key: [serialize(doc) for doc in engine.retrievers[key].bm25.docs]
        for key in COLLECTION_KEYS
    }
    available = set().union(*(
        source_ids(doc["metadata"].get("source"))
        for docs in corpus.values() for doc in docs
    ))
    signature = {
        "corpus_sha256": fingerprint(corpus),
        "corpus_counts": {key: len(docs) for key, docs in corpus.items()},
        "tokenizer_sha256": file_hash(MODEL_ROOT / "app/rag/bm25_tokenizer.py"),
        "bm25_sha256": file_hash(MODEL_ROOT / "app/rag/bm25.py"),
        "translator_sha256": FROZEN_QUERIES["translator_sha256"],
        "embedding_model": "text-embedding-v2", "retrieval_top_k": 80,
    }
    save_json(EXPERIMENT_ROOT / "fusion_corpus.json", corpus)
    return signature, available


def collect_candidates(engine, embedder, case: dict, signature: dict, replay_only: bool) -> dict:
    # 冻结旧翻译输出，保证并行修改代码时本次实验的查询仍保持一致。
    query_key = hashlib.sha256((case["question"] + "|" + case["evidence_type"]).encode("utf-8")).hexdigest()
    query = FROZEN_QUERIES["queries"][query_key]["query"]
    collections = route_collections(case["evidence_type"]) or COLLECTION_KEYS
    identity = {"signature": signature, "query": query, "collections": collections}
    path = EXPERIMENT_ROOT / "fusion_candidates" / (fingerprint(identity) + ".json")
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["identity"] != identity:
            raise ValueError("候选缓存签名不一致")
        return cached
    if replay_only:
        raise ValueError(f"缺少候选缓存：{case['id']}")
    # 同一问题只获取一次查询向量，各桶按同一向量检索，避免重复 API 调用。
    query_vector = embedder.embed_query(query)
    rankings = {}
    for key in collections:
        vector_docs = engine.collections[key].similarity_search_by_vector(query_vector, k=80)
        bm25_docs = engine.retrievers[key].bm25.invoke(_clean_bm25_query(query), k=80)
        rankings[key] = {
            "vector": [serialize(doc) for doc in vector_docs],
            "bm25": [serialize(doc) for doc in bm25_docs],
        }
    cached = {
        "identity": identity, "case_id": case["id"], "question": case["question"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query_vector": query_vector, "rankings": rankings,
    }
    save_json(path, cached)
    return cached


def weighted_merge(lists: list[tuple[list[dict], float]]) -> list[Document]:
    """与项目相同，以原文去重；桶内两路的 RRF 分数按指定权重累计。"""
    scores, documents = {}, {}
    for ranking, weight in lists:
        for rank, item in enumerate(ranking, start=1):
            text = item["page_content"]
            scores[text] = scores.get(text, 0.0) + weight / (60 + rank)
            documents[text] = item
    result = []
    for text in sorted(scores, key=scores.get, reverse=True):
        doc = deserialize(documents[text])
        doc.metadata["rrf_score"] = scores[text]
        result.append(doc)
    return result


def rank_configuration(cached: dict, case: dict, vector_weight: int, budget: int,
                       mode: str, rerank_query: str, reranker) -> list:
    bucket_rankings = []
    for rankings in cached["rankings"].values():
        recall_limit = 80 if mode == "fixed80" else budget
        fused = weighted_merge([
            (rankings["vector"][:recall_limit], vector_weight),
            (rankings["bm25"][:recall_limit], 1.0),
        ])[:budget]
        bucket_rankings.append([serialize(doc) for doc in fused])
    # 跨桶融合维持现有项目的等权 RRF；改变权重只发生在向量/BM25 两路间。
    candidates = weighted_merge([(ranking, 1.0) for ranking in bucket_rankings])[:budget]
    return reranker._fallback_medical_rank(
        candidates,
        case["question"] if rerank_query == "raw_question" else cached["identity"]["query"],
        case["evidence_type"], actual_top_k=20,
    )


def evaluate_dataset(name: str, cases: list, provenance: dict, engine, embedder,
                     signature: dict, available: set, replay_only: bool) -> dict:
    cached_cases = []
    for index, case in enumerate(cases, start=1):
        candidates = collect_candidates(engine, embedder, case, signature, replay_only)
        cached_cases.append((case, candidates))
        print(f"{name} 候选 {index}/{len(cases)} {case['id']}", flush=True)
    # 规则重排需接收题目的证据类型，不能用 None 使类型加权失效。
    reranker = BGEReranker(top_k=20)
    configurations = []
    for rerank_query in ("enriched", "raw_question"):
        for mode in ("fixed80", "matched"):
            for vector_weight in (1, 2, 3):
                for budget in (12, 20, 40, 80):
                    rows = []
                    for case, cached in cached_cases:
                        ranked = rank_configuration(
                            cached, case, vector_weight, budget, mode, rerank_query, reranker,
                        )
                        metrics = retrieval_metrics(ranked, case["expected_source"], available)
                        rows.append({
                            "id": case["id"], "question": case["question"],
                            "evidence_type": case["evidence_type"], "expected_source": case["expected_source"],
                            **metrics,
                            "ranking": [{"rank": rank, "content_sha256": fingerprint(doc.page_content),
                                         **doc.metadata} for rank, doc in enumerate(ranked, start=1)],
                        })
                    configurations.append({
                        "mode": mode, "vector_weight": vector_weight, "bm25_weight": 1,
                        "rerank_query": rerank_query, "candidate_budget": budget,
                        "metrics": {metric: sum(row[metric] for row in rows) / len(rows) for metric in METRICS},
                        "cases": rows,
                    })
    report = {
        "dataset": name, "case_count": len(cases), "provenance": provenance,
        "signature": signature, "limitation": LIMITATION,
        "reranker_sha256": file_hash(MODEL_ROOT / "app/rag/reranker.py"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {"rrf_k": 60, "returned_top_k": 20,
                     "fixed80": "每路保留top80，桶内/全局候选均截断到预算",
                     "matched": "每路召回量、桶内/全局候选均为预算"},
        "configurations": configurations,
    }
    save_json(EXPERIMENT_ROOT / f"fusion_{name}.json", report)
    lines = [f"# 融合实验：{name}", "", LIMITATION, "",
             f"题数：{len(cases)}；查询：translate_query 第一变体；重排：规则回退；top-k：20。", "",
             "| 排序查询 | 召回模式 | 向量:BM25 | 候选预算 | R@3 | R@5 | R@10 | MRR | NDCG@10 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for config in configurations:
        values = " | ".join(f"{config['metrics'][key]:.4f}" for key in METRICS)
        lines.append(f"| {config['rerank_query']} | {config['mode']} | {config['vector_weight']}:1 | "
                     f"{config['candidate_budget']} | {values} |")
    (EXPERIMENT_ROOT / f"fusion_{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-only", action="store_true")
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--deduplicate-secondary", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    engine = UnifiedSearchEngine(
        persist_dir=str(EXPERIMENT_ROOT / "chroma_db_unified"), top_k=20, read_only=True,
    )
    signature, available = cache_signature(engine)
    embedder = DashScopeEmbeddings(model="text-embedding-v2")
    reports = []
    for name, cases, provenance in load_datasets(not args.primary_only, args.deduplicate_secondary):
        reports.append(evaluate_dataset(
            name, cases, provenance, engine, embedder, signature, available, args.replay_only,
        ))
    save_json(EXPERIMENT_ROOT / "fusion_summary.json", {
        "limitation": LIMITATION,
        "datasets": [{"dataset": report["dataset"], "case_count": report["case_count"],
                      "configurations": [{key: value for key, value in config.items() if key != "cases"}
                                         for config in report["configurations"]]}
                     for report in reports],
    })


if __name__ == "__main__":
    main()
