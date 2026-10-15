"""证据检索节点：调用检索服务并行召回证据，并与历史证据合并截断后写入 state。"""
import logging
import asyncio
from typing import Dict
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_EVIDENCE_CHARS
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)


class RetrieveNode(BaseNode):
    """证据检索节点"""

    def __init__(self, medical_assistant):
        self.medical_assistant = medical_assistant

    async def run(self, state: ClinicalState) -> Dict:
        """执行一轮证据检索：查询去重 → 可选附加路由关键词 → 并行召回 → 合并并截断历史证据。"""
        retrieval_round = int(state.get("retrieval_round", 0) or 0) + 1
        previous_queries = [str(item).strip() for item in state.get("retrieved_queries", [])]
        previous_keys = {item.casefold() for item in previous_queries}
        input_queries = [
            str(item).strip()
            for item in state.get("retrieval_queries", state.get("clinical_questions", []))
        ]
        query_indices = [
            i for i, query in enumerate(input_queries)
            if query and query.casefold() not in previous_keys
        ]
        queries = [input_queries[i] for i in query_indices]

        if not queries:
            return {
                "need_retrieve": False,
                "retrieval_queries": [],
                "retrieved_queries": previous_queries,
            }

        # Decision → Evidence Router:优先用 Evidence Router Agent 的输出
        # (evidence_type + target_categories + keywords), 回退到决策节点的 evidence_type
        def select_query_values(values, *, allow_partial=False):
            """路由数组与原查询同步筛选，兼容 Router 已移除空查询的数组。"""
            if not isinstance(values, list):
                return []
            nonempty_indices = [i for i, query in enumerate(input_queries) if query]
            indices = query_indices
            if len(values) == len(nonempty_indices):
                indices = [nonempty_indices.index(i) for i in query_indices]
            elif len(values) != len(input_queries) and not allow_partial:
                return []
            return [values[i] if i < len(values) else None for i in indices]

        router_types = select_query_values(state.get("router_evidence_types", []))
        router_categories = select_query_values(state.get("router_categories", []))
        router_keywords = select_query_values(state.get("router_keywords", []))

        evidence_types: List[str] = []
        category_filters: List[List[str]] = []
        if isinstance(router_types, list) and len(router_types) == len(queries):
            evidence_types = [str(t) if t else "" for t in router_types]
            if isinstance(router_categories, list) and len(router_categories) == len(queries):
                category_filters = [list(c) if isinstance(c, list) else [] for c in router_categories]
        else:
            # 回退:从决策节点取 evidence_type
            tasks = state.get("retrieval_tasks", [])
            decisions = state.get("clinical_decisions", [])
            if isinstance(tasks, list) and tasks:
                tasks_by_query = {
                    str(task.get("query", "")).strip().casefold(): task
                    for task in tasks if isinstance(task, dict) and task.get("query")
                }
                selected_tasks = select_query_values(tasks, allow_partial=True)
                for i, query in enumerate(queries):
                    task = tasks_by_query.get(query.casefold(), selected_tasks[i])
                    # 具名任务只能关联自身查询，扩展查询不能冒用其他任务的类型。
                    if not isinstance(task, dict) or (
                        task.get("query") and str(task["query"]).strip().casefold() != query.casefold()
                    ):
                        evidence_types.append("")
                        continue
                    ev_type = task.get("evidence_type") or task.get("type") or ""
                    evidence_types.append(str(ev_type).strip() if ev_type else "")
            elif isinstance(decisions, list) and decisions:
                evidence_types = [
                    str(d.get("evidence_type", "")).strip() if isinstance(d, dict) else ""
                    for d in select_query_values(decisions, allow_partial=True)
                ]

        # 新 Router 的具名路由优先按查询关联，旧数组继续按原索引兼容。
        routes = state.get("router_routes", [])
        routes_by_query = {
            str(route.get("query", "")).strip().casefold(): route
            for route in routes if isinstance(route, dict) and route.get("query")
        } if isinstance(routes, list) else {}
        if routes_by_query:
            evidence_types = [
                str(routes_by_query.get(query.casefold(), {}).get(
                    "evidence_type", evidence_types[i] if i < len(evidence_types) else ""))
                for i, query in enumerate(queries)
            ]
            category_filters = [
                routes_by_query.get(query.casefold(), {}).get(
                    "target_categories", category_filters[i] if i < len(category_filters) else [])
                for i, query in enumerate(queries)
            ]
            router_keywords = [
                routes_by_query.get(query.casefold(), {}).get(
                    "keywords", router_keywords[i] if i < len(router_keywords) else [])
                for i, query in enumerate(queries)
            ]

        # 原始问题用于排序和跨轮去重，Router 关键词只扩展召回查询。
        original_queries = list(queries)
        # 附加 Router 关键词到查询(增强检索)
        if isinstance(router_keywords, list) and len(router_keywords) == len(queries):
            enriched_queries = []
            for i, q in enumerate(queries):
                kws = router_keywords[i] if isinstance(router_keywords[i], list) else []
                kws = [str(k) for k in kws if str(k).strip()]
                if kws:
                    # 每条查询最多附加 3 个路由关键词，防止检索式过长而降低召回
                    enriched_queries.append(f"{q} {' '.join(kws[:3])}")
                else:
                    enriched_queries.append(q)
            queries = enriched_queries

        # 没有富化时保留旧调用参数，兼容旧门面和注入的检索实现。
        rerank_options = {"rerank_queries": original_queries} if queries != original_queries else {}
        evidence = await self.medical_assistant.afast_parallel_retrieve(
            queries,
            round_number=retrieval_round,
            evidence_types=evidence_types,
            category_filters=category_filters,
            **rerank_options,
        )
        previous_evidence = str(state.get("evidence", "") or "").strip()
        combined = "\n\n---\n\n".join(
            part for part in (previous_evidence, evidence.strip()) if part
        )
        return {
            "evidence": truncate_text(combined, MAX_EVIDENCE_CHARS),
            "retrieval_round": retrieval_round,
            "retrieved_queries": previous_queries + original_queries,
        }
