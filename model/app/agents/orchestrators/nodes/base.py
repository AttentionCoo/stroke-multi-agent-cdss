from abc import ABC, abstractmethod
from typing import Dict, Any, List
from app.agents.core.schema import ClinicalState


async def astream_text(llm, messages, label: str, expert: str | None = None) -> str:
    """astream 调用 LLM, 并把增量文本实时写入 LangGraph custom 流(思考链实时打印)。

    - label: 节点名(前端按节点分组实时渲染)
    - expert: 可选专家标签(reason/debate 等多专家节点用于区分发言者)
    """
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
    except Exception:  # 节点被脱离图直接调用(如单元测试)时无 writer, 静默降级
        writer = None

    parts: List[str] = []
    async for chunk in llm.astream(messages):
        c = getattr(chunk, "content", "") or ""
        if isinstance(c, list):
            # OpenAI 兼容协议返回 content block 列表时拼接文本
            c = "".join(str(getattr(b, "text", "") or "") for b in c)
        if c:
            parts.append(str(c))
            if writer is not None:
                payload: Dict[str, Any] = {"node": label, "chunk": str(c)}
                if expert:
                    payload["expert"] = expert
                writer(payload)
    return "".join(parts)


class BaseNode(ABC):
    """节点基类"""

    @abstractmethod
    async def run(self, state: ClinicalState) -> Dict[str, Any]:
        """
        执行节点逻辑

        Args:
            state: 当前状态

        Returns:
            状态更新字典
        """
        pass
