import asyncio
import os
import sys
from unittest.mock import Mock

import pytest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vision_service import VisionAnalysisService, _STREAM_DONE


@pytest.mark.asyncio
async def test_vision_failure_event_is_marked():
    prompt_manager = Mock()
    prompt_manager.get.return_value = None
    service = VisionAnalysisService(prompt_manager)

    def fail_stream(messages, queue, loop):
        del messages
        asyncio.run_coroutine_threadsafe(queue.put(RuntimeError("模拟失败")), loop).result()
        asyncio.run_coroutine_threadsafe(queue.put(_STREAM_DONE), loop).result()

    service._run_sync_stream = fail_stream

    events = [
        event
        async for event in service.analyze_stream(
            images=["base64-image"],
            question="请分析图片",
            all_info="",
        )
    ]

    assert events[0]["type"] == "thinking"
    assert events[1]["type"] == "chunk"
    assert events[1]["failed"] is True
    assert "图片分析失败" in events[1]["content"]
