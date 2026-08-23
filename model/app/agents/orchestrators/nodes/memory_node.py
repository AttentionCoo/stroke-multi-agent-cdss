"""患者分层记忆节点。"""

from typing import Dict

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.text_utils import truncate_text


class MemoryNode(BaseNode):
    """将短期、情景和语义记忆压缩为本轮可用上下文。"""

    # (字段名, 展示标题, 截断上限字符数)：三类记忆按重要度递减分配长度预算
    _SECTIONS = (
        ("short_term", "短期记忆", 2600),
        ("episodic", "情景记忆", 2200),
        ("semantic", "语义记忆", 1600),
    )

    async def run(self, state: ClinicalState) -> Dict:
        """把分层记忆压缩为带标题的本轮可用上下文 active_memory，并回写规范化的 patient_memory。"""
        raw_memory = state.get("patient_memory") or {}
        has_scoped_memory = bool(raw_memory)
        normalized = {
            key: str(raw_memory.get(key, "") or "").strip()
            for key, _, _ in self._SECTIONS
        }
        # 无分层记忆时，用历史上下文 all_info 兜底填充短期记忆，保证下游始终有可用上下文
        if not normalized["short_term"] and not has_scoped_memory:
            normalized["short_term"] = str(state.get("all_info", "") or "").strip()

        sections = []
        for key, title, limit in self._SECTIONS:
            content = truncate_text(normalized[key], limit)
            if content:
                sections.append(f"【{title}】\n{content}")

        return {
            "patient_memory": normalized,
            "active_memory": "\n\n".join(sections) or "无患者历史记忆",
        }
