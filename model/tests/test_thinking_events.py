import json
import os
import sys

import pytest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.orchestrators.qwen_agent import QwenAgent


@pytest.fixture
def agent():
    return QwenAgent.__new__(QwenAgent)


def test_node_start_contains_running_status(agent):
    event = {
        "event": "on_chain_start",
        "name": "analysis",
        "metadata": {},
    }

    translated = agent._translate_event(event, True, set())

    assert translated == {
        "type": "node_start",
        "node": "analysis",
        "label": "正在分析病例结构...",
        "status": "running",
    }


@pytest.mark.parametrize(
    ("node", "output", "expected_key", "streamed"),
    [
        ("intent", {"intent_type": "consultation"}, "判断结果", False),
        (
            "analysis",
            {
                "complexity": "critical",
                "key_risks": ["再灌注时间窗紧迫"],
                "clinical_questions": ["是否符合静脉溶栓指征"],
            },
            "检索子问题",
            False,
        ),
        (
            "research_plan",
            {
                "need_retrieve": True,
                "retrieval_tasks": [{"question": "是否符合静脉溶栓"}],
                "retrieval_queries": ["AIS thrombolysis guideline"],
                "missing_information": ["INR"],
            },
            "扩展查询",
            False,
        ),
        (
            "retrieve",
            {"evidence": "指南证据一\n---\n指南证据二"},
            "证据摘要",
            False,
        ),
        (
            "reason",
            {
                "proposal": "建议立即完成卒中绿色通道评估。",
                "critique": "需排除活动性出血。",
                "generalist_advice": "关注生命体征。",
            },
            "综合方案摘要",
            False,
        ),
        (
            "validate",
            {
                "validation_passed": False,
                "validation_feedback": "存在禁忌症冲突。",
                "reflection_count": 1,
            },
            "校验结果",
            False,
        ),
        (
            "consensus_agent",
            {
                "consensus": "先完成影像和凝血评估",
                "proposal": "启动卒中绿色通道",
                "critique": "INR结果缺失",
            },
            "会诊共识",
            False,
        ),
        ("generate_report", {"report": "临床报告正文"}, "报告状态", True),
        ("knowledge_answer", {"report": "知识回答正文"}, "回答状态", True),
    ],
)
def test_node_done_contains_displayable_summary(agent, node, output, expected_key, streamed):
    event = {
        "event": "on_chain_end",
        "name": node,
        "metadata": {},
        "data": {"output": output},
    }

    translated = agent._translate_event(event, True, {node} if streamed else set())

    assert translated["type"] == "node_done"
    assert translated["node"] == node
    assert translated["status"] == "done"
    assert translated["label"]
    assert len(translated["summary"]) <= 1600
    assert expected_key in json.loads(translated["summary"])


def test_reason_summary_limits_long_model_output(agent):
    summary = json.loads(
        agent._node_summary(
            "reason",
            {
                "proposal": "方案" * 1000,
                "critique": "风险" * 1000,
                "specialist_advice": "意见" * 1000,
            },
        )
    )

    assert summary["综合方案摘要"].endswith("...")
    assert summary["风险审查摘要"].endswith("...")
    assert summary["专家意见摘要"]["specialist"].endswith("...")


@pytest.mark.parametrize("node", ["reject", "generate_report", "knowledge_answer"])
def test_non_streaming_answer_emits_done_event_before_token(agent, node):
    event = {
        "event": "on_chain_end",
        "name": node,
        "metadata": {},
        "data": {"output": {"report": "完整回答"}},
    }

    translated = agent._translate_event(event, True, set())

    assert [item["type"] for item in translated] == ["node_done", "token"]
    assert translated[0]["status"] == "done"
    assert translated[1]["content"] == "完整回答"


def test_empty_stream_chunk_keeps_full_answer_fallback(agent):
    chunk = type("Chunk", (), {"content": ""})()
    streamed_nodes = set()

    translated_chunk = agent._translate_event(
        {
            "event": "on_chat_model_stream",
            "name": "ChatOpenAI",
            "metadata": {"langgraph_node": "generate_report"},
            "data": {"chunk": chunk},
        },
        True,
        streamed_nodes,
    )

    assert translated_chunk is None
    assert streamed_nodes == set()

    translated_end = agent._translate_event(
        {
            "event": "on_chain_end",
            "name": "generate_report",
            "metadata": {},
            "data": {"output": {"report": "完整报告"}},
        },
        True,
        streamed_nodes,
    )

    assert streamed_nodes == {"generate_report"}
    assert [item["type"] for item in translated_end] == ["node_done", "token"]
