"""脑卒中医疗工具注册表与执行器

聚合所有领域工具,提供:
- 工具列表(schema 形式,供 LLM bind_tools 与 API 展示)
- 按名称调用工具(供独立 API 与 LangGraph ToolNode 使用)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.tools import BaseTool, StructuredTool

from app.agents.tools.contraindications import CONTRAINDICATION_TOOLS
from app.agents.tools.scales import SCALE_TOOLS
from app.agents.tools.subtype import SUBTYPE_TOOLS
from app.agents.tools.thrombolysis import THROMBOLYSIS_TOOLS

logger = logging.getLogger(__name__)

# 全部工具
TOOLS: List[BaseTool] = (
    SCALE_TOOLS + THROMBOLYSIS_TOOLS + CONTRAINDICATION_TOOLS + SUBTYPE_TOOLS
)

# 名称 → 工具
TOOL_MAP: Dict[str, BaseTool] = {tool.name: tool for tool in TOOLS}

# 按类别分组(用于 API 展示与文档)
TOOL_GROUPS: Dict[str, List[str]] = {
    "量表评估": [t.name for t in SCALE_TOOLS],
    "溶栓治疗": [t.name for t in THROMBOLYSIS_TOOLS],
    "禁忌症检查": [t.name for t in CONTRAINDICATION_TOOLS],
    "诊断分型": [t.name for t in SUBTYPE_TOOLS],
}


def get_all_tools() -> List[BaseTool]:
    """返回全部工具对象(供 LLM bind_tools / ToolNode)。"""
    return list(TOOLS)


def get_tool_schemas() -> List[Dict[str, Any]]:
    """返回工具的 OpenAI 风格 schema 列表(供 API 展示)。"""
    schemas = []
    for tool in TOOLS:
        schema = tool.args_schema.model_json_schema() if tool.args_schema else {}
        schemas.append(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            }
        )
    return schemas


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """按名称调用工具。

    Args:
        name: 工具名(如 nihss_score)
        arguments: 工具参数 dict

    Returns:
        统一包装的结果:{"tool": name, "ok": bool, "result": ...} 或错误信息
    """
    tool = TOOL_MAP.get(name)
    if tool is None:
        return {
            "ok": False,
            "tool": name,
            "error": f"未知工具: {name}",
            "available": sorted(TOOL_MAP.keys()),
        }
    try:
        # 日志脱敏:patient_info 可能含病史/检查等敏感信息,仅记录非敏感字段
        log_args = {
            k: (str(v)[:60] + "…" if k == "patient_info" and len(str(v)) > 60 else v)
            for k, v in arguments.items()
        }
        logger.info(f"[tools] 调用工具 {name}, 参数: {log_args}")
        result = tool.invoke(arguments)
        return {"ok": True, "tool": name, "result": result}
    except Exception as e:  # noqa: BLE001 - 工具边界统一兜底
        logger.error(f"[tools] 工具 {name} 调用失败: {e}")
        # 参数校验错误脱敏:只保留字段与约束类型,不暴露输入值与堆栈
        from pydantic import ValidationError

        if isinstance(e, ValidationError):
            brief = "; ".join(
                f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('type', 'invalid')}"
                for err in e.errors()
            )
            error_msg = f"参数校验失败: {brief or str(e)}"
        else:
            error_msg = str(e)
        return {
            "ok": False,
            "tool": name,
            "error": error_msg,
            "hint": "请检查参数是否符合工具 schema",
        }


__all__ = [
    "TOOLS",
    "TOOL_MAP",
    "TOOL_GROUPS",
    "get_all_tools",
    "get_tool_schemas",
    "call_tool",
]
