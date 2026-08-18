import logging
import json
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode, astream_text
from app.agents.constants import MAX_SUB_QUESTIONS
from app.agents.utils.question_extractor import extract_user_questions

logger = logging.getLogger(__name__)


class AnalysisNode(BaseNode):
    """病例分析节点"""

    def __init__(self, llm):
        self.llm = llm

    async def run(self, state: ClinicalState) -> Dict:
        memory_context = state.get("active_memory") or state.get("all_info", "")
        analysis = await self._unified_analysis(state["case_text"], memory_context)
        clinical_questions = analysis.get("clinical_questions", ["该患者当前最紧急的临床问题和处置要点"])

        # 诊断相关关键词过滤
        _DIAGNOSTIC_KW = {"TOAST", "分型", "病因", "定位", "定性", "鉴别", "卒中类型", "发病机制", "卒中原因"}
        _TREATMENT_KW = {"溶栓", "取栓", "抗凝", "降压", "手术", "时间窗", "剂量", "适应证", "禁忌"}
        if any(kw in state["case_text"] for kw in _DIAGNOSTIC_KW):
            filtered = [q for q in clinical_questions if not any(kw in q for kw in _TREATMENT_KW)]
            if filtered:
                clinical_questions = filtered

        # 用户直接提问(必须命中): LLM 提取优先, 规则兜底保证不遗漏普通问句
        user_questions = analysis.get("user_questions", [])
        if not isinstance(user_questions, list) or not user_questions:
            user_questions = extract_user_questions(state["case_text"])

        return {
            "context": analysis.get("structured_context", {"原始病例": state["case_text"]}),
            "clinical_questions": clinical_questions[:MAX_SUB_QUESTIONS],
            "key_risks": analysis.get("key_risks", []),
            "complexity": analysis.get("complexity", "high"),
            "user_questions": user_questions[:MAX_SUB_QUESTIONS],
        }

    async def _unified_analysis(self, case_text: str, all_info: str) -> Dict[str, Any]:
        """一次 LLM 调用完成病例结构化、子问题生成、关键风险提取"""
        _DIAGNOSTIC_KW = {"TOAST", "分型", "病因", "定位", "定性", "鉴别", "卒中类型", "发病机制", "卒中原因"}
        _TREATMENT_KW = {"溶栓", "取栓", "抗凝", "降压", "手术", "用药", "时间窗", "剂量", "治疗方案"}
        _PROGNOSIS_KW = {"预后", "复发", "康复", "二级预防", "随访", "致残", "死亡率"}

        if any(kw in case_text for kw in _DIAGNOSTIC_KW):
            intent_hint = "诊断/分型方向：重点生成定位、定性、病因分型（TOAST）、鉴别诊断类问题，不生成溶栓/取栓等治疗操作类问题。"
        elif any(kw in case_text for kw in _TREATMENT_KW):
            intent_hint = "治疗决策方向：重点生成治疗方案、禁忌症、时间窗、用药安全性类问题。"
        elif any(kw in case_text for kw in _PROGNOSIS_KW):
            intent_hint = "预后/随访方向：重点生成预后评估、复发风险、二级预防类问题。"
        else:
            intent_hint = "综合分析方向：按临床优先级生成最需查证的问题，优先覆盖诊断，再覆盖治疗。"

        prompt = f"""你是神经急诊专家。请对以下病例完成三项任务，一次性输出。

【病例】
{case_text}

【历史上下文】
{all_info if all_info else "无"}

请直接输出 JSON（不要用 markdown 代码块包裹）：

{{
    "structured_context": {{
        "基本信息": {{"年龄": "", "性别": ""}},
        "起病方式": "",
        "主要症状": [],
        "神经系统查体": {{}},
        "意识水平": "",
        "生命体征": {{}},
        "既往史": [],
        "用药史": [],
        "危险因素": [],
        "非卒中线索": []
    }},
    "complexity": "low/medium/high/critical",
    "key_risks": ["最危险的问题1", "最危险的问题2"],
    "clinical_questions": [
        "服务于用户问题方向的检索子问题1（30字以内）",
        "服务于用户问题方向的检索子问题2",
        "服务于用户问题方向的检索子问题3"
    ],
    "user_questions": [
        "用户直接提出的问题原文(问句), 如'该患者是否需要溶栓?'; 没有提问则返回空列表"
    ]
}}

要求：
- structured_context: 提取所有临床信息
- complexity: critical=危及生命
- clinical_questions: 【重要】{intent_hint} 问题必须用中文，每条30字以内，用于检索医学文献
- user_questions: 【重要】提取用户在本轮输入中直接提出的全部问题——显式编号列表('请回答以下问题：1. xxx 2. yyy')或自然语言问句(以'?'/'？'/'吗'/'呢'结尾, 或以'是否/如何/为什么/能不能'等开头)都算, 逐条原文提取; 若输入只是病例描述而没有提问, 返回空数组。"""

        content = await astream_text(self.llm, [HumanMessage(content=prompt)], label="analysis")
        result = self._parse_json(content, None)

        if result and isinstance(result, dict):
            result.setdefault("user_questions", [])
            return result

        return {
            "structured_context": {"原始病例": case_text},
            "complexity": "high",
            "key_risks": [],
            "clinical_questions": ["该患者当前最紧急的临床问题和处置要点"],
            "user_questions": [],
        }

    def _parse_json(self, text: str, default=None):
        content = (text or "").strip()
        try:
            return json.loads(content)
        except Exception:
            pass
        for marker in ["```json", "```"]:
            if marker in content:
                try:
                    s = content.split(marker)[1].split("```")[0].strip()
                    return json.loads(s)
                except Exception:
                    pass
        for sc, ec in [("{", "}"), ("[", "]")]:
            si, ei = content.find(sc), content.rfind(ec)
            if si != -1 and ei > si:
                try:
                    return json.loads(content[si:ei + 1])
                except Exception:
                    pass
        return default
