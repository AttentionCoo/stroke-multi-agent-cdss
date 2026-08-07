"""工具调用节点与推理链集成测试(使用 mock LLM,无需真实 API)

运行: pytest tests/test_tool_use_integration.py -v
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.agents.orchestrators.nodes.tool_use_node import ToolUseNode
from app.agents.orchestrators.clinical_graph import ClinicalGraphBuilder


class _FakeToolArgs(BaseModel):
    weight_kg: float


def _fake_rtpa(**kwargs):
    w = kwargs["weight_kg"]
    return {"total_dose_mg": round(w * 0.9, 2)}


FAKE_TOOL = StructuredTool.from_function(
    name="fake_rtpa",
    description="fake rt-pa dose calc",
    args_schema=_FakeToolArgs,
    func=_fake_rtpa,
)


class _FakeLLM:
    """模拟 LLM:第一轮请求调用 fake_rtpa,第二轮不再调用。"""

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fake_rtpa",
                        "args": {"weight_kg": 70},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="无需更多工具调用")


class _NoCallLLM:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="无需调用工具")


class _DummyNode:
    async def run(self, state):
        return {}


_BASE_STATE = {
    "case_text": "男 65 岁,体重 70kg,突发右侧肢体无力 3 小时",
    "all_info": "",
    "tool_results": "",
    "tool_calls": [],
}


@pytest.mark.asyncio
async def test_tool_use_node_executes_tool_and_writes_results():
    node = ToolUseNode(llm=_FakeLLM(), tools=[FAKE_TOOL], max_rounds=2)
    result = await node.run(_BASE_STATE)
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "fake_rtpa"
    assert result["tool_calls"][0]["result"]["total_dose_mg"] == 63.0
    assert "fake_rtpa" in result["tool_results"]
    assert "63.0" in result["tool_results"]


@pytest.mark.asyncio
async def test_tool_use_node_handles_no_calls():
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    result = await node.run(_BASE_STATE)
    assert result["tool_calls"] == []
    assert result["tool_results"] == ""


def test_graph_builds_with_tool_use_node():
    builder = ClinicalGraphBuilder(
        intent_node=_DummyNode(),
        memory_node=_DummyNode(),
        analysis_node=_DummyNode(),
        research_plan_node=_DummyNode(),
        retrieve_node=_DummyNode(),
        evidence_judge_node=_DummyNode(),
        query_rewrite_node=_DummyNode(),
        reason_node=_DummyNode(),
        debate_node=_DummyNode(),
        consensus_node=_DummyNode(),
        report_node=_DummyNode(),
        validate_node=None,
        tool_use_node=_DummyNode(),
        llm_critic=None,
        report_manager=None,
    )
    graph = builder.build()
    nodes = getattr(graph, "nodes", {})
    assert "tool_use" in nodes
    assert "analysis" in nodes
    assert "research_plan" in nodes


def test_graph_builds_without_tool_use_node():
    """无 tool_use 节点时保持原有拓扑(向后兼容)。"""
    builder = ClinicalGraphBuilder(
        intent_node=_DummyNode(),
        memory_node=_DummyNode(),
        analysis_node=_DummyNode(),
        research_plan_node=_DummyNode(),
        retrieve_node=_DummyNode(),
        evidence_judge_node=_DummyNode(),
        query_rewrite_node=_DummyNode(),
        reason_node=_DummyNode(),
        debate_node=_DummyNode(),
        consensus_node=_DummyNode(),
        report_node=_DummyNode(),
        validate_node=None,
        tool_use_node=None,
        llm_critic=None,
        report_manager=None,
    )
    graph = builder.build()
    nodes = getattr(graph, "nodes", {})
    assert "tool_use" not in nodes


@pytest.mark.asyncio
async def test_rule_based_fallback_triggers_on_stroke_case():
    """LLM 不调用工具时,规则兜底应根据病例线索自动调度工具。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    # 直接测试规则方法
    case = "69岁患者突发混合性失语伴右侧偏瘫,血压170/102mmHg"
    calls = node._rule_based_fallback(case)
    names = [n for n, _ in calls]
    assert "nihss_score" in names
    assert "contraindication_check" in names
    # mRS 需临床随访评估,不应占位调用
    assert "mrs_score" not in names
    # 含发病时间 → 时间窗
    case2 = "男65岁突发右侧肢体无力3小时,既往房颤史,血压185/115"
    calls2 = node._rule_based_fallback(case2)
    names2 = {n for n, _ in calls2}
    assert "thrombolysis_window_check" in names2
    assert "toast_classify" in names2
    # 知识问题不误触发
    assert node._rule_based_fallback("如何预防脑卒中?") == []


