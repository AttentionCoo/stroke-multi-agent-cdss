import os
import sys

import pytest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import health_check, resources


@pytest.mark.asyncio
async def test_health_check_reports_starting_before_model_ready(monkeypatch):
    """模型未就绪时必须返回 503(让 docker healthcheck/depends_on 真正等待就绪)。"""
    monkeypatch.setitem(resources, "model", None)

    result = await health_check()

    assert result.status_code == 503
    body = result.body.decode("utf-8") if isinstance(result.body, bytes) else str(result.body)
    assert '"status":"starting"' in body
    assert '"model_loaded":false' in body


@pytest.mark.asyncio
async def test_health_check_reports_ready_after_model_loaded(monkeypatch):
    monkeypatch.setitem(resources, "model", object())

    result = await health_check()

    assert result.status_code == 200
    body = result.body.decode("utf-8") if isinstance(result.body, bytes) else str(result.body)
    assert '"status":"ready"' in body
    assert '"model_loaded":true' in body
