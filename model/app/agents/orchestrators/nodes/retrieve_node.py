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
        retrieval_round = int(state.get("retrieval_round", 0) or 0) + 1
        previous_queries = [str(item).strip() for item in state.get("retrieved_queries", [])]
        previous_keys = {item.casefold() for item in previous_queries}
        queries = [
            str(item).strip()
            for item in state.get("retrieval_queries", state.get("clinical_questions", []))
            if str(item).strip() and str(item).strip().casefold() not in previous_keys
        ]

        if not queries:
            return {
                "need_retrieve": False,
                "retrieval_queries": [],
                "retrieved_queries": previous_queries,
            }

        # Decision → Evidence Router:优先用 Evidence Router Agent 的输出
        # (evidence_type + target_categories + keywords), 回退到决策节点的 evidence_type
        router_types = state.get("router_evidence_types", [])
        router_categories = state.get("router_categories", [])
        router_keywords = state.get("router_keywords", [])

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
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    ev_type = task.get("evidence_type") or task.get("type") or ""
                    evidence_types.append(str(ev_type).strip() if ev_type else "")
            elif isinstance(decisions, list) and decisions:
                evidence_types = [
                    str(d.get("evidence_type", "")).strip()
                    for d in decisions if isinstance(d, dict)
                ][:len(queries)]

        # 附加 Router 关键词到查询(增强检索)
        if isinstance(router_keywords, list) and len(router_keywords) == len(queries):
            enriched_queries = []
            for i, q in enumerate(queries):
                kws = router_keywords[i] if isinstance(router_keywords[i], list) else []
                kws = [str(k) for k in kws if str(k).strip()]
                if kws:
                    enriched_queries.append(f"{q} {' '.join(kws[:3])}")
                else:
                    enriched_queries.append(q)
            queries = enriched_queries

        evidence = await self.medical_assistant.afast_parallel_retrieve(
            queries,
            round_number=retrieval_round,
            evidence_types=evidence_types,
            category_filters=category_filters,
        )
        previous_evidence = str(state.get("evidence", "") or "").strip()
        combined = "\n\n---\n\n".join(
            part for part in (previous_evidence, evidence.strip()) if part
        )
        return {
            "evidence": truncate_text(combined, MAX_EVIDENCE_CHARS),
            "retrieval_round": retrieval_round,
            "retrieved_queries": previous_queries + queries,
        }
