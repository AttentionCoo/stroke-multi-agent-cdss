"""工具 API 端点测试(认证 / 错误脱敏)

运行: pytest tests/test_tools_api.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app.main as m


def _client():
    return TestClient(m.app)


def test_list_endpoint_returns_tools():
    r = _client().get("/model/tools/list")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["count"] == 8
    names = {t["name"] for t in data["tools"]}
    assert "nihss_score" in names and "rtpa_dose_calc" in names
    assert "lvo_screening" in names


def test_call_endpoint_without_token_succeeds():
    """token 为空时保持向后兼容(与 pubmed 端点一致)。"""
    r = _client().post(
        "/model/tools/call",
        json={"name": "rtpa_dose_calc", "arguments": {"weight_kg": 70}},
    )
    assert r.status_code == 200
    assert r.json()["data"]["total_dose_mg"] == 63.0


def test_call_endpoint_invalid_token_rejected():
    r = _client().post(
        "/model/tools/call",
        json={
            "name": "rtpa_dose_calc",
            "arguments": {"weight_kg": 70},
            "token": "invalid-token",
        },
    )
    assert r.status_code == 401


def test_call_endpoint_unknown_tool_redacts_details():
    """未知工具的错误响应不暴露内部细节。"""
    r = _client().post(
        "/model/tools/call",
        json={"name": "no_such_tool", "arguments": {}},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["ok"] is False
    assert "no_such_tool" in detail["error"]
    assert "available" in detail


def test_call_endpoint_validation_error_redacted():
    """参数校验失败的内部异常细节不应外泄。"""
    r = _client().post(
        "/model/tools/call",
        json={"name": "rtpa_dose_calc", "arguments": {"weight_kg": -5}},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    # 不包含 pydantic 原始异常串
    assert "validation error" not in str(detail)
