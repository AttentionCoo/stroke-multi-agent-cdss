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
import json
import logging
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from datasets import Dataset  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
)

from app.agents.services.retrieval_service import route_collections  # noqa: E402
from app.agents.services.query_translator import translate_query  # noqa: E402
from app.rag.retrievers import (  # noqa: E402
    UnifiedSearchEngine,
    DashScopeEmbeddings,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("eval_ragas")

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CONTEXT_MAX_CHARS = 1500
BENCHMARK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "evaluation", "stroke_ragas.json")
REPORT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "evaluation", "regression_report.md")

# 兜底用例(找不到 benchmark 文件时)
FALLBACK_CASES = [
    {"id": "fallback-01", "question": "急性缺血性卒中患者, 发病3小时, NIHSS评分18分, 是否适合静脉溶栓?",
     "evidence_type": "treatment",
     "expected_source": ["中国急性缺血性卒中诊治指南2023.pdf"],
     "ground_truth": "发病3小时内且NIHSS≥5分的急性缺血性卒中患者, 无禁忌证时推荐静脉溶栓。"},
    {"id": "fallback-02", "question": "左侧大脑中动脉综合征的临床表现和解剖定位?",
     "evidence_type": "anatomy",
     "expected_source": ["neuroanatomy_clinical_cases.pdf"],
     "ground_truth": "MCA梗死常致对侧偏瘫、偏身感觉障碍、偏盲, 优势半球受累可有失语。"},
    {"id": "fallback-03", "question": "急性缺血性卒中 TOAST 病因分型包括哪些?",
     "evidence_type": "etiology",
     "expected_source": ["中国急性缺血性卒中诊治指南2023.pdf"],
     "ground_truth": "TOAST 分型: 大动脉粥样硬化型、心源性栓塞型、小动脉闭塞型、其他明确病因型、不明原因型。"},
]


def load_benchmark() -> list:
    """加载 30 题 benchmark; 不存在时回退兜底用例。"""
    path = Path(BENCHMARK_PATH)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)
        logger.info(f"加载 benchmark: {path.name} ({len(cases)} 题)")
        return cases
    logger.warning(f"⚠️  benchmark 不存在({path}), 使用兜底 {len(FALLBACK_CASES)} 题")
    return FALLBACK_CASES


def source_hit(doc_source: str, expected: list) -> bool:
    """检索结果来源是否命中期望来源文档(支持 QA 对的多来源逗号拼接)。"""
    src = str(doc_source or "").strip()
    if not src:
        return False  # 来源缺失不视为命中, 避免空串 in exp 恒真
    for exp in expected:
        if exp and (exp in src or src in exp):
            return True
    return False


def retrieval_metrics(docs, expected: list, k_values=(3, 5, 10)) -> dict:
    """按期望来源文档计算 Recall@K / MRR / NDCG@K。

    相关性按"来源文档"聚合(同一来源多条只算一次), 避免 top-K 全来自
    同一文档时 recall 虚高。
    """
    m = {}
    # 首个命中来源的 rank(条目级, 用于 MRR)
    first_hit_rank = None
    # 命中来源集合(去重, 用于 recall/ndcg)
    hit_sources = set()
    for i, d in enumerate(docs, start=1):
        src = d.metadata.get("source", "")
        if source_hit(src, expected):
            if first_hit_rank is None:
                first_hit_rank = i
            hit_sources.add(str(src))
    for k in k_values:
        top_sources = {d.metadata.get("source", "") for d in docs[:k]}
        n_hit = sum(1 for s in top_sources if source_hit(s, expected))
        m[f"recall@{k}"] = round(min(1.0, n_hit / max(len(expected), 1)), 4)
    m["mrr"] = round(1.0 / first_hit_rank, 4) if first_hit_rank else 0.0
    # NDCG@10: 按来源位置相关性(1=命中来源首次出现位置)
    dcg = 0.0
    seen = set()
    for i, d in enumerate(docs[:10], start=1):
        src = str(d.metadata.get("source", ""))
        if src in seen:
            continue
        seen.add(src)
        if source_hit(src, expected):
            dcg += 1.0 / math.log2(i + 1)
    idcg = sum(1.0 / math.log2(i + 1)
               for i in range(1, min(len(expected), 10) + 1))
    m["ndcg@10"] = round(dcg / idcg, 4) if idcg else 0.0
    return m


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
    args = parser.parse_args()

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY 未设置")
        sys.exit(1)

    cases = load_benchmark()
    if args.max_cases:
        cases = cases[:args.max_cases]

    logger.info("初始化检索链路...")
    se = UnifiedSearchEngine(persist_dir="/app/chroma_db_unified", top_k=3,
                             docs_dir="/app/empty_docs")
    total_chunks = sum(c._collection.count() for c in se.collections.values())
    if total_chunks == 0:
        logger.error("❌ 向量库为空, 评估无意义")
        sys.exit(2)
    logger.info(f"向量库就绪: {total_chunks} 条 chunk")

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
                         collections=collections)
        rm = retrieval_metrics(docs, expected)
        retr_rows.append({"id": case["id"], "question": q, **rm,
                          "first_hit_rank": next((i for i, d in enumerate(docs, 1)
                                                  if source_hit(d.metadata.get("source", ""),
                                                               expected)), "N/A")})
        # top3 上下文给 ragas + 答案生成
        contexts = [d.page_content[:CONTEXT_MAX_CHARS] for d in docs[:3]]
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
    _write_report(cases, retr_rows, avg, ragas_avg)


def _write_report(cases, retr_rows, avg, ragas_avg):
    lines = ["# RAGAS 检索回归报告", "",
             f"- 用例数: {len(cases)}", f"- 生成时间: {Path(__file__).stat().st_mtime}",
             f"- 检索 top-k: 20(Recall@K 用 3/5/10)", "", "## 检索指标", "",
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
    lines += ["", "## 说明", "",
              "- Recall@K/MRR/NDCG 按期望来源文档(evaluation/stroke_ragas.json 的 expected_source)计算",
              "- RAGAS 指标由 qwen-plus 评分(小样本噪声较大, 以检索指标为主要回归依据)"]
    Path(REPORT_PATH).write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"回归报告已写入 {REPORT_PATH}")


if __name__ == "__main__":
    main()
