"""RAGAS 评估脚本: 真实检索链路 + LLM 生成, 计算 RAG 质量指标。

检索指标(与来源文档对齐, 无需 LLM):
- Recall@K    期望来源文档在 top-K 检索结果中的覆盖率
- MRR         首个期望来源排名的倒数均值
- NDCG@K      按期望来源二值相关性的归一化折损累计增益

RAGAS 指标(需 LLM 评分):
- context_precision / context_recall / faithfulness
- answer_relevancy / answer_correctness

评分器 LLM 使用 DashScope qwen-plus(OpenAI 兼容接口);
embeddings 使用项目 DashScope text-embedding-v2。

用法(容器内, 需先安装 ragas==0.2.15):
    python -m scripts.eval_ragas [--max-cases N] [--top-k 20]
"""
import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from app.evaluation.retrieval_metrics import (  # noqa: E402
    source_ids,
    retrieval_metrics as score_retrieval,
)

from app.agents.services.retrieval_service import route_collections  # noqa: E402
from app.agents.services.query_translator import translate_query  # noqa: E402
from app.rag.retrievers import (  # noqa: E402
    UnifiedSearchEngine,
    DashScopeEmbeddings,
    CONFIG,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("eval_ragas")

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CONTEXT_MAX_CHARS = 1500
BENCHMARK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "evaluation", "stroke_ragas.json")
REPORT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "evaluation", "regression_report.md")

def load_benchmark(path=BENCHMARK_PATH) -> list:
    """题集缺失或无效时失败，避免悄悄换用小样本而产生虚假提升。"""
    from scripts.eval_bm25 import load_cases

    cases = load_cases(Path(path))
    for case in cases:
        if not case.get("evidence_type") or not case.get("ground_truth"):
            raise ValueError(f"用例 {case['id']} 缺少 evidence_type 或 ground_truth")
    logger.info("加载 benchmark: %s (%s 题)", Path(path).name, len(cases))
    return cases


def _fingerprint(value) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _experiment_provenance(cases, engine) -> dict:
    corpus = sorted(
        json.dumps({"collection": key, "text": doc.page_content, "metadata": doc.metadata},
                   ensure_ascii=False, sort_keys=True)
        for key, retriever in engine.retrievers.items()
        if retriever.bm25 is not None
        for doc in retriever.bm25.docs
    )
    root = Path(__file__).resolve().parents[1]
    return {
        "cases_sha256": _fingerprint(cases),
        "corpus_sha256": _fingerprint(corpus),
        "implementation_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), root / "app/rag/bm25.py",
                         root / "app/rag/bm25_tokenizer.py", root / "app/rag/retrievers.py",
                         root / "app/rag/reranker.py",
                         root / "app/agents/services/query_translator.py",
                         root / "app/evaluation/retrieval_metrics.py")
        },
        "embedding_query_model": "text-embedding-v2",
        "query_variants": "仅第一变体；未评测服务层的多变体聚合和不匹配过滤",
        "relevance": "期望来源覆盖；不代表页面语义相关性或临床正确性",
    }


def source_hit(doc_source: str, expected: list) -> bool:
    """检索结果来源是否命中期望来源文档(支持 QA 对的多来源逗号拼接)。"""
    return bool(source_ids(doc_source) & source_ids(expected))


def retrieval_metrics(docs, expected: list, k_values=(3, 5, 10)) -> dict:
    """按期望来源文档计算 Recall@K / MRR / NDCG@K。

    相关性按"来源文档"聚合(同一来源多条只算一次), 避免 top-K 全来自
    同一文档时 recall 虚高。
    """
    score = score_retrieval(docs, expected)
    return {
        **{f"recall@{k}": round(score[f"recall_at_{k}"], 4) for k in k_values},
        "mrr": round(score["mrr"], 4),
        "ndcg@10": round(score["ndcg_at_10"], 4),
    }


