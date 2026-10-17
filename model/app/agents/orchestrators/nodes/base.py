"""节点基类与通用工具函数。

- astream_text: 流式调用 LLM 并把增量文本写入 LangGraph custom 流(思考链实时打印);
- make_structured_runner / try_get_stream_writer: 结构化输出与流写入器工具, 不可用时静默降级;
- BaseNode: 所有编排节点的抽象基类, 约定 run(state) -> 状态更新字典。
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from app.agents.core.schema import ClinicalState

logger = logging.getLogger(__name__)


def _extract_content(obj) -> str:
    """从 LLM 消息/chunk 对象中提取文本内容(兼容 str 与 content block 列表)。"""
    c = getattr(obj, "content", "") or ""
    if isinstance(c, list):
        # OpenAI 兼容协议返回 content block 列表时拼接文本
        c = "".join(str(getattr(b, "text", "") or "") for b in c)
    return str(c or "")


async def astream_text(llm, messages, label: str, expert: str | None = None) -> str:
    """astream 调用 LLM, 并把增量文本实时写入 LangGraph custom 流(思考链实时打印)。

    - label: 节点名(前端按节点分组实时渲染)
    - expert: 可选专家标签(reason/debate 等多专家节点用于区分发言者)
    - 流式协议异常(如 DeepSeek 流式解析错乱)时自动回退非流式调用,
      保证专家意见等关键内容不因流式传输错误而整体丢失
    """
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
    except Exception:  # 节点被脱离图直接调用(如单元测试)时无 writer, 静默降级
        writer = None

    parts: List[str] = []
    try:
        async for chunk in llm.astream(messages):
            c = _extract_content(chunk)
            if c:
                parts.append(c)
                if writer is not None:
                    payload: Dict[str, Any] = {"node": label, "chunk": c}
                    if expert:
                        payload["expert"] = expert
                    writer(payload)
    except Exception as exc:
        logger.warning(
            "[astream_text] 流式调用失败(%s), 回退非流式: label=%s", type(exc).__name__, label
        )
        try:
            resp = await llm.ainvoke(messages)
            c = _extract_content(resp)
            if c and writer is not None:
                payload = {"node": label, "chunk": c}
                if expert:
                    payload["expert"] = expert
                writer(payload)
            return c
        except Exception as exc2:
            logger.error("[astream_text] 非流式回退也失败: %s", exc2)
            raise
    # 返回累计的完整文本(供调用方作为节点最终输出), 同时已实时写入 custom 流
    return "".join(parts)


def make_structured_runner(llm, schema):
    """构建结构化输出 Runner(阶段3); 不可用时返回 None, 调用方回退文本解析路径。

    - Mock 对象(unittest.mock)与不具备 with_structured_output 的伪 LLM → None;
    - with_structured_output 构建失败(如 provider 不支持) → None;
    - DeepSeek 不支持 json_schema 响应格式(400 response_format unavailable),
      自动改用 json_mode(json_object): schema 注入提示词, 输出由 langchain 解析回结构体。
    """
    if llm is None:
        return None
    if type(llm).__name__ == "Mock":  # 单元测试的 Mock LLM: 所有属性都存在但无真实语义
        return None
    if not hasattr(llm, "with_structured_output"):
        return None
    try:
        base_url = str(
            getattr(llm, "openai_api_base", "") or getattr(llm, "base_url", "") or ""
        )
        if "deepseek" in base_url.lower():
            return llm.with_structured_output(schema, method="json_mode")
        return llm.with_structured_output(schema)
    except Exception:
        return None


def try_get_stream_writer():
    """获取 LangGraph 流写入器(脱离图运行/测试时返回 None)。"""
    try:
        from langgraph.config import get_stream_writer
        return get_stream_writer()
    except Exception:
        return None


# 所有图节点的统一入口: 子类实现 run(), 返回部分状态更新字典供 LangGraph 合并
class BaseNode(ABC):
    """节点基类"""

    @abstractmethod
    async def run(self, state: ClinicalState) -> Dict[str, Any]:
        """
        执行节点逻辑

        参数:
            state: 当前状态

        返回:
            状态更新字典
        """
        pass
