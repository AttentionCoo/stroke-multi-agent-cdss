import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.orchestrators.nodes.debate_node import ConsensusNode, DebateNode
from app.agents.orchestrators.nodes.evidence_node import EvidenceJudgeNode, QueryRewriteNode
from app.agents.orchestrators.nodes.memory_node import MemoryNode
from app.agents.orchestrators.nodes.research_node import ResearchPlanNode
from app.agents.orchestrators.nodes.report_node import ReportNode
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.nodes.validate_node import ValidateNode


def clinical_state(**overrides):
    state = {
        "case_text": "男65岁，突发右侧肢体无力3小时",
        "all_info": "上一轮：患者有高血压病史",
        "patient_memory": {},
        "active_memory": "",
        "context": {"主要症状": ["右侧肢体无力"]},
        "clinical_questions": ["是否符合静脉溶栓指征"],
        "retrieval_tasks": [],
        "retrieval_queries": [],
        "retrieved_queries": [],
        "hypothetical_document": "",
        "need_retrieve": True,
        "evidence": "",
        "evidence_quality": 0.0,
        "evidence_assessment": "",
        "missing_information": [],
        "retrieval_round": 0,
        "expert_opinions": {},
        "debate_transcript": "",
        "consensus": "",
        "validation_feedback": "",
        "reflection_count": 0,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_memory_node_builds_three_level_active_memory():
    node = MemoryNode()
    state = clinical_state(
        patient_memory={
            "short_term": "本次对话：3小时前起病",
            "episodic": "2026-07-20 CTA提示M1闭塞",
            "semantic": "高血压；长期服用华法林",
        }
    )

    result = await node.run(state)

    assert "【短期记忆】" in result["active_memory"]
    assert "【情景记忆】" in result["active_memory"]
    assert "【语义记忆】" in result["active_memory"]
    assert "M1闭塞" in result["active_memory"]


@pytest.mark.asyncio
async def test_scoped_patient_memory_does_not_fall_back_to_unscoped_chat_history():
    node = MemoryNode()
    result = await node.run(
        clinical_state(
            all_info="另一位患者的历史对话",
            patient_memory={
                "short_term": "",
                "episodic": "本患者既往评估",
                "semantic": "本患者高血压病史",
            },
        )
    )

    assert "另一位患者" not in result["active_memory"]
    assert "本患者高血压病史" in result["active_memory"]


@pytest.mark.asyncio
async def test_research_plan_expands_medical_queries_and_hyde_document():
    llm = Mock()
    response = Mock()
    response.content = """{
        "need_retrieve": true,
        "missing_information": ["INR", "CTA"],
        "tasks": [
            {"question": "是否符合静脉溶栓", "query": "2024 AHA AIS thrombolysis guideline"},
            {"question": "是否存在大血管闭塞", "query": "M1 occlusion thrombectomy guideline"}
        ],
        "expanded_queries": ["急性缺血性卒中 静脉溶栓 禁忌证", "MCA M1 闭塞 机械取栓"],
        "hypothetical_document": "急性缺血性卒中再灌注治疗应结合时间窗、影像与禁忌证。"
    }"""
    llm.ainvoke = AsyncMock(return_value=response)

    result = await ResearchPlanNode(llm).run(clinical_state())

    assert result["need_retrieve"] is True
    assert len(result["retrieval_tasks"]) == 2
    assert "2024 AHA AIS thrombolysis guideline" in result["retrieval_queries"]
    assert "MCA M1 闭塞 机械取栓" in result["retrieval_queries"]
    assert result["hypothetical_document"].startswith("急性缺血性卒中")


@pytest.mark.asyncio
async def test_research_plan_reserves_query_slot_for_hyde_document():
    llm = Mock()
    response = Mock()
    response.content = """{
        "need_retrieve": true,
        "tasks": [{"question": "任务", "query": "查询1"}],
        "expanded_queries": ["查询2", "查询3", "查询4", "查询5", "查询6", "查询7", "查询8", "查询9"],
        "hypothetical_document": "HyDE 假设性医学文档"
    }"""
    llm.ainvoke = AsyncMock(return_value=response)

    result = await ResearchPlanNode(llm, max_queries=8).run(clinical_state())

    assert len(result["retrieval_queries"]) == 8
    assert result["retrieval_queries"][-1] == "HyDE 假设性医学文档"


@pytest.mark.asyncio
async def test_retrieve_node_accumulates_evidence_and_tracks_rounds():
    assistant = Mock()
    assistant.afast_parallel_retrieve = AsyncMock(return_value="【证据 R2-Q1-E1】指南新增证据")
    node = RetrieveNode(assistant)
    state = clinical_state(
        retrieval_queries=["alteplase contraindication", "M1 thrombectomy"],
        retrieved_queries=["alteplase contraindication"],
        evidence="【证据 R1-Q1-E1】既有指南证据",
        retrieval_round=1,
    )

    result = await node.run(state)

    assistant.afast_parallel_retrieve.assert_awaited_once_with(
        ["M1 thrombectomy"], round_number=2
    )
    assert result["retrieval_round"] == 2
    assert result["retrieved_queries"] == ["alteplase contraindication", "M1 thrombectomy"]
    assert "既有指南证据" in result["evidence"]
    assert "指南新增证据" in result["evidence"]


@pytest.mark.asyncio
async def test_evidence_judge_requests_another_round_when_no_evidence():
    llm = Mock()
    llm.ainvoke = AsyncMock()
    node = EvidenceJudgeNode(llm, max_rounds=2)

    result = await node.run(clinical_state(retrieval_round=1, evidence=""))

    assert result["need_retrieve"] is True
    assert result["evidence_quality"] == 0.0
    assert result["missing_information"] == ["是否符合静脉溶栓指征"]
    llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_evidence_judge_stops_when_evidence_is_sufficient():
    llm = Mock()
    response = Mock()
    response.content = """{
        "quality": 0.86,
        "is_sufficient": true,
        "missing_information": [],
        "assessment": "关键临床问题均有指南证据覆盖"
    }"""
    llm.ainvoke = AsyncMock(return_value=response)
    node = EvidenceJudgeNode(llm, quality_threshold=0.65, max_rounds=2)

    result = await node.run(
        clinical_state(retrieval_round=1, evidence="【证据 R1-Q1-E1】AHA指南证据")
    )

    assert result["need_retrieve"] is False
    assert result["evidence_quality"] == pytest.approx(0.86)
    assert result["evidence_assessment"] == "关键临床问题均有指南证据覆盖"


@pytest.mark.asyncio
async def test_evidence_judge_retries_conservatively_when_assessment_fails():
    llm = Mock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("审查服务不可用"))
    node = EvidenceJudgeNode(llm, quality_threshold=0.65, max_rounds=2)
    evidence = "\n".join(
        f"【证据 R1-Q{i}-E1】候选片段" for i in range(1, 4)
    )

    result = await node.run(clinical_state(retrieval_round=1, evidence=evidence))

    assert result["evidence_quality"] < 0.65
    assert result["need_retrieve"] is True


