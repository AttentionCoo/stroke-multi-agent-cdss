"""临床决策规划与循证检索节点（Clinical Decision Planner）。

将"生成医学问题→搜索答案"升级为"生成临床决策→判断缺失信息→检索支持决策的证据"。
每个决策携带固定 Schema(decision_name/decision_type/patient_evidence/uncertainty/
required_evidence/priority/evidence_type),并由 Evidence Router 按决策类型路由检索源。
"""

import logging
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.json_utils import parse_json_output


logger = logging.getLogger(__name__)

# 决策类型 → 优先证据源类型（Evidence Router）
EVIDENCE_SOURCE_ROUTING = {
    "treatment": ["临床指南", "RCT", "Meta分析"],
    "diagnosis": ["诊断标准", "系统综述", "临床综述"],
    "anatomy": ["神经解剖教材", "定位参考"],
    "etiology": ["TOAST标准", "诊断指南"],
    "prognosis": ["预后研究", "队列研究", "临床指南"],
    "prevention": ["二级预防指南", "RCT", "临床指南"],
}

# 决策类型默认（未命中时）
DEFAULT_EVIDENCE_TYPE = "treatment"


class ResearchPlanNode(BaseNode):
    """把临床问题拆成决策节点，并生成专业查询与 HyDE 文档。"""

    def __init__(self, llm, max_queries: int = 8, max_decisions: int = 6):
        self.llm = llm
        self.max_queries = max_queries
        self.max_decisions = max_decisions

    async def run(self, state: ClinicalState) -> Dict:
        questions = state.get("clinical_questions", [])
        prompt = f"""你是高级卒中中心临床决策规划专家。你的任务不是回答"患者是什么病"，而是识别"当前医生需要做什么决定、需要什么证据支持这个决定"。

【病例】
{state.get('case_text', '')}

【结构化信息】
{state.get('context', {})}

【待决策方向】
{questions}

【患者记忆】
{state.get('active_memory', '')}

请按临床优先级生成 1-{self.max_decisions} 个临床决策节点，只输出 JSON：
{{
  "need_retrieve": true,
  "missing_information": ["影响决策但病例中缺失的信息"],
  "clinical_decisions": [
    {{
      "decision_id": "AIS_IVT_001",
      "decision_name": "是否进行静脉溶栓(IV thrombolysis)",
      "decision_type": "treatment",
      "patient_evidence": ["病例中支持该决策的事实，如'发病90分钟'"],
      "uncertainty": ["决策关键但病例中缺失/不明确的信息，如'血小板计数'"],
      "required_evidence": ["支持该决策的指南或证据名称，如'AHA卒中指南'"],
      "evidence_type": "treatment",
      "evidence_source": ["AHA guideline", "ESO guideline", "RCT"],
      "priority": 10,
      "pico": {{
        "population": "急性缺血性卒中发病4.5小时内患者",
        "intervention": "阿替普酶静脉溶栓(alteplase IV thrombolysis)",
        "comparison": "不溶栓(no thrombolysis)",
        "outcome": "功能独立/症状性颅内出血(functional independence, symptomatic ICH)"
      }},
      "search_query": [
        "acute ischemic stroke intravenous alteplase within 4.5 hours guideline",
        "AHA ASA guideline alteplase recommendation"
      ]
    }}
  ],
  "retrieval_tasks": [{{"question": "面向该决策的临床问题", "query": "由PICO生成的检索式，如 alteplase acute ischemic stroke within 4.5 hours guideline"}}],
  "expanded_queries": ["医学同义词、指南术语或疾病实体扩展查询"],
  "hypothetical_document": "一段用于 HyDE 向量检索的可能相关医学描述，不得虚构患者事实"
}}

要求：
- decision_type 取值：diagnosis / treatment / anatomy / etiology / prognosis / prevention
- priority：1-10，时间敏感性×生命危险×治疗获益，越紧急越高
- 决策必须按优先级从高到低排列（先再灌注、再LVO评估、再血压/病因、最后定位）
- **定位类决策(anatomy)优先级应低于治疗类**：急诊医生不会因不知道MCA定位而暂停治疗
- patient_evidence 只写病例中真实存在的事实，不得编造检查结果
- uncertainty 必须列出影响该决策的缺失信息
- 每个决策至少对应一个检索任务，查询应包含具体疾病实体、检查或指南术语
- 每个决策必须生成 **PICO 结构化检索式**（Population/Intervention/Comparison/Outcome），
  retrieval_tasks 的 query 由 PICO 生成（英文标准术语），如：
  "alteplase acute ischemic stroke within 4.5 hours guideline"（I 溶栓 + P 卒中 + 时间窗）
- PICO 的 Intervention 与 Outcome 是检索核心词，Population 限定人群（如 AF 相关卒中）
- 每个决策生成 1-2 条 **search_query**（可直接检索的英文专业查询，含疾病实体+干预+时间窗/人群），
  retrieval_tasks 的 query 优先取 search_query；evidence_source 列出证据来源（如 AHA/ESO guideline、RCT）
- 检索任务必须是**临床决策问题**，不是文献性能问题：
  ✅ "对于NIHSS16分伴失语偏瘫的急性卒中患者，是否推荐急诊CTA筛查大血管闭塞？"
  ❌ "CTA/MRA检出前循环LVO的敏感性与特异性是多少？"
- **常识性/已明确的定位问题不需要检索**，可在 retrieval_tasks 中标记 need_retrieve=false
- **禁止从神经定位直接推导病因**：定位证据和病因证据必须分离
  ❌ "失语+偏瘫 → 心源性栓塞"
  ✅ "左MCA综合征 → 需CTA/ECG/Holter/Echo进一步检查 → 再TOAST分类"
- 不给出最终治疗结论"""

        data = None
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是医学临床决策规划与循证检索专家。"),
                HumanMessage(content=prompt),
            ])
            data = parse_json_output(getattr(response, "content", ""), None)
        except Exception as exc:
            logger.warning("决策规划失败，使用临床问题回退: %s", exc)

        if not isinstance(data, dict):
            data = {}

        # 决策节点（决策驱动核心）
        decisions = self._normalize_decisions(data.get("clinical_decisions"), questions)
        clinical_decisions = decisions

        tasks = self._normalize_tasks(data.get("retrieval_tasks"), questions, decisions)
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
            # 临床决策节点（供 reason 等下游节点消费）
            "clinical_decisions": clinical_decisions,
        }

    @staticmethod
    def _normalize_decisions(raw_decisions, questions: List[str]) -> List[Dict]:
        """规范化决策节点，保证 Schema 字段齐全并按优先级排序。"""
        decisions = []
        if isinstance(raw_decisions, list):
            for item in raw_decisions:
                if not isinstance(item, dict):
                    continue
                decision_name = str(item.get("decision_name", "") or "").strip()
                if not decision_name:
                    continue
                decision_type = str(item.get("decision_type", "") or "").strip().lower()
                if decision_type not in EVIDENCE_SOURCE_ROUTING:
                    decision_type = DEFAULT_EVIDENCE_TYPE
                try:
                    priority = int(item.get("priority", 5))
                except (TypeError, ValueError):
                    priority = 5
                decisions.append({
                    "decision_id": str(item.get("decision_id", "") or "").strip(),
                    "decision_name": decision_name,
                    "decision_type": decision_type,
                    "patient_evidence": _as_str_list(item.get("patient_evidence")),
                    "uncertainty": _as_str_list(item.get("uncertainty")),
                    "required_evidence": _as_str_list(item.get("required_evidence")),
                    "evidence_type": str(item.get("evidence_type") or decision_type or DEFAULT_EVIDENCE_TYPE),
                    "evidence_source": _as_str_list(item.get("evidence_source")),
                    "priority": priority,
                    "pico": item.get("pico") if isinstance(item.get("pico"), dict) else {},
                    "search_query": _as_str_list(item.get("search_query")),
                })

        if decisions:
            decisions.sort(key=lambda d: d["priority"], reverse=True)
            return decisions[:6]

        # 回退：将临床问题包装为诊断决策（保证下游可消费）
        return [
            {
                "decision_name": str(question),
                "decision_type": "diagnosis",
                "patient_evidence": [],
                "uncertainty": [],
                "required_evidence": [],
                "evidence_type": "diagnosis",
                "priority": 5,
            }
            for question in questions[:3]
            if str(question).strip()
        ]

    @staticmethod
    def _normalize_tasks(raw_tasks, questions: List[str], decisions: List[Dict]) -> List[Dict[str, str]]:
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
        # 回退：从决策节点生成任务(优先用 search_query, 其次 PICO)
        fallback = []
        for d in decisions:
            if not d.get("decision_name"):
                continue
            queries = d.get("search_query") or []
            if isinstance(queries, list) and queries:
                for q in queries[:2]:
                    fallback.append({"question": d["decision_name"], "query": str(q).strip()})
            else:
                query = _pico_to_query(d.get("pico") or {})
                fallback.append({"question": d["decision_name"], "query": query or d["decision_name"]})
        if fallback:
            return fallback
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


def _as_str_list(value) -> List[str]:
    """将任意值规范化为字符串列表。"""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def _pico_to_query(pico: Dict) -> str:
    """从 PICO 结构生成检索式(intervention + population + outcome 核心词)。"""
    if not isinstance(pico, dict):
        return ""
    parts = []
    for key in ("intervention", "population", "outcome"):
        val = str(pico.get(key, "") or "").strip()
        if not val:
            continue
        # 提取英文核心词(括号内的英文术语优先)
        en = val[val.find("(") + 1:val.find(")")] if "(" in val and ")" in val else ""
        if en and any(c.isascii() and c.isalpha() for c in en):
            parts.append(en.strip())
        else:
            parts.append(val)
    return " ".join(parts) if parts else ""
