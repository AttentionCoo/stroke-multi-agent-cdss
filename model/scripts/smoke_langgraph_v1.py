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


if __name__ == "__main__":
    asyncio.run(check_astream())
    check_event_handlers()
    print("ALL PASS")
