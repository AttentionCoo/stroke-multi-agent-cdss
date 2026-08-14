"""零成本冒烟验证: LangGraph 1.x astream(updates+messages) 契约 + QwenAgent 事件翻译逻辑。

不调用任何 LLM API, 仅验证:
1. astream 双流模式在 langgraph 1.2.11 可用, 产出 (mode, payload) 元组
2. _on_node_updates / _on_message_chunk 的事件映射与旧 astream_events 行为一致
"""
import asyncio
import sys
from typing import TypedDict

from langgraph.graph import StateGraph, END, START

sys.path.insert(0, ".")
from app.agents.orchestrators.qwen_agent import QwenAgent, _NODE_DISPLAY


class FakeChunk:
    def __init__(self, content):
        self.content = content


class State(TypedDict, total=False):
    x: int
    report: str
    tool_calls: list


def node_a(state):
    return {"x": 1}


def node_report(state):
    return {"report": "报告内容"}


def node_tool(state):
    return {"tool_calls": [{"tool": "nihss_score", "arguments": {"score": 12}, "result": {"level": "moderate"}}]}


def build_graph():
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_node("tool_use", node_tool)
    g.add_node("generate_report", node_report)
    g.add_edge(START, "a")
    g.add_edge("a", "tool_use")
    g.add_edge("tool_use", "generate_report")
    g.add_edge("generate_report", END)
    return g.compile()


async def check_astream():
    app = build_graph()
    seen_modes = set()
    async for mode, chunk in app.astream({"x": 0}, stream_mode=["updates", "messages"]):
        seen_modes.add(mode)
        if mode == "updates":
            assert isinstance(chunk, dict), f"updates 应为 dict, 得到 {type(chunk)}"
            print(f"  updates: {list(chunk.keys())}")
        else:
            assert isinstance(chunk, tuple) and len(chunk) == 2, "messages 应为 (chunk, metadata)"
            print(f"  messages: node={chunk[1].get('langgraph_node')}")
    assert "updates" in seen_modes, "updates 流未产出"
    print("PASS astream 契约")


