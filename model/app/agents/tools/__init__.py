"""脑卒中医疗工具包

为系统提供可独立调用、也可接入 LLM tool calling 的脑卒中领域工具:
- 量表评估:NIHSS / mRS / GCS
- 溶栓治疗:时间窗判断、rt-PA 剂量计算
- 禁忌症检查:复用 rules_config.yaml 规则
- 诊断分型:TOAST 分型辅助

使用方式:
    from app.agents.tools.registry import get_all_tools, call_tool
"""
from app.agents.tools.registry import (
    TOOLS,
    TOOL_GROUPS,
    TOOL_MAP,
    call_tool,
    get_all_tools,
    get_tool_schemas,
)

__all__ = [
    "TOOLS",
    "TOOL_GROUPS",
    "TOOL_MAP",
    "call_tool",
    "get_all_tools",
    "get_tool_schemas",
]
