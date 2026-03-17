# error_codes.py — 模型层结构化错误码定义（对应改进方案 2.3 节）

import asyncio
import traceback
from datetime import datetime, timezone
from enum import Enum


class ModelErrorCode(Enum):
    """
    结构化错误码枚举，每个成员携带 code / default_message / retryable 三个属性。
    错误码范围：E1xxx = Python 模型层
    """
    E1001 = ("E1001", "推理超时, 已达 120s 上限", True)
    E1002 = ("E1002", "模型拒绝回答", False)
    E1003 = ("E1003", "模型内存不足 (OOM)", True)
    E1099 = ("E1099", "未知错误", False)

    def __init__(self, code: str, default_message: str, retryable: bool):
        self.code = code
        self.default_message = default_message
        self.retryable = retryable


def classify_exception(exc: Exception) -> ModelErrorCode:
    """根据异常类型映射到对应错误码"""
    if isinstance(exc, asyncio.TimeoutError):
        return ModelErrorCode.E1001
    if isinstance(exc, MemoryError):
        return ModelErrorCode.E1003
    # 安全/拒绝类：通过消息内容关键词判断（LangChain 无专用异常类）
    exc_msg = str(exc).lower()
    if any(kw in exc_msg for kw in ("safety", "sensitive", "违禁", "安全拒绝", "内容违规")):
        return ModelErrorCode.E1002
    return ModelErrorCode.E1099


def build_error_event(exc: Exception, talk_id=None) -> dict:
    """
    构造结构化错误事件字典。
    双写兼容：保留 content 字段（旧前端读此字段），同时新增 error 对象（新前端/运维）。
    """
    error_code = classify_exception(exc)
    return {
        "type": "error",
        "talkId": talk_id,
        # 过渡期双写：旧前端通过 content 字段获取错误信息
        "content": str(exc),
        # 新增结构化错误对象
        "error": {
            "code": error_code.code,
            "message": error_code.default_message,
            "retryable": error_code.retryable,
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
    }


def format_error_log(exc: Exception) -> str:
    """返回含完整堆栈的日志字符串，供 logger.error 调用"""
    return (
        f"异常类型: {type(exc).__name__} | "
        f"消息: {exc} | "
        f"堆栈:\n{traceback.format_exc()}"
    )