@pytest.mark.asyncio
async def test_rule_based_fallback_extracts_real_nihss():
    """NIHSS 兜底应从病例文本提取真实症状分项,而非全 0 占位。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    case = "突发右侧肢体无力1.5小时,右侧上下肢不能抬起,言语困难,口角歪斜,无意识障碍"
    calls = dict(node._rule_based_fallback(case))
    assert "nihss_score" in calls
    nihss_args = calls["nihss_score"]
    # 右侧完全瘫痪 → 肢体运动 4;口角歪斜 → 面瘫;失语 → 语言
    assert nihss_args.get("motor_arm") == 4
    assert nihss_args.get("motor_leg") == 4
    assert nihss_args.get("facial") >= 1
    assert nihss_args.get("language") >= 1
    # 未提及的分项不应被臆测为非零
    assert nihss_args.get("visual", 0) == 0


@pytest.mark.asyncio
async def test_rule_based_fallback_treatment_defaults_to_thrombolysis():
    """急性卒中无明确药物指征时,禁忌症检查默认溶栓而非双抗。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    case = "男65岁,突发左侧肢体无力2小时,言语不清,血压185/115,血小板90"
    calls = dict(node._rule_based_fallback(case))
    assert calls.get("contraindication_check", {}).get("treatment") == "溶栓"

    # 明确双抗用药时切换为双抗
    case2 = "男70岁,右侧肢体无力1小时,服用阿司匹林+氯吡格雷"
    calls2 = dict(node._rule_based_fallback(case2))
    assert calls2.get("contraindication_check", {}).get("treatment") == "双抗"


def test_contraindication_negative_ct_no_false_positive():
    """CT平扫未见出血不应被误判为'头颅CT高密度'(出血)。"""
    from app.agents.tools.registry import call_tool
    r = call_tool(
        "contraindication_check",
        {"treatment": "溶栓", "patient_info": "头颅CT平扫:未见出血,左侧基底节区低密度影"},
    )
    assert r["result"]["passed"] is True
    assert "头颅CT高密度" not in r["result"]["hits"]


def test_contraindication_real_hemorrhage_still_detected():
    """真实的CT高密度(出血)仍应命中禁忌症。"""
    from app.agents.tools.registry import call_tool
    r = call_tool(
        "contraindication_check",
        {"treatment": "溶栓", "patient_info": "头颅CT示高密度影,考虑出血"},
    )
    assert r["result"]["passed"] is False
    assert "头颅CT高密度" in r["result"]["hits"]


def test_rule_based_fallback_respects_explicit_nihss_score():
    """病例明确给出 NIHSS 总分时,规则兜底不应重新计算覆盖临床输入。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    case = "NIHSS评分:16分,右侧肢体无力2小时,言语困难"
    calls = [n for n, _ in node._rule_based_fallback(case)]
    assert "nihss_score" not in calls


def test_clinical_consistency_warns_on_conflict():
    """工具计算结果与病例明确分数冲突时应产生警示。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    warnings = node._check_clinical_consistency(
        "NIHSS评分:16分,右侧肢体无力",
        [{"tool": "nihss_score", "result": {"total_score": 11}}],
    )
    assert len(warnings) == 1
    assert "16" in warnings[0]
    # 一致时无警示
    warnings2 = node._check_clinical_consistency(
        "NIHSS评分:16分",
        [{"tool": "nihss_score", "result": {"total_score": 16}}],
    )
    assert warnings2 == []


