"""阶段3 结构化输出测试(Schema 校验 + 节点快路径/回退路径, mock LLM, 无需真实 API)。

运行: pytest tests/test_structured_outputs.py -v
"""
import sys
import json

import pytest
from pydantic import ValidationError

sys.path.insert(0, ".")

from app.agents.schemas import (
    IntentResult, EvidenceRoute, EvidenceRoutes, ResearchPlanResult,
    DecisionItem, RetrievalTask, HumanReviewDecision,
)
from app.agents.orchestrators.nodes.intent_node import IntentNode
from app.agents.orchestrators.nodes.evidence_router_node import EvidenceRouterNode
from app.agents.orchestrators.nodes.research_node import ResearchPlanNode


# ── Schema 校验 ──

def test_intent_schema_rejects_invalid_literal():
    with pytest.raises(ValidationError):
        IntentResult(type="bogus")
    r = IntentResult(type="consultation", reason="含患者细节")
    assert r.type == "consultation"


def test_human_review_decision_defaults():
    d = HumanReviewDecision(approved=True)
    assert d.approved is True
    assert d.feedback == ""


def test_research_plan_result_dumps_clean():
    plan = ResearchPlanResult(
        need_retrieve=True,
        missing_information=["血小板计数"],
        clinical_decisions=[DecisionItem(decision_name="是否静脉溶栓", priority=10)],
        retrieval_tasks=[RetrievalTask(question="是否溶栓", query="alteplase stroke guideline")],
    )
    data = plan.model_dump()
    assert data["clinical_decisions"][0]["decision_name"] == "是否静脉溶栓"
    assert data["retrieval_tasks"][0]["query"].startswith("alteplase")


# ── IntentNode: 结构化快路径 + 回退路径 ──
# 注: IntentNode 构造时会把 llm 接进 LangChain 管道, 伪 LLM 必须是 callable 或 Runnable

class _StructuredIntentLLM:
    """with_structured_output 可用: 返回合法 IntentResult。"""

    def __call__(self, messages):
        return '{"type": "consultation", "reason": "fallback-not-used"}'

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return IntentResult(type="consultation", reason="含患者具体细节")


class _BadStructuredLLM:
    """with_structured_output 可用但输出不合法: 应回退文本解析路径。"""

    def __call__(self, messages):
        return '{"type": "knowledge", "reason": "通用知识问题"}'

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return {"type": "unexpected-shape"}


class _NoStructuredLLM:
    """无 with_structured_output: 直接走文本解析路径。"""

    def __call__(self, messages):
        return '{"type": "irrelevant"}'


@pytest.mark.asyncio
async def test_intent_structured_fast_path():
    node = IntentNode(llm=_StructuredIntentLLM())
    result = await node.run({"case_text": "69岁男性突发右侧偏瘫1小时"})
    assert result["intent_type"] == "consultation"


@pytest.mark.asyncio
async def test_intent_falls_back_when_structured_invalid():
    node = IntentNode(llm=_BadStructuredLLM())
    result = await node.run({"case_text": "什么是脑卒中?"})
    assert result["intent_type"] == "knowledge"


@pytest.mark.asyncio
async def test_intent_legacy_path_without_structured():
    node = IntentNode(llm=_NoStructuredLLM())
    result = await node.run({"case_text": "今天天气如何"})
    assert result["intent_type"] == "irrelevant"


# ── EvidenceRouterNode: 结构化快路径 ──

class _StructuredRouterLLM:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return EvidenceRoutes(routes=[
            EvidenceRoute(query="是否静脉溶栓", evidence_type="treatment",
                          target_categories=["指南", "专家共识"], keywords=["alteplase"]),
            EvidenceRoute(query="左MCA定位", evidence_type="anatomy",
                          target_categories=["教材"], keywords=["MCA syndrome"]),
        ])

    async def astream(self, messages):
        if False:
            yield None


@pytest.mark.asyncio
async def test_evidence_router_structured_path():
    node = EvidenceRouterNode(llm=_StructuredRouterLLM())
    state = {
        "retrieval_queries": ["是否静脉溶栓", "左MCA定位"],
        "clinical_decisions": [],
    }
    r = await node.run(state)
    assert r["router_evidence_types"] == ["treatment", "anatomy"]
    assert r["router_categories"][0] == ["指南", "专家共识"]
    assert r["router_categories"][1] == ["教材"]
    assert r["router_keywords"][0] == ["alteplase"]


# ── ResearchPlanNode: 结构化快路径 ──

class _StructuredPlanLLM:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return ResearchPlanResult(
            need_retrieve=True,
            missing_information=["血小板计数", "CTA结果"],
            clinical_decisions=[
                DecisionItem(decision_name="是否机械取栓", decision_type="treatment",
                             patient_evidence=["NIHSS 16"], uncertainty=["CTA闭塞"],
                             required_evidence=["EVT指南"], priority=9),
                DecisionItem(decision_name="是否静脉溶栓", decision_type="treatment",
                             patient_evidence=["发病90分钟"], uncertainty=["血小板"],
                             required_evidence=["AHA指南"], priority=10),
                DecisionItem(decision_name="TOAST分型", decision_type="etiology",
                             patient_evidence=["房颤史"], priority=5),
            ],
            retrieval_tasks=[RetrievalTask(
                question="是否溶栓", query="acute ischemic stroke IV alteplase guideline 4.5h")],
            expanded_queries=["thrombolysis window"],
            hypothetical_document="疑似急性缺血性卒中患者时间窗内评估",
        )

    async def astream(self, messages):
        if False:
            yield None


_BASE_STATE = {
    "case_text": "男69岁右偏瘫失语NIHSS16发病90分钟",
    "all_info": "", "context": {},
    "clinical_questions": ["是否溶栓"], "active_memory": "",
}


@pytest.mark.asyncio
async def test_decision_planner_structured_path():
    node = ResearchPlanNode(llm=_StructuredPlanLLM())
    result = await node.run(_BASE_STATE)
    decisions = result["clinical_decisions"]
    assert len(decisions) == 3
    prios = [d["priority"] for d in decisions]
    assert prios == sorted(prios, reverse=True)
    assert decisions[0]["decision_name"] == "是否静脉溶栓"
    by_name = {d["decision_name"]: d for d in decisions}
    assert by_name["TOAST分型"]["evidence_type"] == "etiology"
    assert "血小板计数" in result["missing_information"]
    assert result["retrieval_queries"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
