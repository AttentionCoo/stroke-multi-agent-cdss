"""阶段7 安全合规工具。

- mask_sensitive: 日志脱敏(身份证/手机号/银行卡), 防止患者隐私写入日志;
- RequestConcurrencyGuard: 内存级请求并发闸(单用户 + 全局上限), 防滥用拖垮模型服务。
"""

import re
from typing import Dict

# 18 位身份证(含末位 X)、15 位旧身份证、11 位手机号、16-19 位银行卡
# 边界用数字 lookaround 而非 \b: Python re 的 \w 含中文, 中文字符旁 \b 不成立
_ID_CARD_18 = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_ID_CARD_15 = re.compile(r"(?<!\d)\d{6}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")


def mask_sensitive(text: str) -> str:
    """把常见个人敏感信息替换为掩码, 供日志输出前调用。"""
    if not text:
        return text
    masked = _ID_CARD_18.sub("身份证号[已脱敏]", text)
    masked = _ID_CARD_15.sub("身份证号[已脱敏]", masked)
    masked = _PHONE.sub("手机号[已脱敏]", masked)
    masked = _BANK_CARD.sub("银行卡号[已脱敏]", masked)
    return masked


class RequestConcurrencyGuard:
    """单事件循环内的并发计数器(无 await 的检查-递增是原子的, 无需锁)。"""

    def __init__(self, per_user_limit: int = 2, global_limit: int = 8):
        self.per_user_limit = max(1, int(per_user_limit))
        self.global_limit = max(1, int(global_limit))
        self._counts: Dict[str, int] = {}
        self._total = 0

    def try_acquire(self, key: str) -> bool:
        """尝试占用一个并发名额, 成功返回 True(必须配 release)。"""
        if self._total >= self.global_limit:
            return False
        if self._counts.get(key, 0) >= self.per_user_limit:
            return False
        self._total += 1
        self._counts[key] = self._counts.get(key, 0) + 1
        return True

    def release(self, key: str):
        """释放一个并发名额(与 try_acquire 成功一一对应)。"""
        if self._counts.get(key, 0) <= 1:
            self._counts.pop(key, None)
        else:
            self._counts[key] -= 1
        self._total = max(0, self._total - 1)

    def active(self) -> int:
        """当前在途请求数(供 /model/info 展示)。"""
        return self._total
