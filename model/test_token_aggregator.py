# test_token_aggregator.py — TokenAggregator 单元测试
#
# 运行方式：在 model/ 目录下执行 pytest test_token_aggregator.py -v

import time
import pytest
from token_aggregator import TokenAggregator


class TestCountBasedAggregation:
    """场景一：正常聚合（按 token 数量触发）"""

    def test_returns_none_before_threshold(self):
        """未达到 max_tokens 时返回 None"""
        agg = TokenAggregator(max_tokens=3, max_wait_ms=10_000)
        assert agg.add("a") is None
        assert agg.add("b") is None

    def test_flushes_at_max_tokens(self):
        """达到 max_tokens 时自动 flush，返回合并字符串"""
        agg = TokenAggregator(max_tokens=3, max_wait_ms=10_000)
        agg.add("a")
        agg.add("b")
        result = agg.add("c")
        assert result == "abc"

    def test_buffer_cleared_after_count_flush(self):
        """count flush 后缓冲区必须清空"""
        agg = TokenAggregator(max_tokens=2, max_wait_ms=10_000)
        agg.add("x")
        agg.add("y")  # 触发 flush
        # 下一轮重新计数
        assert agg.add("z") is None
        assert agg.flush() == "z"

    def test_multiple_batches(self):
        """连续多批次聚合，每批独立合并"""
        agg = TokenAggregator(max_tokens=2, max_wait_ms=10_000)
        r1 = None
        r2 = None
        for i, tok in enumerate(["a", "b", "c", "d"]):
            result = agg.add(tok)
            if i == 1:
                r1 = result
            if i == 3:
                r2 = result
        assert r1 == "ab"
        assert r2 == "cd"


class TestTimeBasedAggregation:
    """场景二：超时刷新（按时间触发）"""

    def test_time_triggers_flush_on_next_add(self):
        """超过 max_wait_ms 后，下一次 add 触发 flush"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=50)
        agg.add("x")
        time.sleep(0.06)          # 超过 50ms
        result = agg.add("y")     # 此时距上次 flush > 50ms，触发
        assert result == "xy"

    def test_no_flush_within_window(self):
        """在时间窗口内连续 add，不触发 flush"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=200)
        # 快速连续 add，不超时
        for tok in ["a", "b", "c"]:
            result = agg.add(tok)
            assert result is None

    def test_buffer_cleared_after_time_flush(self):
        """time flush 后缓冲区必须清空"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=30)
        agg.add("p")
        time.sleep(0.04)
        agg.add("q")              # 触发 time flush
        # 此后缓冲区为空（q 已包含在合并结果中）
        assert agg.flush() is None


class TestForceFlusBeforeDone:
    """场景三：done/error 前强制刷新"""

    def test_flush_returns_buffered_content(self):
        """flush() 返回缓冲区中未达触发条件的剩余内容"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=10_000)
        agg.add("p")
        agg.add("q")
        result = agg.flush()
        assert result == "pq"

    def test_flush_clears_buffer(self):
        """flush() 后缓冲区必须清空"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=10_000)
        agg.add("a")
        agg.flush()
        assert agg._buffer == []

    def test_double_flush_returns_none(self):
        """连续两次 flush，第二次返回 None"""
        agg = TokenAggregator(max_tokens=100, max_wait_ms=10_000)
        agg.add("x")
        agg.flush()
        assert agg.flush() is None

    def test_flush_empty_buffer_returns_none(self):
        """空缓冲区 flush 返回 None"""
        agg = TokenAggregator(max_tokens=5, max_wait_ms=10_000)
        assert agg.flush() is None

    def test_add_after_flush_starts_new_batch(self):
        """flush 后继续 add，开始新一批次计数"""
        agg = TokenAggregator(max_tokens=2, max_wait_ms=10_000)
        agg.add("a")
        agg.flush()          # 强制 flush
        assert agg.add("b") is None   # 新批次，计数从 1 开始
        assert agg.add("c") == "bc"   # 达到 max_tokens=2 触发
