"""Self-RAG 证据质量评估与查询重写节点。"""

import logging
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.json_utils import parse_json_output
from app.agents.utils.text_utils import truncate_text


logger = logging.getLogger(__name__)


class EvidenceJudgeNode(BaseNode):
    """判断证据是否充分，并控制是否继续检索。"""

    def __init__(self, llm, quality_threshold: float = 0.65, max_rounds: int = 2):
        self.llm = llm
        self.quality_threshold = quality_threshold
        self.max_rounds = max_rounds

    async def run(self, state: ClinicalState) -> Dict:
        evidence = str(state.get("evidence", "") or "").strip()
        retrieval_round = int(state.get("retrieval_round", 0) or 0)
        questions = state.get("clinical_questions", [])

        if not evidence:
            return {
                "evidence_quality": 0.0,
                "evidence_assessment": "当前轮次未检索到可用证据",
                "missing_information": list(questions),
                "need_retrieve": retrieval_round < self.max_rounds,
            }

        prompt = f"""你是 Self-RAG 证据审查器。判断检索证据是否足以支持后续临床推理。

【临床问题】
{questions}

【检索证据】
{truncate_text(evidence, 6000)}

只输出 JSON：
{{
  "quality": 0.0,
  "is_sufficient": false,
  "missing_information": ["尚未被证据覆盖的临床问题或关键信息"],
  "assessment": "一句话说明证据的相关性、权威性和覆盖度"
}}

评分需同时考虑：与病例的相关性、来源可信度、时效性、关键问题覆盖度。"""

        data = None
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是独立的循证医学证据审查员。"),
                HumanMessage(content=prompt),
            ])
            data = parse_json_output(getattr(response, "content", ""), None)
        except Exception as exc:
            logger.warning("证据质量评估失败，使用启发式结果: %s", exc)

        if not isinstance(data, dict):
            evidence_count = evidence.count("【证据 ")
            # 无法完成语义审查时保持保守，证据条数不能替代来源与覆盖度判断。
            quality = min(0.60, 0.20 + evidence_count * 0.10)
            data = {
                "quality": quality,
                "is_sufficient": False,
                "missing_information": list(questions),
                "assessment": (
                    f"证据语义审查不可用；仅确认检索到 {evidence_count} 条带编号候选证据，"
                    "尚未验证来源、时效与覆盖度"
                ),
            }

        try:
            quality = max(0.0, min(1.0, float(data.get("quality", 0.0))))
        except (TypeError, ValueError):
            quality = 0.0
        missing = data.get("missing_information", [])
        if not isinstance(missing, list):
            missing = []
        sufficient = bool(data.get("is_sufficient", False)) and quality >= self.quality_threshold
        can_retry = retrieval_round < self.max_rounds

        return {
            "evidence_quality": quality,
            "evidence_assessment": str(data.get("assessment", "") or "").strip(),
            "missing_information": [str(item).strip() for item in missing if str(item).strip()],
            "need_retrieve": not sufficient and can_retry,
        }


class QueryRewriteNode(BaseNode):
    """根据证据缺口生成下一轮不重复的医学检索式。"""

    def __init__(self, llm, max_queries: int = 6):
        self.llm = llm
        self.max_queries = max_queries

    async def run(self, state: ClinicalState) -> Dict:
        previous = [str(item).strip() for item in state.get("retrieved_queries", [])]
        missing = [str(item).strip() for item in state.get("missing_information", [])]
        prompt = f"""你是医学检索查询重写专家。当前证据不足，请为下一轮生成更精确且不重复的查询。

【病例】{state.get('case_text', '')}
【证据缺口】{missing}
【已检索查询】{previous}
【证据评估】{state.get('evidence_assessment', '')}

只输出 JSON：{{"queries": ["查询1", "查询2"]}}
查询可使用中英文指南术语、同义词、检查名称和关键禁忌证。"""

        candidates: List[str] = []
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你负责修正低召回率的医学检索查询。"),
                HumanMessage(content=prompt),
            ])
            data = parse_json_output(getattr(response, "content", ""), {})
            if isinstance(data, dict) and isinstance(data.get("queries"), list):
                candidates = data["queries"]
            elif isinstance(data, list):
                candidates = data
        except Exception as exc:
            logger.warning("查询重写失败，使用证据缺口回退: %s", exc)

        if not candidates:
            candidates = missing or state.get("clinical_questions", [])

        previous_keys = {item.casefold() for item in previous}
        queries = []
        seen = set()
        for value in candidates:
            query = str(value or "").strip()
            key = query.casefold()
            if not query or key in previous_keys or key in seen:
                continue
            seen.add(key)
            queries.append(query)

        queries = queries[:self.max_queries]
        return {
            "retrieval_queries": queries,
            "need_retrieve": bool(queries),
        }