def _generate_answer(llm, question: str, contexts: list) -> str:
    """用 LLM 依据检索上下文生成回答。"""
    context_text = "\n\n---\n\n".join(contexts) if contexts else "未检索到相关证据"
    prompt = (
        f"你是神经内科主治医师。请仅依据下列医学证据回答临床问题, "
        f"不要编造证据外内容, 不要给出具体剂量处方。\n\n"
        f"【证据】\n{context_text}\n\n【问题】\n{question}"
    )
    try:
        resp = llm.invoke([
            SystemMessage(content="你是严谨的医学回答者, 严格依据给定证据回答。"),
            HumanMessage(content=prompt),
        ])
        return str(getattr(resp, "content", "") or "")[:2000]
    except Exception as e:
        logger.error(f"生成答案失败: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser(description="RAGAS + 检索指标评估")
    parser.add_argument("--max-cases", type=int, default=0, help="最多评估题数(0=全部)")
    parser.add_argument("--top-k", type=int, default=20, help="检索指标用的 top-k")
    parser.add_argument("--cases", type=Path, default=Path(BENCHMARK_PATH), help="评测题集 JSON")
    parser.add_argument("--candidate-k", type=int, default=CONFIG["retrieval_candidate_k"],
                        help="每路召回候选数量，与最终返回条数无关")
    parser.add_argument("--rerank-k", type=int, default=CONFIG["rerank_candidate_k"],
                        help="固定重排候选数量，与最终返回条数无关")
    parser.add_argument(
        "--docs-dir",
        default=os.getenv("MEDICAL_DOCS_DIR") or CONFIG["docs_dir"],
        help="知识库 PDF 目录；评测从已有 collection 加载 BM25，不重新入库",
    )
    parser.add_argument(
        "--persist-dir",
        default=os.getenv("CHROMA_PERSIST_DIR") or CONFIG["persist_dir"],
        help="持久化 Chroma 目录",
    )
    parser.add_argument(
        "--bm25-tokenizer",
        choices=("jieba", "whitespace"),
        default="jieba",
        help="BM25 分词器；whitespace 用于与旧版本做同配置 A/B 对照",
    )
    parser.add_argument("--retrieval-only", action="store_true",
                        help="仅测真实检索指标，不生成答案或调用 RAGAS 评分")
    parser.add_argument("--report-path", type=Path, default=Path(REPORT_PATH),
                        help="Markdown 报告路径，同时生成同名 JSON")
    args = parser.parse_args()
    if args.top_k < 10:
        parser.error("--top-k 至少为 10，才能完整评测 Recall@10")
    if args.max_cases < 0:
        parser.error("--max-cases 不能为负数")
    if not 10 <= args.rerank_k <= args.candidate_k:
        parser.error("评测需满足 10 <= --rerank-k <= --candidate-k")

    # BM25 建索引与查询使用同一选择，进程重启后不会复用旧内存索引。
    os.environ["BM25_TOKENIZER"] = args.bm25_tokenizer

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY 未设置")
        sys.exit(1)

    cases = load_benchmark(args.cases)
    if args.max_cases:
        cases = cases[:args.max_cases]

    logger.info("初始化检索链路...")
    se = UnifiedSearchEngine(persist_dir=args.persist_dir, top_k=3,
                             docs_dir=args.docs_dir, read_only=True,
                             candidate_k=args.candidate_k, rerank_k=args.rerank_k)
    total_chunks = sum(c._collection.count() for c in se.collections.values())
    if total_chunks == 0:
        logger.error("❌ 向量库为空, 评估无意义")
        sys.exit(2)
    bm25_chunks = sum(
        len(retriever.bm25.docs)
        for retriever in se.retrievers.values()
        if retriever.bm25 is not None
    )
    if bm25_chunks == 0:
        logger.error(
            "❌ BM25 语料为空：请检查 collection 持久化数据"
        )
        sys.exit(3)
    for key, store in se.collections.items():
        if store._collection.count() > 0 and se.retrievers[key].bm25 is None:
            logger.error("%s 的 BM25 读取失败，拒绝部分降级的分词对照", key)
            sys.exit(3)
    logger.info(f"BM25 语料就绪: {bm25_chunks} 条 chunk ({args.bm25_tokenizer} tokenizer)")
    logger.info(f"向量库就绪: {total_chunks} 条 chunk")
    provenance = _experiment_provenance(cases, se)

    gen_llm = None
    if not args.retrieval_only:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (faithfulness, answer_relevancy, context_precision,
                                   context_recall, answer_correctness)
        gen_llm = ChatOpenAI(model="qwen-plus", api_key=api_key,
                            base_url=DASHSCOPE_BASE, temperature=0.2)

    rows, retr_rows = [], []
    for i, case in enumerate(cases, 1):
        q = case["question"]
        expected = case.get("expected_source", [])
        collections = route_collections(case["evidence_type"])
        variants = translate_query(q, case["evidence_type"])
        retrieval_query = variants[0] if variants else q

        # 检索 top-k(评估 Recall@K/MRR/NDCG)
        docs = se.search(retrieval_query, top_k_final=args.top_k,
                         evidence_type=case["evidence_type"],
                         collections=collections, rerank_query=q)
        rm = retrieval_metrics(docs, expected)
        retr_rows.append({"id": case["id"], "question": q, "retrieval_query": retrieval_query,
                          "ranking": [{"source": d.metadata.get("source", ""),
                                       "page": d.metadata.get("page"),
                                       "rerank_layer": d.metadata.get("rerank_layer")}
                                      for d in docs], **rm,
                          "first_hit_rank": next((i for i, d in enumerate(docs, 1)
                                                  if source_hit(d.metadata.get("source", ""),
                                                               expected)), "N/A")})
        # top3 上下文给 ragas + 答案生成
        contexts = [d.page_content[:CONTEXT_MAX_CHARS] for d in docs[:3]]
        if gen_llm is not None:
            answer = _generate_answer(gen_llm, q, contexts)
            rows.append({"question": q, "answer": answer, "contexts": contexts,
                         "ground_truth": case["ground_truth"]})
        logger.info(f"[{i}/{len(cases)}] {case['id']} 检索 top{args.top_k}, "
                    f"recall@5={rm['recall@5']} mrr={rm['mrr']}")

    # 检索指标汇总
    print("\n===== 检索指标(期望来源对齐) =====")
    hdr = ["id", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "first_hit"]
    print("  " + " | ".join(hdr))
    for r in retr_rows:
        print("  " + " | ".join(str(r[h]) for h in
                                 ["id", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "first_hit_rank"]))
    n = max(len(retr_rows), 1)
    avg = {k: round(sum(r[k] for r in retr_rows) / n, 4)
           for k in ("recall@3", "recall@5", "recall@10", "mrr", "ndcg@10")}
    print(f"  平均: recall@3={avg['recall@3']} recall@5={avg['recall@5']} "
          f"recall@10={avg['recall@10']} mrr={avg['mrr']} ndcg@10={avg['ndcg@10']}")

    if args.retrieval_only:
        _write_report(cases, retr_rows, avg, {}, args, se.stats(), provenance)
        return

    # RAGAS 指标
    dataset = Dataset.from_list(rows)
    judge_llm = ChatOpenAI(model="qwen-plus", api_key=api_key,
                           base_url=DASHSCOPE_BASE, temperature=0)
    emb_wrapper = LangchainEmbeddingsWrapper(DashScopeEmbeddings(model="text-embedding-v2"))
    metrics = [faithfulness, answer_relevancy, context_precision,
               context_recall, answer_correctness]
    result = evaluate(dataset, metrics=metrics,
                      llm=LangchainLLMWrapper(judge_llm), embeddings=emb_wrapper)
    df = result.to_pandas()
    print("\n===== RAGAS 评估结果 =====")
    print(df.to_string(index=False))
    print("\n===== 平均指标 =====")
    ragas_avg = {}
    import pandas as pd
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            ragas_avg[col] = round(float(df[col].mean()), 4)
            print(f"  {col}: {ragas_avg[col]}")

    # 生成回归报告
    _write_report(cases, retr_rows, avg, ragas_avg, args, se.stats(), provenance)


def _write_report(cases, retr_rows, avg, ragas_avg, args=None, stats=None, provenance=None):
    args = args or argparse.Namespace(top_k=20, bm25_tokenizer="jieba",
                                      report_path=Path(REPORT_PATH), retrieval_only=False)
    generated_at = datetime.now(timezone.utc).isoformat()
    layers = sorted({item.get("rerank_layer") or "unknown"
                     for row in retr_rows for item in row.get("ranking", [])})
    title = "RAG 检索回归报告（仅检索）" if args.retrieval_only else "RAGAS 检索回归报告"
    lines = [f"# {title}", "",
             f"- 用例数: {len(cases)}", f"- 生成时间: {generated_at}",
             f"- 检索 top-k: {args.top_k}(Recall@K 用 3/5/10)",
             f"- BM25 分词器: {args.bm25_tokenizer}",
             f"- 召回/重排候选预算: {(stats or {}).get('retrieval_config', {})}",
             f"- 实际重排方式: {', '.join(layers)}", "", "## 检索指标", "",
             "| id | recall@3 | recall@5 | recall@10 | MRR | NDCG@10 | 首命中位 |",
             "|---|---|---|---|---|---|---|"]
    for r in retr_rows:
        lines.append(f"| {r['id']} | {r['recall@3']} | {r['recall@5']} | "
                     f"{r['recall@10']} | {r['mrr']} | {r['ndcg@10']} | {r['first_hit_rank']} |")
    lines.append(f"| **平均** | {avg['recall@3']} | {avg['recall@5']} | "
                 f"{avg['recall@10']} | {avg['mrr']} | {avg['ndcg@10']} | - |")
    lines += ["", "## RAGAS 指标", ""]
    for k, v in ragas_avg.items():
        lines.append(f"- {k}: {v}")
    if not ragas_avg:
        lines.append("本次仅评测检索，未生成或评分答案。")
    lines += ["", "## 说明", "",
              "- Recall@K/MRR/NDCG 按期望来源文档(evaluation/stroke_ragas.json 的 expected_source)计算",
              "- 来源文件名按统一别名规则匹配，两种分词器使用相同规则；不能直接与旧口径快照作因果比较",
              "- 本次仅使用查询第一变体，未覆盖服务层多变体聚合和不匹配过滤",
              "- 来源命中不证明页面语义相关性或临床正确性"]
    if ragas_avg:
        lines.append("- RAGAS 指标由 qwen-plus 评分(小样本噪声较大, 以检索指标为主要回归依据)")
    if provenance:
        lines += ["", "## 实验溯源", "",
                  f"- 题集 SHA-256: `{provenance['cases_sha256']}`",
                  f"- Collection 语料 SHA-256: `{provenance['corpus_sha256']}`"]
    path = args.report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    report = {
        "generated_at": generated_at,
        "cases": len(cases),
        "top_k": args.top_k,
        "bm25_tokenizer": args.bm25_tokenizer,
        "retrieval_only": args.retrieval_only,
        "rerank_layers": layers,
        "provenance": provenance,
        "metrics": {"recall_at_3": avg["recall@3"], "recall_at_5": avg["recall@5"],
                    "recall_at_10": avg["recall@10"], "mrr": avg["mrr"],
                    "ndcg_at_10": avg["ndcg@10"], **ragas_avg},
        "knowledge_base": stats,
        "results": retr_rows,
    }
    path.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    logger.info(f"回归报告已写入 {path}")


if __name__ == "__main__":
    main()
