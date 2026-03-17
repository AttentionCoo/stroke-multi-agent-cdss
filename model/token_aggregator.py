# token_aggregator.py — thinking token 聚合器（对应改进方案 3.2 节）
#
# 对高频 thinking token 流进行批量聚合，减少 SSE 事件发送频率。
# 两个触发条件（任一满足即 flush）：
#   1. 缓冲区累积达到 max_tokens 个 token
#   2. 距上次 flush 超过 max_wait_ms 毫秒

import time
from typing import Optional


class TokenAggregator:
    """
    将高频 thinking token 聚合为更大的批次再发出，降低 SSE 事件数量。

    用法::

        agg = TokenAggregator(max_tokens=20, max_wait_ms=100)
        for token in token_stream:
            merged = agg.add(token)
            if merged is not None:
                yield thinking_event(merged)
        # 流结束前强制刷新
        remaining = agg.flush()
        if remaining is not None:
            yield thinking_event(remaining)
    """

    def __init__(self, max_tokens: int = 20, max_wait_ms: int = 100):
        """
        Args:
            max_tokens:  缓冲区内 token 数量阈值，达到即触发 flush
            max_wait_ms: 距上次 flush 的最大等待毫秒数，超时即触发 flush
        """
        self.max_tokens = max_tokens
        self.max_wait = max_wait_ms / 1000.0
        self._buffer: list[str] = []
        self._last_flush: float = time.monotonic()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def add(self, token: str) -> Optional[str]:
        """
        将一个 token 加入缓冲区。
        满足聚合条件时自动 flush，返回合并后的字符串；否则返回 None。

        Args:
            token: 单个 token 字符串（可以是一个字符或一段文字片段）

        Returns:
            聚合后的字符串，或 None（尚未达到触发条件）
        """
        self._buffer.append(token)
        if self._should_flush():
            return self._do_flush()
        return None

    def flush(self) -> Optional[str]:
        """
        强制刷新缓冲区，返回剩余内容。
        应在 done/error 事件 yield 之前调用，确保不丢失任何 thinking 内容。

        Returns:
            缓冲区中剩余内容的聚合字符串；缓冲区为空时返回 None
        """
        if not self._buffer:
            return None
        return self._do_flush()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _should_flush(self) -> bool:
        """检查是否满足任一触发条件"""
        return (
            len(self._buffer) >= self.max_tokens
            or time.monotonic() - self._last_flush >= self.max_wait
        )

    def _do_flush(self) -> str:
        """执行 flush：合并缓冲区、清空、重置计时器，返回合并结果"""
        merged = "".join(self._buffer)
        self._buffer.clear()
        self._last_flush = time.monotonic()
        return merged
