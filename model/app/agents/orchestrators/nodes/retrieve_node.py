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

        # Decision → Evidence Type Router:按决策节点的 evidence_type 路由检索类别
        # retrieval_tasks 由 Decision Planner 生成,含 evidence_type 字段
        evidence_types: List[str] = []
        tasks = state.get("retrieval_tasks", [])
        decisions = state.get("clinical_decisions", [])
        if isinstance(tasks, list) and tasks:
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                ev_type = task.get("evidence_type") or task.get("type") or ""
                evidence_types.append(str(ev_type).strip() if ev_type else "")
        elif isinstance(decisions, list) and decisions:
            # 无 tasks 时回退到决策节点的 evidence_type
            evidence_types = [
                str(d.get("evidence_type", "")).strip()
                for d in decisions if isinstance(d, dict)
            ][:len(queries)]

        evidence = await self.medical_assistant.afast_parallel_retrieve(
            queries,
            round_number=retrieval_round,
            evidence_types=evidence_types,
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