def check_event_handlers():
    agent = object.__new__(QwenAgent)  # 绕过 __init__, 不触碰 LLM
    agent._live_buffers = {}
    started, streamed = set(), set()

    # 节点完成 → node_start + node_done (+tool_call 展开)
    events = agent._on_node_updates(
        {"tool_use": {"tool_calls": [{"tool": "nihss_score", "arguments": {}, "result": {}}]}},
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    types = [e["type"] for e in events]
    assert types[0] == "node_start" and types[1] == "node_done" and "tool_call_0" in [e.get("node") for e in events], types
    print("  tool_use 事件:", types, [e.get("node") for e in events])

    # 流式 token → 首次 node_start + token
    events = agent._on_message_chunk(
        (FakeChunk("片段1"), {"langgraph_node": "generate_report"}),
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    assert [e["type"] for e in events] == ["node_start", "token"], events
    # 后续 token 不再重复 node_start
    events = agent._on_message_chunk(
        (FakeChunk("片段2"), {"langgraph_node": "generate_report"}),
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    assert [e["type"] for e in events] == ["token"], events

    # 非流式节点回退 token(reject 路径)
    events = agent._on_node_updates(
        {"reject": {"report": "与脑卒中无关"}},
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    assert [e["type"] for e in events] == ["node_start", "node_done", "token"], [e["type"] for e in events]

    # content block 列表拼接
    events = agent._on_message_chunk(
        (FakeChunk([type("B", (), {"text": "a"}), type("B", (), {"text": "b"})]), {"langgraph_node": "knowledge_answer"}),
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    assert events[-1]["content"] == "ab", events

    # 非展示节点 token 忽略
    events = agent._on_message_chunk(
        (FakeChunk("x"), {"langgraph_node": "analysis"}),
        show_thinking=True, started_nodes=started, streamed_nodes=streamed,
    )
    assert events == []
    print("PASS 事件翻译逻辑")


def check_full_content():
    """零成本验证: 所有节点的全文渲染均有内容且不截断。"""
    agent = object.__new__(QwenAgent)
    samples = {
        "intent": {"intent_type": "consultation", "type": "consultation"},
        "memory": {"patient_memory": {"short_term": "会话摘要", "episodic": "历史事件", "semantic": "稳定病史"}, "active_memory": "激活上下文全文"},
        "analysis": {"complexity": "high", "key_risks": ["血压偏高"], "clinical_questions": ["是否溶栓"], "structured_context": {"主诉": "左侧肢体无力3小时"}},
        "tool_use": {"tool_calls": [{"tool": "nihss_score", "arguments": {"items": [1, 2]}, "result": {"level": "moderate"}}]},
        "research_plan": {"need_retrieve": True, "clinical_decisions": [{"priority": 10, "decision_name": "是否溶栓"}], "retrieval_queries": ["rt-PA 禁忌"], "missing_information": ["INR"]},
        "evidence_router": {"router_routes": [{"evidence_type": "treatment", "categories": ["指南"]}], "router_keywords": ["溶栓"]},
        "retrieve": {"retrieval_round": 1, "evidence": "【证据 R1-Q1-E1】内容"},
        "evidence_judge": {"evidence_quality": 0.9, "need_retrieve": False, "evidence_assessment": "证据充分"},
        "query_rewrite": {"retrieval_queries": ["重写查询"], "need_retrieve": True},
        "reason": {"expert_opinions": {"全科医生": "意见A", "神经专科医生": "意见B", "临床药师": "意见C"}},
        "debate": {"debate_transcript": "质询全文"},
        "consensus_agent": {"consensus": "共识", "proposal": "方案", "critique": "风险审查"},
        "validate": {"validation_passed": True, "reflection_count": 1, "validation_feedback": "反馈全文"},
        "generate_report": {"report": "这是一份完整的临床报告内容测试文本"},
        "knowledge_answer": {"report": "这是一份完整知识回答内容测试文本"},
        "reject": {"report": "与脑卒中无关"},
    }
    for node, output in samples.items():
        content = agent._node_full_content(node, output)
        assert content and len(content) > 10, f"{node} 全文渲染为空: {content!r}"
        print(f"  {node}: {len(content)} 字符 -> {content.splitlines()[0][:40]}")
    # evidence_router 必须在展示表中(所有过程都要打印)
    assert "evidence_router" in _NODE_DISPLAY, "evidence_router 缺少展示配置"
    print("PASS 全节点全文渲染")


def check_live_stream():
    """零成本验证: custom 流实时快照(node_token)逻辑。"""
    agent = object.__new__(QwenAgent)
    agent._live_buffers = {}
    started = set()

    # 单节点自定义流: 首次补 node_start, 快照逐段累积
    events = agent._on_custom_event({"node": "analysis", "chunk": "片段一"}, True, started)
    assert [e["type"] for e in events] == ["node_start", "node_token"], events
    assert events[-1]["content"] == "片段一"
    events = agent._on_custom_event({"node": "analysis", "chunk": "片段二"}, True, started)
    assert len(events) == 1 and events[0]["type"] == "node_token"
    assert events[0]["content"] == "片段一片段二", events[0]["content"]

    # 专家标签: reason 节点三位专家各自累积
    agent._on_custom_event({"node": "reason", "chunk": "意见A", "expert": "全科医生"}, True, started)
    events = agent._on_custom_event({"node": "reason", "chunk": "意见B", "expert": "神经专科医生"}, True, started)
    content = events[-1]["content"]
    assert "【全科医生】" in content and "【神经专科医生】" in content, content

    # tuple 形式兼容与未知节点忽略
    events = agent._on_custom_event(({"node": "debate", "chunk": "质询"}, {}), True, started)
    assert events and events[-1]["type"] == "node_token"
    assert agent._on_custom_event({"node": "nope", "chunk": "x"}, True, started) == []

    # 节点完成后清缓冲, 反思回环重新积累
    agent._live_buffers.pop("analysis", None)
    events = agent._on_custom_event({"node": "analysis", "chunk": "新一轮"}, True, started)
    assert events[-1]["content"] == "新一轮", events[-1]["content"]
    print("PASS 实时流(custom)处理")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(check_astream())
    check_event_handlers()
    check_full_content()
    check_live_stream()
    print("ALL PASS")
