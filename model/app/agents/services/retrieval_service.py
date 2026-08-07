import logging
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

logger = logging.getLogger(__name__)

# Evidence Type Router:决策类型 → 检索类别过滤
# 返回允许类别列表;含 '!' 前缀为排除类别
EVIDENCE_CATEGORY_ROUTING = {
    "treatment": ["指南", "专家共识", "规范"],       # 治疗决策 → 指南/共识
    "diagnosis": ["指南", "专家共识", "规范"],       # 诊断 → 标准/指南
    "etiology": ["指南", "专家共识"],               # 病因 → 指南/TOAST相关
    "anatomy": ["教材"],                            # 解剖定位 → 教材
    "prognosis": ["指南", "专家共识"],
    "prevention": ["指南", "专家共识", "规范"],
    # 兜底:不限制
}


def route_category_filter(evidence_type: str) -> List[str] | None:
    """按证据类型返回类别过滤(Evidence Router)。"""
    key = (evidence_type or "").strip().lower()
    if not key:
        return None
    if key in EVIDENCE_CATEGORY_ROUTING:
        return EVIDENCE_CATEGORY_ROUTING[key]
    # 中文或部分匹配
    for k, v in EVIDENCE_CATEGORY_ROUTING.items():
        if k in key or key in k:
            return v
    return None


class EvidenceRetrievalService:

    def __init__(self, retriever, top_k=3):
        self.retriever = retriever
        self.top_k = top_k

    def retrieve_single(self, query: str, evidence_prefix: str = "R1-Q1",
                        evidence_type: str = None, category_filter: List[str] = None) -> str:

        if category_filter is None and evidence_type:
            category_filter = route_category_filter(evidence_type)

        docs = self.retriever.search(query, self.top_k, category_filter=category_filter)

        if not docs:
            return ""

        results = []

        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "未知")
            page = doc.metadata.get("page", "?")
            score = doc.metadata.get("relevance_score", "N/A")
            category = doc.metadata.get("category", "?")

            content = doc.page_content[:500]

            results.append(
                f"【证据 {evidence_prefix}-E{i+1}】"
                f"[来源:{source} p.{page}]"
                f"[类别:{category}]"
                f"(相关度:{score})\n"
                f"{content}"
            )

        return "\n\n".join(results)

    async def aretrieve_single(self, query: str, evidence_prefix: str = "R1-Q1",
                               evidence_type: str = None, category_filter: List[str] = None) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.retrieve_single, query, evidence_prefix, evidence_type, category_filter)

    async def aparallel_retrieve(self, queries: List[str], round_number: int = 1,
                                 evidence_types: List[str] = None) -> str:
        """并行检索,支持按决策类型逐查询路由证据源。"""
        import asyncio
        types = evidence_types or [None] * len(queries)
        tasks = [
            self.aretrieve_single(
                q, f"R{round_number}-Q{i + 1}",
                evidence_type=types[i] if i < len(types) else None,
            )
            for i, q in enumerate(queries)
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        parts = []
        for i, (q, content) in enumerate(zip(queries, results_list)):
            if isinstance(content, Exception):
                logger.error(f"检索失败 {q}: {content}")
                content = ""
            if content:
                parts.append(f"### 检索维度{i+1}: {q}\n{content}")

        return "\n\n---\n\n".join(parts)

    def parallel_retrieve(self, queries: List[str]) -> str:

        results = {}

        with ThreadPoolExecutor(
            max_workers=min(3, len(queries))
        ) as executor:

            future_map = {
                executor.submit(self.retrieve_single, q, f"R1-Q{i + 1}"): q
                for i, q in enumerate(queries)
            }

            for future in as_completed(future_map):
                q = future_map[future]

                try:
                    results[q] = future.result()
                except Exception as e:
                    logger.error(f"检索失败 {q}: {e}")
                    results[q] = ""

        parts = []

        for i, q in enumerate(queries):
            content = results.get(q, "")

            if content:
                parts.append(
                    f"### 检索维度{i+1}: {q}\n{content}"
                )

        return "\n\n---\n\n".join(parts)
