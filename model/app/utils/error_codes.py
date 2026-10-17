

# 错误码与异常分类(阶段7 脱敏): 把运行期异常映射为对外错误码, 不向客户端暴露内部细节。
import asyncio
import traceback
from datetime import datetime, timezone
from enum import Enum


# 对外错误码枚举: 值为 (错误码, 默认提示, 是否可重试)
class ModelErrorCode(Enum):
    E1001 = ("E1001", "推理超时, 已达 120s 上限", True)
    E1002 = ("E1002", "模型拒绝回答", False)
    E1003 = ("E1003", "模型内存不足 (OOM)", True)
    E1004 = ("E1004", "模型服务限流, 请稍后重试", True)
    E1099 = ("E1099", "未知错误", False)

    def __init__(self, code: str, default_message: str, retryable: bool):
        self.code = code
        self.default_message = default_message
        self.retryable = retryable


# 按异常类型/消息关键词归类: 超时→E1001, OOM→E1003, 安全拒答关键词→E1002, 限流→E1004, 其余→E1099
def classify_exception(exc: Exception) -> ModelErrorCode:
    if isinstance(exc, asyncio.TimeoutError):
        return ModelErrorCode.E1001
    if isinstance(exc, MemoryError):
        return ModelErrorCode.E1003
    exc_msg = str(exc).lower()
    if any(kw in exc_msg for kw in ("safety", "sensitive", "违禁", "安全拒绝", "内容违规")):
        return ModelErrorCode.E1002
    # 限流: 如阿里云百炼 429 limit_requests / openai SDK RateLimitError, 明确提示稍后重试
    if type(exc).__name__ == "RateLimitError" or any(
        kw in exc_msg for kw in ("rate limit", "limit_requests", "too many requests", "请求过于频繁")
    ):
        return ModelErrorCode.E1004
    return ModelErrorCode.E1099


def build_error_event(exc: Exception, talk_id=None) -> dict:
    """构建对外错误事件(阶段7: 脱敏, 不向客户端暴露内部异常细节)。

    客户端只见错误码与通用提示; 完整异常由调用方记录在服务端日志。
    """
    error_code = classify_exception(exc)
    message = error_code.default_message
    return {
        "type": "error",
        "talkId": talk_id,
        "content": message,
        "error": {
            "code": error_code.code,
            "message": message,
            "retryable": error_code.retryable,
            "detail": message,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
    }


# 拼接完整异常信息(类型/消息/堆栈), 供服务端日志记录(不对外返回)
def format_error_log(exc: Exception) -> str:
    return (
        f"异常类型: {type(exc).__name__} | "
        f"消息: {exc} | "
        f"堆栈:\n{traceback.format_exc()}"
    )
