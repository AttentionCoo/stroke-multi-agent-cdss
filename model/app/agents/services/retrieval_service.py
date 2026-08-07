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

        # 过滤检索
        docs = self.retriever.search(query, self.top_k, category_filter=category_filter)

        # P2: Retrieval Failure Recovery — 0 结果时多级恢复
        if not docs:
            recovery = self._recover_retrieval(query, evidence_type, category_filter)
            if recovery:
                docs = recovery

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

    def _recover_retrieval(self, query: str, evidence_type: str | None,
                           category_filter: List[str] | None):
        """
        Retrieval Failure Recovery:
        1. 去掉类别过滤, 无过滤检索
        2. 扩展同义词(概念 OR 组)检索
        3. 降低限定(用核心概念子集)检索
        """
        from app.agents.services.query_translator import (
            extract_medical_concepts, build_or_and_query, expand_synonyms,
        )

        # 级别1:去掉类别过滤(Evidence Router 过严时)
        if category_filter:
            logger.info(f"⚠️ [Recovery-1] 类别过滤 {category_filter} 无结果, 回退无过滤检索")
            docs = self.retriever.search(query, self.top_k, category_filter=None)
            if docs:
                return docs

        # 级别2:同义词扩展(OR 组)
        concepts = extract_medical_concepts(query)
        or_and = build_or_and_query(concepts) if concepts else ""
        candidates = [or_and] if or_and else []
        candidates += expand_synonyms(query)[:3]
        for variant in candidates:
            if variant.strip().casefold() == query.strip().casefold():
                continue
            logger.info(f"⚠️ [Recovery-2] 同义词扩展检索: {variant[:60]}...")
            docs = self.retriever.search(variant, self.top_k, category_filter=None)
            if docs:
                return docs

        # 级别3:核心概念子集(取前2个概念组合)
        if concepts and len(concepts) > 2:
            subset = dict(list(concepts.items())[:2])
            subset_query = build_or_and_query(subset)
            logger.info(f"⚠️ [Recovery-3] 降低限定检索: {subset_query[:60]}...")
            docs = self.retriever.search(subset_query, self.top_k, category_filter=None)
            if docs:
                return docs

        return []

    async def aretrieve_single(self, query: str, evidence_prefix: str = "R1-Q1",
                               evidence_type: str = None, category_filter: List[str] = None) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.retrieve_single, query, evidence_prefix, evidence_type, category_filter)

    async def aparallel_retrieve(self, queries: List[str], round_number: int = 1,
                                 evidence_types: List[str] = None) -> str:
        """并行检索,支持按决策类型路由证据源,并用 Query Translator 多路召回。

        每条临床查询先经 Medical Query Translator 转换为多组文献查询变体
        (术语标准化+同义词扩展+证据源关键词),再并行检索,提升召回率。
        """
        import asyncio
        from app.agents.services.query_translator import translate_query

        types = evidence_types or [None] * len(queries)

        # 1. 翻译:每条查询 → 多组变体
        translated: List[tuple] = []  # (原查询, 证据类型, 变体列表)
        for i, q in enumerate(queries):
            ev_type = types[i] if i < len(types) else None
            variants = translate_query(q, ev_type)
            translated.append((q, ev_type, variants))

        # 2. 并行检索所有变体
        tasks = []
        task_meta = []  # (原查询, 变体, 前缀)
        for i, (q, ev_type, variants) in enumerate(translated):
            for j, variant in enumerate(variants):
                tasks.append(self.aretrieve_single(
                    variant, f"R{round_number}-Q{i + 1}v{j + 1}",
                    evidence_type=ev_type,
                ))
                task_meta.append((q, variant))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 按原查询聚合变体结果
        parts = []
        for i, (q, _variant) in enumerate(task_meta):
            content = results_list[i]
            if isinstance(content, Exception):
                logger.error(f"检索失败 {q}: {content}")
                continue
            if content:
                parts.append(content)

        # 去重(内容相同的检索块合并)
        seen_blocks = set()
        unique_parts = []
        for block in parts:
            key = block[:200]
            if key in seen_blocks:
                continue
            seen_blocks.add(key)
            unique_parts.append(block)

        return "\n\n---\n\n".join(unique_parts)

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