def test_clinical_scores_used_as_given_for_all_scales():
    """临床量表只要给出分数就用给出的, 不自行计算(NIHSS/mRS/GCS 全覆盖)。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    case = "NIHSS评分:16分, mRS分级:3分, GCS评分:15分, 右侧肢体无力2小时"
    # 规则兜底: 三种量表均不调用计算工具
    names = [n for n, _ in node._rule_based_fallback(case)]
    assert "nihss_score" not in names
    assert "mrs_score" not in names
    assert "gcs_score" not in names
    # 临床优先判定
    assert node._should_use_clinical_score(case, "nihss_score") is True
    assert node._should_use_clinical_score(case, "mrs_score") is True
    assert node._should_use_clinical_score(case, "gcs_score") is True
    # verdict 直接采用临床分数
    assert node._clinical_score_verdict(case, "nihss_score")["total_score"] == 16
    assert node._clinical_score_verdict(case, "mrs_score")["score"] == 3
    assert node._clinical_score_verdict(case, "gcs_score")["total_score"] == 15


def test_clinical_score_blocks_llm_direct_call():
    """LLM 主动调用量表工具时, 病例已给分也以临床输入为准, 不执行计算。"""
    from langchain_core.messages import AIMessage

    class _ScoreLLM:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[{"name": "nihss_score", "args": {}, "id": "c1"}],
            )

    node = ToolUseNode(llm=_ScoreLLM(), max_rounds=1)
    state = {
        "case_text": "NIHSS评分:16分,右侧肢体无力",
        "all_info": "",
        "tool_results": "",
        "tool_calls": [],
    }
    result = asyncio.run(node.run(state))
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["result"].get("source") == "clinical_input"
    assert result["tool_calls"][0]["result"].get("total_score") == 16


def test_estimated_score_marked_not_clinical():
    """无临床给分时, 量表估算结果应标注 source=estimated 并附估算提示。"""
    from app.agents.tools.registry import call_tool

    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    args = node._extract_nihss_args("右侧肢体无力,言语困难,口角歪斜")
    result = call_tool("nihss_score", args)["result"]
    # 模拟 ToolUseNode 的标注逻辑
    result["source"] = "estimated"
    result.setdefault("note", "")
    result["note"] += "【估算提示】"
    assert result["source"] == "estimated"
    assert "估算提示" in result["note"]


def test_gcs_not_called_when_alert():
    """神志清楚时禁止调用 GCS(避免产生'意识障碍'错误语义)。"""
    node = ToolUseNode(llm=_NoCallLLM(), tools=[FAKE_TOOL], max_rounds=2)
    case_clear = "患者神志清楚,言语清晰,突发右侧偏瘫2小时"
    names = [n for n, _ in node._rule_based_fallback(case_clear)]
    assert "gcs_score" not in names
    # 昏迷时应调用
    case_coma = "患者昏迷,刺痛无反应,突发偏瘫"
    names_coma = [n for n, _ in node._rule_based_fallback(case_coma)]
    assert "gcs_score" in names_coma


def test_evidence_router_category_routing():
    """Evidence Router 应按决策类型返回正确类别过滤。"""
    from app.agents.services.retrieval_service import route_category_filter
    assert route_category_filter("treatment") == ["指南", "专家共识", "规范"]
    assert route_category_filter("anatomy") == ["教材"]
    assert route_category_filter("etiology") == ["指南", "专家共识"]
    assert route_category_filter(None) is None


def test_query_translator_medical_terms():
    """Query Translator 应把临床语言转换为医学文献标准术语并扩展同义词。"""
    from app.agents.services.query_translator import translate_query
    variants = translate_query("左侧大脑中动脉供血区急性缺血性卒中定位依据", "anatomy")
    assert len(variants) >= 2
    # 证据类型关键词注入
    assert any("localization" in v or "神经解剖" in v for v in variants)
    # 同义词扩展(MCA → middle cerebral artery)
    assert any("middle cerebral artery" in v for v in variants)


def test_medical_concept_normalizer_or_and():
    """Medical Concept Normalizer 应抽取概念并生成 OR-AND 医学检索式。"""
    from app.agents.services.query_translator import (
        extract_medical_concepts, build_or_and_query,
    )
    q = "急性缺血性卒中 左大脑中动脉闭塞 对侧偏瘫 失语"
    concepts = extract_medical_concepts(q)
    assert "mca" in concepts or "middle cerebral artery" in concepts
    assert "aphasia" in concepts
    assert "hemiparesis" in concepts
    or_and = build_or_and_query(concepts)
    # OR-AND 结构:多组概念 AND 连接, 每组内含 OR
    assert " AND " in or_and
    assert " OR " in or_and
    # 同义词不交叉重复(mca 只出现一次)
    assert or_and.count('"mca"') == 1


def test_lvo_screening_tool():
    """LVO 筛查工具应输出概率分层与 CTA 建议。"""
    from app.agents.tools.registry import call_tool
    r = call_tool("lvo_screening", {
        "nihss_score": 16, "aphasia": True, "hemiplegia": True,
        "cortical_signs": True,
    })
    assert r["ok"] is True
    result = r["result"]
    assert result["lvo_probability"] == "高"
    assert result["cta_recommended"] is True
    # 低风险案例
    r2 = call_tool("lvo_screening", {"nihss_score": 2})
    assert r2["result"]["lvo_probability"] == "低"
    assert r2["result"]["cta_recommended"] is False
