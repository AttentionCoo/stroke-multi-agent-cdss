"""临床决策规划节点测试(mock LLM,无需真实 API)

运行: pytest tests/test_decision_planner.py -v
"""
import sys
import json

import pytest

sys.path.insert(0, ".")

from app.agents.orchestrators.nodes.research_node import ResearchPlanNode


class _FakeLLM:
    _content = json.dumps({
        "need_retrieve": True,
        "missing_information": ["血小板计数", "CTA结果"],
        "clinical_decisions": [
            {"decision_name": "是否机械取栓", "decision_type": "treatment",
             "patient_evidence": ["NIHSS 16"], "uncertainty": ["CTA闭塞"],
             "required_evidence": ["EVT指南"], "priority": 9},
            {"decision_name": "是否静脉溶栓", "decision_type": "treatment",
             "patient_evidence": ["发病90分钟"], "uncertainty": ["血小板"],
             "required_evidence": ["AHA指南"], "priority": 10},
            {"decision_name": "TOAST分型", "decision_type": "etiology",
             "patient_evidence": ["房颤史"], "uncertainty": [],
             "required_evidence": ["TOAST标准"], "priority": 5},
        ],
        "retrieval_tasks": [{"question": "是否溶栓", "query": "acute ischemic stroke IV alteplase guideline 4.5h"}],
        "expanded_queries": ["thrombolysis window"],
        "hypothetical_document": "疑似急性缺血性卒中患者时间窗内评估",
    })

    async def ainvoke(self, messages):
        return type("R", (), {"content": self._content})

    async def astream(self, messages):
        yield type("R", (), {"content": self._content})


class _EmptyLLM:
    async def ainvoke(self, messages):
        return type("R", (), {"content": "invalid json"})

    async def astream(self, messages):
        yield type("R", (), {"content": "invalid json"})


_BASE_STATE = {
    "case_text": "男69岁右偏瘫失语NIHSS16发病90分钟",
    "all_info": "", "context": {},
    "clinical_questions": ["是否溶栓"], "active_memory": "",
}


@pytest.mark.asyncio
async def test_decision_planner_generates_schema():
    """决策规划应生成完整 Schema 并按优先级降序。"""
    node = ResearchPlanNode(llm=_FakeLLM())
    result = await node.run(_BASE_STATE)
    decisions = result["clinical_decisions"]
    assert len(decisions) == 3
    for d in decisions:
        assert set(d.keys()) == {
            "decision_id", "decision_name", "decision_type", "patient_evidence",
            "uncertainty", "required_evidence", "evidence_type", "evidence_source",
            "priority", "pico", "search_query",
        }
    prios = [d["priority"] for d in decisions]
    assert prios == sorted(prios, reverse=True)
    # 最高优先级应为溶栓(10)
    assert decisions[0]["decision_name"] == "是否静脉溶栓"


@pytest.mark.asyncio
async def test_decision_planner_routes_evidence_type():
    """evidence_type 应按决策类型路由(treatment/etiology)。"""
    node = ResearchPlanNode(llm=_FakeLLM())
    result = await node.run(_BASE_STATE)
    by_name = {d["decision_name"]: d for d in result["clinical_decisions"]}
    assert by_name["是否静脉溶栓"]["evidence_type"] == "treatment"
    assert by_name["TOAST分型"]["evidence_type"] == "etiology"


@pytest.mark.asyncio
async def test_decision_planner_fallback_on_llm_failure():
    """LLM 返回无效内容时,应从临床问题回退生成诊断决策。"""
    node = ResearchPlanNode(llm=_EmptyLLM())
    state = {**_BASE_STATE, "clinical_questions": ["是否溶栓", "TOAST分型"]}
    result = await node.run(state)
    decisions = result["clinical_decisions"]
    assert len(decisions) == 2
    for d in decisions:
        assert d["decision_type"] == "diagnosis"
        assert d["priority"] == 5
    # 回退时仍应有检索任务
    assert result["retrieval_tasks"]


@pytest.mark.asyncio
async def test_decision_planner_missing_info_passthrough():
    """缺失信息应传递给下游。"""
    node = ResearchPlanNode(llm=_FakeLLM())
    result = await node.run(_BASE_STATE)
    assert "血小板计数" in result["missing_information"]
    assert "CTA结果" in result["missing_information"]