@pytest.mark.asyncio
async def test_query_rewrite_uses_missing_information_and_avoids_repeated_queries():
    llm = Mock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("服务不可用"))
    node = QueryRewriteNode(llm)
    state = clinical_state(
        missing_information=["INR禁忌证", "CTA大血管闭塞"],
        retrieved_queries=["INR禁忌证"],
        retrieval_round=1,
    )

    result = await node.run(state)

    assert result["retrieval_queries"] == ["CTA大血管闭塞"]


@pytest.mark.asyncio
async def test_query_rewrite_falls_back_to_clinical_questions_when_gaps_are_empty():
    llm = Mock()
    llm.ainvoke = AsyncMock(return_value=Mock(content='{"queries": []}'))
    node = QueryRewriteNode(llm)

    result = await node.run(
        clinical_state(
            clinical_questions=["是否符合静脉溶栓指征"],
            missing_information=[],
            retrieved_queries=[],
        )
    )

    assert result["need_retrieve"] is True
    assert result["retrieval_queries"] == ["是否符合静脉溶栓指征"]


class FakeExpertManager:
    def get_experts(self):
        return [
            {"role": "神经专科医生", "instruction": "评估再灌注治疗"},
            {"role": "临床药师", "instruction": "评估禁忌证"},
        ]

    def get_synthesis_config(self):
        return {
            "proposal_separator": "### PROPOSAL ###",
            "critique_separator": "### CRITIQUE ###",
        }


@pytest.mark.asyncio
async def test_debate_agents_can_see_peer_opinions_and_evidence():
    llm = Mock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            Mock(content="神经专科回应：同意先核对INR【证据 R1-Q1-E1】"),
            Mock(content="临床药师回应：INR异常时需谨慎【证据 R1-Q1-E1】"),
        ]
    )
    node = DebateNode(llm, FakeExpertManager())
    state = clinical_state(
        evidence="【证据 R1-Q1-E1】指南指出应核对凝血指标",
        user_questions=["该患者是否符合静脉溶栓指征？"],
        expert_opinions={
            "神经专科医生": "建议评估溶栓",
            "临床药师": "需先核对INR",
        },
    )

    result = await node.run(state)

    assert "神经专科医生" in result["debate_transcript"]
    first_prompt = llm.ainvoke.await_args_list[0].args[0][-1].content
    assert "临床药师" in first_prompt
    assert "【证据 R1-Q1-E1】" in first_prompt
    assert "该患者是否符合静脉溶栓指征？" in first_prompt


@pytest.mark.asyncio
async def test_consensus_node_parses_moderator_decision():
    llm = Mock()
    llm.ainvoke = AsyncMock(
        return_value=Mock(
            content=(
                "### CONSENSUS ###\n先完成影像与凝血评估。\n"
                "### PROPOSAL ###\n启动卒中绿色通道【证据 R1-Q1-E1】。\n"
                "### CRITIQUE ###\nINR结果缺失，暂不做确定性判断。"
            )
        )
    )
    node = ConsensusNode(llm, FakeExpertManager())

    result = await node.run(clinical_state(debate_transcript="双方已完成交叉质询"))

    assert result["consensus"] == "先完成影像与凝血评估。"
    assert "【证据 R1-Q1-E1】" in result["proposal"]
    assert "INR结果缺失" in result["critique"]


