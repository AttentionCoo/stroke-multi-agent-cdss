"""LLM 用量追踪测试(离线: 校验两种 token 提取路径与账本汇总)。

运行: pytest tests/test_usage_tracking.py -v
"""
import sys

import pytest

sys.path.insert(0, ".")

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.utils.usage import RequestUsage, UsageCallbackHandler


def _llm_result(generations=None, llm_output=None):
    return LLMResult(generations=generations or [], llm_output=llm_output)


def test_extract_legacy_llm_output_path():
    """旧版结构: llm_output['token_usage'](prompt/completion_tokens)。"""
    result = _llm_result(llm_output={
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "model_name": "qwen-turbo",
    })
    in_tokens, out_tokens, model = UsageCallbackHandler._extract_usage(
        result, {"invocation_params": {"model": "qwen-turbo"}}
    )
    assert (in_tokens, out_tokens, model) == (10, 20, "qwen-turbo")


def test_extract_usage_metadata_path():
    """langchain-core 1.x 流式/函数调用路径: llm_output=None, token 在 usage_metadata。"""
    message = AIMessage(
        content="回答",
        usage_metadata={"input_tokens": 30, "output_tokens": 40, "total_tokens": 70},
    )
    result = _llm_result(generations=[[ChatGeneration(message=message)]])
    in_tokens, out_tokens, model = UsageCallbackHandler._extract_usage(
        result, {"invocation_params": {"model": "qwen-plus"}}
    )
    assert (in_tokens, out_tokens, model) == (30, 40, "qwen-plus")


def test_extract_multi_generation_sums():
    """多个 generation(并行生成)时应汇总全部 usage_metadata。"""
    g1 = ChatGeneration(message=AIMessage(
        content="a", usage_metadata={"input_tokens": 5, "output_tokens": 6, "total_tokens": 11}))
    g2 = ChatGeneration(message=AIMessage(
        content="b", usage_metadata={"input_tokens": 7, "output_tokens": 8, "total_tokens": 15}))
    result = _llm_result(generations=[[g1, g2]])
    in_tokens, out_tokens, _ = UsageCallbackHandler._extract_usage(
        result, {"invocation_params": {"model": "qwen-plus"}}
    )
    assert in_tokens == 12
    assert out_tokens == 14


def test_extract_empty_result():
    in_tokens, out_tokens, model = UsageCallbackHandler._extract_usage(
        _llm_result(), {"invocation_params": {}}
    )
    assert in_tokens == 0 and out_tokens == 0


def test_request_usage_summary():
    usage = RequestUsage()
    usage.record("qwen-plus", 1000, 500)
    usage.record("qwen-turbo", 100, 50)
    summary = usage.summary()
    assert summary["calls"] == 2
    assert summary["input_tokens"] == 1100
    assert summary["output_tokens"] == 550
    assert summary["cost"] > 0
    assert set(summary["by_model"].keys()) == {"qwen-plus", "qwen-turbo"}
    assert summary["by_model"]["qwen-plus"]["calls"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
