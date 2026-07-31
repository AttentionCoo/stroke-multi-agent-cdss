"""临床检索规划与医学查询扩展节点。"""

import logging
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.json_utils import parse_json_output


logger = logging.getLogger(__name__)


class ResearchPlanNode(BaseNode):
    """把临床问题拆成检索任务，并生成专业查询与 HyDE 文档。"""

    def __init__(self, llm, max_queries: int = 8):
        self.llm = llm
        self.max_queries = max_queries

    async def run(self, state: ClinicalState) -> Dict:
        questions = state.get("clinical_questions", [])
        prompt = f"""你是循证医学检索规划专家。请根据病例制定主动检索计划。

【病例】
{state.get('case_text', '')}

【结构化信息】
{state.get('context', {})}

【待回答问题】
{questions}

【患者记忆】
{state.get('active_memory', '')}

只输出 JSON：
{{
  "need_retrieve": true,
  "missing_information": ["影响决策但病例中缺失的信息"],
  "tasks": [{{"question": "临床任务", "query": "对应的中英文专业检索式"}}],
  "expanded_queries": ["医学同义词、指南术语或疾病实体扩展查询"],
  "hypothetical_document": "一段用于 HyDE 向量检索的可能相关医学描述，不得虚构患者事实"
}}

要求：
- 每个待回答问题至少对应一个检索任务
- 同时覆盖诊断、再灌注指征和关键禁忌证中的相关项
- 查询应包含具体疾病实体、检查或指南术语
- 不给出最终治疗结论"""

        data = None
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是医学检索规划与查询扩展专家。"),
                HumanMessage(content=prompt),
            ])
            data = parse_json_output(getattr(response, "content", ""), None)
        except Exception as exc:
            logger.warning("检索规划失败，使用临床问题回退: %s", exc)

        if not isinstance(data, dict):
            data = {}

        tasks = self._normalize_tasks(data.get("tasks"), questions)
        task_queries = [task["query"] for task in tasks]
        expanded = data.get("expanded_queries", [])
        if not isinstance(expanded, list):
            expanded = []
        hypothetical_document = str(data.get("hypothetical_document", "") or "").strip()
        queries = self._build_queries(task_queries + expanded, hypothetical_document)

        missing = data.get("missing_information", [])
        if not isinstance(missing, list):
            missing = []

        return {
            "retrieval_tasks": tasks,
            "retrieval_queries": queries,
            "retrieved_queries": [],
            "hypothetical_document": hypothetical_document,
            "missing_information": [str(item).strip() for item in missing if str(item).strip()],
            "need_retrieve": bool(data.get("need_retrieve", True) and queries),
            "retrieval_round": 0,
            "evidence_quality": 0.0,
            "evidence_assessment": "等待证据检索与质量评估",
        }

    @staticmethod
    def _normalize_tasks(raw_tasks, questions: List[str]) -> List[Dict[str, str]]:
        tasks = []
        if isinstance(raw_tasks, list):
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "") or "").strip()
                query = str(item.get("query", "") or "").strip()
                if query:
                    tasks.append({"question": question or query, "query": query})
        if tasks:
            return tasks
        return [
            {"question": str(question), "query": str(question)}
            for question in questions
            if str(question).strip()
        ]

    @staticmethod
    def _unique(values: List[str]) -> List[str]:
        result = []
        seen = set()
        for value in values:
            text = str(value or "").strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _build_queries(self, regular_queries: List[str], hypothetical_document: str) -> List[str]:
        """为 HyDE 文档固定保留一个检索槽位，避免被普通扩展查询挤出。"""
        regular = self._unique(regular_queries)
        if not hypothetical_document:
            return regular[:self.max_queries]

        hyde = hypothetical_document.strip()
        if hyde.casefold() in {query.casefold() for query in regular}:
            return regular[:self.max_queries]

        regular_limit = max(self.max_queries - 1, 0)
        return regular[:regular_limit] + ([hyde] if self.max_queries > 0 else [])