@pytest.mark.asyncio
async def test_consensus_prompt_keeps_every_original_user_question():
    llm = Mock()
    llm.ainvoke = AsyncMock(
        return_value=Mock(
            content=(
                "### CONSENSUS ###\n需结合禁忌证评估。\n"
                "### PROPOSAL ###\n逐项回答原问题。\n"
                "### CRITIQUE ###\n需人工复核。"
            )
        )
    )
    questions = [
        "该患者目前的诊断是什么？",
        "如果静脉溶栓后症状改善不明显，下一步如何治疗？",
    ]

    await ConsensusNode(llm, FakeExpertManager()).run(
        clinical_state(user_questions=questions, debate_transcript="已完成质询")
    )

    prompt = llm.ainvoke.await_args.args[0][1].content
    assert all(question in prompt for question in questions)
    assert "逐项回答" in prompt


class FakeValidationManager:
    def get_contraindication_rules(self):
        return {"溶栓": ["颅内出血"]}

    def get_max_reflection_count(self):
        return 2

    def is_rule_engine_enabled(self):
        return True

    def is_llm_reflection_enabled(self):
        return False


@pytest.mark.asyncio
async def test_validation_does_not_treat_guideline_text_as_patient_condition():
    node = ValidateNode(Mock(), FakeValidationManager())
    state = clinical_state(
        case_text="男65岁，突发偏瘫3小时，头颅CT未见出血",
        active_memory="高血压病史",
        proposal="建议评估静脉溶栓适应证",
        evidence="【证据 R1-Q1-E1】指南列出颅内出血为溶栓禁忌证",
    )

    assert await node._rule_engine_check(state) == ""


@pytest.mark.asyncio
async def test_validation_keeps_positive_fact_after_an_earlier_negated_fact():
    node = ValidateNode(Mock(), FakeValidationManager())
    state = clinical_state(
        case_text="既往否认颅内出血，本次头颅CT提示颅内出血",
        proposal="建议评估静脉溶栓适应证",
        evidence="",
    )

    feedback = await node._rule_engine_check(state)

    assert "颅内出血" in feedback


@pytest.mark.asyncio
async def test_report_always_prepends_warning_after_validation_exhaustion():
    llm = Mock()

    async def stream(_messages):
        yield Mock(content="## 临床报告\n正文")

    llm.astream = stream
    report_manager = Mock()
    report_manager.system_role = "临床报告生成器"
    report_manager.get_template.return_value = (
        "患者：{context}\n历史：{all_info}\n证据：{evidence}\n"
        "方案：{proposal}\n风险：{critique}"
    )
    node = ReportNode(llm, report_manager)
    state = clinical_state(
        report_mode="emergency",
        user_questions=[],
        proposal="建议进一步评估",
        critique="存在不确定性",
        validation_passed=False,
        validation_feedback="多轮会诊后仍存在禁忌证冲突",
    )

    result = await node.run(state)

    assert result["report"].startswith("## 安全警告")
    assert "多轮会诊后仍存在禁忌证冲突" in result["report"]


@pytest.mark.asyncio
async def test_report_answers_explicit_questions_before_validation_warning():
    captured_messages = []
    llm = Mock()

    async def stream(messages):
        captured_messages.extend(messages)
        yield Mock(
            content=(
                "### 问题1\n考虑急性缺血性脑卒中。\n\n"
                "### 问题2\n符合时间窗，但须先排除禁忌证。\n\n"
                "### 问题3\n溶栓前须先控制血压。\n\n"
                "### 问题4\n应立即衔接血管内治疗评估。"
            )
        )

    llm.astream = stream
    report_manager = Mock()
    report_manager.system_role = "临床报告生成器"
    report_manager.get_template.return_value = (
        "患者：{context}\n历史：{all_info}\n证据：{evidence}\n"
        "方案：{proposal}\n风险：{critique}"
    )
    questions = [
        "该患者目前的诊断是什么？",
        "根据现行指南，该患者是否符合静脉溶栓指征？请说明理由。",
        "针对该患者的血压情况，在启动溶栓前应如何处理？",
        "如果静脉溶栓开始后患者症状改善不明显，下一步的最佳治疗方案是什么？",
    ]
    node = ReportNode(llm, report_manager)
    state = clinical_state(
        report_mode="emergency",
        user_questions=questions,
        proposal="建议评估急性缺血性脑卒中及静脉溶栓适应证",
        critique="需要核对血压与手术史",
        validation_passed=False,
        validation_feedback="REJECT: 血压未达标前不得启动静脉溶栓",
    )

    result = await node.run(state)

    assert captured_messages, "存在明确问题时仍应进入最终答案生成"
    prompt = captured_messages[-1].content
    assert all(question in prompt for question in questions)
    assert "逐项回答" in prompt
    assert result["report"].startswith("### 问题1")
    assert result["report"].index("## 安全警告") > result["report"].index("### 问题4")
