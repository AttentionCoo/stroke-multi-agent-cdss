"""合规审计节点测试(纯规则, 无需真实 API)。

运行: pytest tests/test_compliance_node.py -v
"""
import sys

import pytest

sys.path.insert(0, ".")

from app.agents.orchestrators.nodes.compliance_node import ComplianceNode, DISCLAIMER
from app.agents.orchestrators.clinical_graph import ClinicalGraphBuilder


def _state(**overrides):
    base = {
        "consensus": "",
        "proposal": "",
        "critique": "",
        "tool_results": "",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_compliance_passes_clean_draft():
    node = ComplianceNode()
    state = _state(
        consensus="建议尽快评估再灌注指征, 结合时间窗与影像结果个体化决策。",
        proposal="疑似急性缺血性卒中, 建议神经内科急会诊。",
        critique="注意鉴别出血性卒中, 完善影像检查。",
    )
    result = await node.run(state)
    assert result["compliance_passed"] is True
    assert result["compliance_issues"] == []
    assert result["compliance_audit"]["disclaimer"] == DISCLAIMER


@pytest.mark.asyncio
async def test_compliance_detects_phi():
    node = ComplianceNode()
    state = _state(consensus="联系电话13812345678, 身份证110101199003074518, 建议溶栓评估。")
    result = await node.run(state)
    assert result["compliance_passed"] is False
    issues = "".join(result["compliance_issues"])
    assert "PHI" in issues
    assert "手机号" in issues or "身份证" in issues
    # 审计日志字段完整
    assert result["compliance_audit"]["phi"]


@pytest.mark.asyncio
async def test_compliance_flags_certainty():
    node = ComplianceNode()
    state = _state(proposal="该患者100%是脑梗死, 必定需要溶栓。")
    result = await node.run(state)
    assert result["compliance_passed"] is False
    assert any("绝对化断言" in issue for issue in result["compliance_issues"])


@pytest.mark.asyncio
async def test_compliance_does_not_flag_absolute_contraindication():
    """'绝对禁忌证'是合法临床术语, 不应被误判为绝对化断言。"""
    node = ComplianceNode()
    state = _state(proposal="rt-PA 绝对禁忌证包括近期颅内手术史; 应评估绝对适应证后个体化决策。")
    result = await node.run(state)
    assert result["compliance_passed"] is True
    assert result["compliance_issues"] == []


@pytest.mark.asyncio
async def test_compliance_dose_warning_only():
    """具体剂量为警告级: 不判失败, 但写入提示。"""
    node = ComplianceNode()
    state = _state(proposal="阿替普酶 0.9mg/kg 静脉溶栓。")
    result = await node.run(state)
    assert result["compliance_passed"] is True
    assert result["compliance_warnings"]
    assert any("剂量" in w for w in result["compliance_warnings"])


def test_graph_builds_with_compliance_node():
    class _DummyNode:
        async def run(self, state):
            return {}

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
        validate_node=_DummyNode(),
        tool_use_node=None,
        evidence_router_node=None,
        llm_critic=None,
        report_manager=None,
    )
    graph = builder.build()
    nodes = getattr(graph, "nodes", {})
    assert "compliance" in nodes
    assert "human_review" in nodes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
