import os
import sys

import pytest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import health_check, resources


@pytest.mark.asyncio
async def test_health_check_reports_starting_before_model_ready(monkeypatch):
    monkeypatch.setitem(resources, "model", None)

    result = await health_check()

    assert result == {
        "status": "starting",
        "model_loaded": False,
    }


@pytest.mark.asyncio
async def test_health_check_reports_ready_after_model_loaded(monkeypatch):
    monkeypatch.setitem(resources, "model", object())

    result = await health_check()

    assert result == {
        "status": "ready",
        "model_loaded": True,
    }
