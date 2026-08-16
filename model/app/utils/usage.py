"""LLM 用量与成本跟踪(请求级, contextvars 隔离并发请求)。

通过 langchain BaseCallbackHandler 挂到 ChatOpenAI 实例上,
每次 LLM 调用按 API 返回的真实 token_usage 记账, 最后汇总成本估算。
"""
import contextvars
import logging
import time
from typing import Dict

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

# 当前请求的用量记录(contextvars: 并发请求互不干扰)
_current: contextvars.ContextVar = contextvars.ContextVar("llm_request_usage", default=None)

# DashScope 计费参考(元/千token): {model: (输入, 输出)}
PRICING = {
    "qwen-plus": (0.0008, 0.002),
    "qwen-turbo": (0.0003, 0.0006),
    "qwen-max": (0.0024, 0.0096),
}


class RequestUsage:
    """单次请求的 LLM 用量账本。"""

    def __init__(self):
        self.started = time.time()
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.by_model: Dict[str, dict] = {}

    def record(self, model: str, in_tokens: int, out_tokens: int):
        self.calls += 1
        self.input_tokens += int(in_tokens or 0)
        self.output_tokens += int(out_tokens or 0)
        m = self.by_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        m["calls"] += 1
        m["input_tokens"] += int(in_tokens or 0)
        m["output_tokens"] += int(out_tokens or 0)

    def summary(self) -> dict:
        total_cost = 0.0
        for model, m in self.by_model.items():
            p_in, p_out = PRICING.get(model, (0.0008, 0.002))
            m["cost"] = round(m["input_tokens"] / 1000 * p_in + m["output_tokens"] / 1000 * p_out, 4)
            total_cost += m["cost"]
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "by_model": self.by_model,
            "cost": round(total_cost, 4),
            "seconds": round(time.time() - self.started, 1),
        }


def begin_request() -> RequestUsage:
    """请求开始时调用: 建立本请求的用量账本。"""
    usage = RequestUsage()
    _current.set(usage)
    return usage


def end_request() -> dict:
    """请求结束时调用: 返回用量汇总并清理上下文。"""
    usage = _current.get()
    _current.set(None)
    return usage.summary() if usage else {"calls": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}, "cost": 0.0, "seconds": 0.0}


class UsageCallbackHandler(BaseCallbackHandler):
    """挂到 ChatOpenAI 上, 每次 LLM 调用按真实 token_usage 记账。"""

    def on_llm_end(self, response, **kwargs) -> None:
        usage = _current.get()
        if usage is None:
            return
        try:
            in_tokens, out_tokens, model = self._extract_usage(response, kwargs)
            if in_tokens or out_tokens:
                usage.record(model, in_tokens, out_tokens)
        except Exception as e:  # noqa: BLE001 - 记账失败不影响主流程
            logger.debug("用量记账失败: %s", e)

    @staticmethod
    def _extract_usage(response, kwargs):
        """从 LLMResult 提取 (入tokens, 出tokens, 模型名)。

        langchain-core 1.x 下流式/结构化输出路径的 llm_output 可能为 None,
        token 用量改放在 generation.message.usage_metadata(input_tokens/output_tokens),
        因此两条路径都兼容。
        """
        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or {}
        in_tokens = int(token_usage.get("prompt_tokens", 0) or 0)
        out_tokens = int(token_usage.get("completion_tokens", 0) or 0)
        model = str(
            (kwargs.get("invocation_params") or {}).get("model")
            or llm_output.get("model_name")
            or "unknown"
        )

        # llm_output 为空(流式/函数调用路径): 汇总 generations 里的 usage_metadata
        if not in_tokens and not out_tokens:
            for gen_list in getattr(response, "generations", None) or []:
                for gen in gen_list or []:
                    message = getattr(gen, "message", None)
                    meta = getattr(message, "usage_metadata", None) or {}
                    in_tokens += int(meta.get("input_tokens", 0) or 0)
                    out_tokens += int(meta.get("output_tokens", 0) or 0)
                    if model == "unknown":
                        model = str(
                            (getattr(message, "response_metadata", None) or {}).get("model_name", "")
                            or "unknown"
                        )
        return in_tokens, out_tokens, model
