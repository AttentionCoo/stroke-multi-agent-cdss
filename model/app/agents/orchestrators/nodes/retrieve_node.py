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

        evidence = await self.medical_assistant.afast_parallel_retrieve(
            queries,
            round_number=retrieval_round,
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
