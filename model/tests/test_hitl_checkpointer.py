"""阶段3 HITL + Checkpointer 测试(离线: sqlite 检查点 + interrupt/resume 往返)。

运行: pytest tests/test_hitl_checkpointer.py -v
"""
import sys
import os

import pytest

sys.path.insert(0, ".")

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END, START
from langgraph.types import interrupt, Command

from app.agents.orchestrators.clinical_graph import ClinicalGraphBuilder
from app.agents.orchestrators.checkpoint import build_checkpointer, open_checkpointer, prune_stale_threads


# ── 最小图: interrupt → resume 往返(Sqlite 持久化检查点) ──

class _MiniState(TypedDict):
    approved: bool
    step: str


def _build_mini_graph():
    g = StateGraph(_MiniState)

    def review(state):
        decision = interrupt({"question": "是否批准?"})
        return {"approved": bool(decision.get("approved", False)), "step": "reviewed"}

    def final(state):
        return {"step": "final"}

    g.add_node("review", review)
    g.add_node("final", final)
    g.add_edge(START, "review")
    g.add_edge("review", "final")
    g.add_edge("final", END)
    return g


@pytest.mark.asyncio
async def test_sqlite_interrupt_resume_roundtrip(tmp_path, monkeypatch):
    path = str(tmp_path / "cp.sqlite")
    monkeypatch.setenv("CHECKPOINTER_PATH", path)
    saver = await open_checkpointer()
    assert type(saver).__name__ == "AsyncSqliteSaver"
    graph = _build_mini_graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "t1"}}

    events = []
    async for _mode, chunk in graph.astream(
        {"approved": False, "step": ""}, config=cfg, stream_mode=["updates"]
    ):
        events.append(chunk)
    # 首次运行: 在 review 节点 interrupt 挂起
    assert any("__interrupt__" in c for c in events)
    assert not any("final" in c for c in events)

    # 恢复: Command(resume=...) 注入医生决定
    events2 = []
    async for _mode, chunk in graph.astream(
        Command(resume={"approved": True}), config=cfg, stream_mode=["updates"]
    ):
        events2.append(chunk)
    assert any("final" in c for c in events2)

    # 检查点持久化可读
    snap = await graph.aget_state(cfg)
    assert snap.values["approved"] is True
    assert snap.values["step"] == "final"

    # 线程删除(推理完成后的清理路径)
    await saver.adelete_thread("t1")
    snap2 = await graph.aget_state(cfg)
    assert snap2.values == {}


@pytest.mark.asyncio
async def test_sqlite_interrupt_reject_and_retry(tmp_path, monkeypatch):
    """驳回 → 状态持久化, 支持多轮复核。"""
    path = str(tmp_path / "cp2.sqlite")
    monkeypatch.setenv("CHECKPOINTER_PATH", path)
    saver = await open_checkpointer()
    graph = _build_mini_graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "t2"}}

    async for _mode, chunk in graph.astream(
        {"approved": False, "step": ""}, config=cfg, stream_mode=["updates"]
    ):
        pass
    async for _mode, chunk in graph.astream(
        Command(resume={"approved": False}), config=cfg, stream_mode=["updates"]
    ):
        pass
    snap = await graph.aget_state(cfg)
    assert snap.values["approved"] is False


# ── ClinicalGraphBuilder: 复核节点与路由逻辑 ──

class _DummyNode:
    async def run(self, state):
        return {}


def _make_builder():
    return ClinicalGraphBuilder(
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


def test_graph_builds_with_human_review_node():
    builder = _make_builder()
    graph = builder.build()
    nodes = getattr(graph, "nodes", {})
    assert "human_review" in nodes
    assert "validate" in nodes


@pytest.mark.asyncio
async def test_human_review_passthrough_when_not_required():
    builder = _make_builder()
    r = await builder._human_review_node({"human_review_required": False})
    assert r == {"human_review_done": True}
    assert builder._route_review({"human_review_required": False}) == "report"


@pytest.mark.asyncio
async def test_human_review_reject_feeds_back_and_retries():
    builder = _make_builder()
    state = {
        "human_review_required": True,
        "review_decision": {"approved": False, "feedback": "请补充CTA评估"},
        "consensus": "共识文本", "proposal": "方案文本",
        "key_risks": [], "validation_feedback": "",
        "review_count": 0,
    }
    r = await builder._human_review_node(state)
    assert r["review_approved"] is False
    assert r["review_feedback"] == "请补充CTA评估"
    assert r["validation_feedback"] == "请补充CTA评估"
    assert r["review_count"] == 1
    # 未达上限 → 重新会诊
    assert builder._route_review({"human_review_required": True, "review_approved": False, "review_count": 1}) == "reason"
    # 达上限 → 强制生成报告(流程必须终止)
    assert builder._route_review({"human_review_required": True, "review_approved": False, "review_count": 2}) == "report"
    # 批准 → 生成报告
    assert builder._route_review({"human_review_required": True, "review_approved": True}) == "report"


# ── checkpointer 构建与环境解析 ──

def test_build_checkpointer_falls_back_to_memory(monkeypatch):
    monkeypatch.delenv("CHECKPOINTER_PATH", raising=False)
    saver = build_checkpointer()
    assert saver is not None
    assert type(saver).__name__ == "InMemorySaver"


@pytest.mark.asyncio
async def test_open_checkpointer_sqlite_and_prune(tmp_path, monkeypatch):
    path = str(tmp_path / "cp.sqlite")
    monkeypatch.setenv("CHECKPOINTER_PATH", path)
    saver = await open_checkpointer()
    assert type(saver).__name__ == "AsyncSqliteSaver"
    assert os.path.exists(path)
    # 空库清理不报错
    assert prune_stale_threads(path) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
