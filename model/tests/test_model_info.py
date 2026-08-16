"""阶段5 运行时信息端点测试(/model/info, mock 资源, 无需真实 API)。

运行: pytest tests/test_model_info.py -v
"""
import sys
import os
import time

import pytest

sys.path.insert(0, ".")

import app.main as main_mod
from app.main import model_info, resources


@pytest.fixture
def fake_resources(monkeypatch):
    """注入轻量假资源, 并绕过 JWT 校验。"""
    monkeypatch.setattr(main_mod, "verify_token", lambda token: None)
    monkeypatch.setitem(resources, "model", None)
    monkeypatch.setitem(resources, "started_at", time.time() - 125)
    monkeypatch.setitem(resources, "retriever", None)

    class _FakeRouter:
        def info(self):
            return {"main": {"model": "qwen-plus", "request_timeout": 120, "max_retries": 3}}

    monkeypatch.setitem(resources, "model_router", _FakeRouter())
    return monkeypatch


@pytest.mark.asyncio
async def test_model_info_reports_runtime(fake_resources):
    result = await model_info(token="x")
    assert result["code"] == 1
    data = result["data"]
    assert data["models"]["main"]["model"] == "qwen-plus"
    assert data["checkpointer"] == "unknown"  # model=None → 图不存在
    assert data["kb"]["documents"] == 0
    assert data["kb"]["health_warnings"] == []
    assert 120 <= data["uptime_seconds"] <= 130


@pytest.mark.asyncio
async def test_model_info_with_graph_checkpointer(fake_resources):
    class _FakeSaver:
        pass

    class _FakeGraph:
        checkpointer = _FakeSaver()

    class _FakeAgent:
        graph = _FakeGraph()

    fake_resources.setitem(resources, "model", _FakeAgent())
    result = await model_info(token="x")
    assert result["data"]["checkpointer"] == "_FakeSaver"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
