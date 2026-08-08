"""RAGAS 评估脚本: 真实检索链路 + LLM 生成, 计算 RAG 质量指标。

指标:
- context_precision  检索上下文精确率(检索质量)
- context_recall     检索上下文召回率(需 ground_truth)
- faithfulness       答案对上下文的忠实度(生成质量)
- answer_relevancy   答案相关性(生成质量)
- answer_correctness 答案正确性(需 ground_truth)

评分器 LLM 使用 DashScope qwen-plus(OpenAI 兼容接口);
embeddings 使用项目 DashScope text-embedding-v2。

用法(容器内, 需先安装 ragas==0.2.15):
    python -m scripts.eval_ragas
"""
import logging
import os
import sys

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
from app.rag.retrievers import (  # noqa: E402
    UnifiedSearchEngine,
    DashScopeEmbeddings,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("eval_ragas")

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CONTEXT_MAX_CHARS = 1500

# 评估用例: 覆盖各检索路由的典型临床问题
CASES = [
    {
        "question": "急性缺血性卒中患者, 发病3小时, NIHSS评分18分, 是否适合静脉溶栓?",
        "evidence_type": "treatment",
        "ground_truth": "发病3小时内且NIHSS≥5分的急性缺血性卒中患者, 无禁忌证时推荐静脉溶栓(阿替普酶0.9mg/kg, 最大90mg, 总量10%静脉推注后剩余90%静滴1小时)。NIHSS评分高不是溶栓禁忌。",
    },
    {
        "question": "左侧大脑中动脉综合征的临床表现和解剖定位?",
        "evidence_type": "anatomy",
        "ground_truth": "大脑中动脉(MCA)梗死常导致对侧偏瘫、偏身感觉障碍、偏盲, 优势半球受累可有失语, 非优势半球可有偏侧忽略。主干闭塞多为大面积梗死。",
    },
    {
        "question": "急性缺血性卒中 TOAST 病因分型包括哪些?",
        "evidence_type": "etiology",
        "ground_truth": "TOAST 分型包括: 大动脉粥样硬化型、心源性栓塞型、小动脉闭塞型、其他明确病因型、不明原因型五类。",
    },
    {
        "question": "房颤患者缺血性卒中后二级预防如何选择抗凝治疗?",
        "evidence_type": "prevention",
        "ground_truth": "房颤相关缺血性卒中后应评估抗凝指征, 无禁忌时优先选择新型口服抗凝药(利伐沙班/达比加群等), 华法林作为备选; 急性期抗凝启动时机需个体化评估出血与复发风险。",
    },
    {
        "question": "急性缺血性卒中患者血压管理原则是什么?",
        "evidence_type": "treatment",
        "ground_truth": "拟行静脉溶栓患者血压需控制在185/110mmHg以下; 未溶栓患者急性期血压升高一般不予紧急降压, 除非合并其他特殊情况。溶栓后24小时内血压控制在180/105mmHg以下。",
    },
]


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
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY 未设置")
        sys.exit(1)

    # 检索链路(连接已有 5 collection 向量库)
    logger.info("初始化检索链路...")
    se = UnifiedSearchEngine(persist_dir="/app/chroma_db_unified", top_k=3,
                             docs_dir="/app/empty_docs")

    gen_llm = ChatOpenAI(model="qwen-plus", api_key=api_key,
                         base_url=DASHSCOPE_BASE, temperature=0.2)

    rows = []
    for i, case in enumerate(CASES, 1):
        q = case["question"]
        collections = route_collections(case["evidence_type"])
        logger.info(f"[{i}/{len(CASES)}] 检索+生成: {q[:40]}... (collections={collections})")
        docs = se.search(q, top_k_final=3, evidence_type=case["evidence_type"],
                         collections=collections)
        contexts = [d.page_content[:CONTEXT_MAX_CHARS] for d in docs]
        answer = _generate_answer(gen_llm, q, contexts)
        rows.append({
            "question": q,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": case["ground_truth"],
        })
        logger.info(f"   contexts={len(contexts)} 条, answer_len={len(answer)}")

    dataset = Dataset.from_list(rows)

    # RAGAS 评分器(qwen-plus) + embedding(text-embedding-v2)
    judge_llm = ChatOpenAI(model="qwen-plus", api_key=api_key,
                           base_url=DASHSCOPE_BASE, temperature=0)
    emb_wrapper = LangchainEmbeddingsWrapper(DashScopeEmbeddings(model="text-embedding-v2"))

    metrics = [faithfulness, answer_relevancy, context_precision,
               context_recall, answer_correctness]
    result = evaluate(
        dataset,
        metrics=metrics,
        llm=LangchainLLMWrapper(judge_llm),
        embeddings=emb_wrapper,
    )

    df = result.to_pandas()
    print("\n===== RAGAS 评估结果 =====")
    print(df.to_string(index=False))
    print("\n===== 平均指标 =====")
    import pandas as pd
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            print(f"  {col}: {df[col].mean():.4f}")


if __name__ == "__main__":
    main()
