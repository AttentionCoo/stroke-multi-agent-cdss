"""
工具调用节点 - 为临床推理链提供 tool calling 能力

功能说明：
- 在分析病例结构后、规划检索前,让 LLM 通过 function calling 自主选择调用脑卒中医疗工具
- 工具结果(量表评分、剂量、禁忌症、分型)以结构化文本写入 state,供后续推理使用
- 最多进行 max_rounds 轮工具调用,防止失控

设计模式：
- Function Calling 模式：LLM bind_tools 后自主决定调用哪些工具
- 安全兜底模式：工具调用失败不会阻塞主流程,只记录错误
- 有限循环模式：限制最大工具调用轮数
"""

import json
import logging
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)

# 工具调用指令(引导 LLM 在合适的场景使用工具)
_TOOL_USE_PROMPT = """你是脑卒中临床决策支持系统的工具调度员。请仔细阅读以下病例信息,判断需要调用哪些医疗工具来辅助后续的专家推理。

可用工具(按需调用,可调用多个,也可不调用):
- nihss_score / mrs_score / gcs_score:存在神经功能缺损体征时评估量表
- thrombolysis_window_check:存在发病时间信息时判断溶栓时间窗
- rtpa_dose_calc:存在体重信息且涉及溶栓时计算剂量
- contraindication_check:涉及溶栓/抗凝/双抗治疗时检查禁忌症
- toast_classify:存在血管/心脏/影像线索时辅助 TOAST 分型

规则：
1. 只有病例中存在相应信息(体征、时间、体重、治疗意向、影像线索)时才调用工具,不要凭空调用
2. 每次调用只传病例中确实存在的字段
3. 如果信息不足以调用任何工具,直接回答"无需调用工具"

病例：
{case_text}

历史上下文：
{all_info}
"""


class ToolUseNode(BaseNode):
    """
    工具调用节点

    职责：
    - 分析病例中可利用的工具触发信息
    - 通过 LLM function calling 选择并执行工具
    - 将工具结果写入 state 供后续推理节点使用

    输入状态：
    - case_text: 患者病例文本
    - all_info: 历史上下文

    输出状态：
    - tool_results: 工具调用结果的格式化文本(供 reason 等节点注入提示词)
    - tool_calls: 工具调用记录列表(供展示与审计)
    """

    def __init__(
        self,
        llm,
        tools: Optional[List[BaseTool]] = None,
        max_rounds: int = 2,
    ):
        from app.agents.tools.registry import get_all_tools

        self.tools = tools if tools is not None else get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        # bind_tools 使 LLM 具备 function calling 能力
        self.llm = llm.bind_tools(self.tools) if self.tools else llm
        self.max_rounds = max_rounds
        logger.info(f"[tool_use] 已绑定 {len(self.tools)} 个工具, 最大调用轮数: {max_rounds}")
        logger.info(f"[tool_use] 工具列表: {[t.name for t in self.tools]}")

    async def run(self, state: ClinicalState) -> Dict:
        logger.info(f"[tool_use] 开始工具调用节点, 病例长度: {len(state['case_text'])}")

        messages = [
            SystemMessage(
                content="你是一位严谨的工具调度员,只依据病例中真实存在的信息调用工具。"
            ),
            HumanMessage(
                content=_TOOL_USE_PROMPT.format(
                    case_text=state["case_text"],
                    all_info=state.get("all_info", "") or state.get("active_memory", ""),
                )
            ),
        ]

        tool_records: List[Dict] = []
        called_once = False

        for _round in range(self.max_rounds):
            try:
                response = await self.llm.ainvoke(messages)
            except Exception as e:  # noqa: BLE001 - 工具调度失败不阻塞主流程
                logger.error(f"[tool_use] LLM 工具调度失败: {e}")
                break

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                break

            called_once = True
            logger.info(f"[tool_use] 第 {_round + 1} 轮: LLM 请求调用 {len(tool_calls)} 个工具")

            # 将 LLM 的工具调用请求回填到消息历史
            messages.append(
                AIMessage(content="", tool_calls=tool_calls)
            )

            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {}) or {}
                call_id = tc.get("id", "")
                tool = self.tool_map.get(name)

                if tool is None:
                    result = {"error": f"未知工具: {name}", "available": sorted(self.tool_map.keys())}
                else:
                    try:
                        # 日志脱敏:patient_info 可能含敏感病史
                        log_args = {
                            k: (str(v)[:60] + "…" if k == "patient_info" and len(str(v)) > 60 else v)
                            for k, v in args.items()
                        }
                        logger.info(f"[tool_use] 调用工具 {name}, 参数: {log_args}")
                        result = tool.invoke(args)
                    except Exception as e:  # noqa: BLE001 - 单个工具失败不中断
                        logger.error(f"[tool_use] 工具 {name} 执行失败: {e}")
                        result = {"error": str(e)}

                tool_records.append({"tool": name, "arguments": args, "result": result})
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=call_id,
                    )
                )

        if not called_once:
            logger.info("[tool_use] LLM 未调用任何工具(信息不足或无需调用)")

        # 结构化结果文本,供 reason 等节点注入提示词
        if tool_records:
            parts = []
            for i, rec in enumerate(tool_records, 1):
                parts.append(
                    f"【工具调用 {i}】{rec['tool']}\n"
                    f"参数: {json.dumps(rec.get('arguments', {}), ensure_ascii=False)}\n"
                    f"结果: {json.dumps(rec.get('result', {}), ensure_ascii=False)}"
                )
            tool_results_text = "\n\n".join(parts)
        else:
            tool_results_text = ""

        logger.info(f"[tool_use] 工具调用完成, 共 {len(tool_records)} 次调用, 结果长度: {len(tool_results_text)}")

        return {
            "tool_results": tool_results_text,
            "tool_calls": tool_records,
        }
