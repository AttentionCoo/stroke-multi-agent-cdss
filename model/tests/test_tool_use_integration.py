"""工具调用节点与推理链集成测试(使用 mock LLM,无需真实 API)

运行: pytest tests/test_tool_use_integration.py -v
"""
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
