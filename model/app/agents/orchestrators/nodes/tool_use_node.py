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
import re
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
            # 规则兜底:根据病例文本中的关键临床线索自动调用工具
            # 避免弱模型漏掉明确存在的评估/检查需求
            fallback_calls = self._rule_based_fallback(state.get("case_text", ""))
            if fallback_calls:
                logger.info(f"[tool_use] 规则兜底触发: 自动调用 {len(fallback_calls)} 个工具")
                for name, args in fallback_calls:
                    tool = self.tool_map.get(name)
                    if tool is None:
                        continue
                    try:
                        result = tool.invoke(args)
                    except Exception as e:  # noqa: BLE001 - 兜底工具失败不中断
                        logger.error(f"[tool_use] 兜底工具 {name} 执行失败: {e}")
                        result = {"error": str(e)}
                    tool_records.append({"tool": name, "arguments": args, "result": result})
                    logger.info(f"[tool_use] 兜底调用 {name}, 参数: {args}")

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

    def _rule_based_fallback(self, case_text: str) -> List[tuple]:
        """
        基于病例文本关键词的规则兜底调度。

        当 LLM 未调用任何工具时,若病例文本命中明确的临床线索,则自动调用对应工具。
        返回 [(工具名, 参数dict), ...]
        """
        text = (case_text or "").strip()
        if not text:
            return []

        calls: List[tuple] = []
        lower = text.lower()

        # 1. 量表评估:NIHSS(神经功能缺损体征)/ GCS(意识障碍)/ mRS
        neuro_signs = ["偏瘫", "无力", "瘫痪", "失语", "言语不清", "构音", "凝视", "面瘫",
                       "麻木", "共济失调", "忽视", "肢体", "numb", "hemiparesis", "aphasia",
                       "hemiplegia", "dysarthria"]
        if any(s in text for s in neuro_signs):
            calls.append(("nihss_score", {}))
            calls.append(("mrs_score", {"score": 0}))  # 占位,由 reason 节点结合整体评估
        if any(s in text for s in ["意识障碍", "昏迷", "嗜睡", "昏睡", "gcs", "格拉斯哥"]):
            calls.append(("gcs_score", {"eye": 4, "verbal": 5, "motor": 6}))  # 占位默认值

        # 2. 溶栓时间窗:出现发病时长描述
        if re.search(r"(\d+(\.\d+)?)\s*(小时|h|hrs?|分钟|min|mins?)", lower) and any(
            s in text for s in ["发病", "起病", "突发", "onset", "起病时间"]
        ):
            # 提取分钟数用于窗口判断
            m = re.search(r"(\d+(\.\d+)?)\s*(小时|h|hrs?|分钟|min|mins?)", lower)
            if m:
                val = float(m.group(1))
                unit = m.group(3)
                minutes = val * 60 if "小时" in unit or unit.startswith("h") else val
                calls.append(("thrombolysis_window_check", {"minutes_from_onset": minutes}))

        # 3. 禁忌症检查:涉及治疗方式关键词,或卒中症状+血压/血小板异常
        treatment_hits = [s for s in ["溶栓", "抗凝", "双抗", "阿替普酶", "rt-pa", "rtpa", "华法林",
                                      "阿司匹林", "氯吡格雷", "thrombolysis", "anticoagul"] if s in text]
        has_stroke_signs = any(s in text for s in neuro_signs) or any(
            s in text for s in ["卒中", "中风", "stroke", "梗死", "缺血"] if s.lower() in lower
        )
        bp_abnormal = re.search(r"血压\s*[=:]?\s*(\d{2,3})\s*[/／]\s*(\d{2,3})", text) or any(
            s in text for s in ["血小板", "出血", "凝血", "血小板低"]
        )
        if treatment_hits or (has_stroke_signs and bp_abnormal):
            treatment = "溶栓" if any(s in text for s in ["溶栓", "阿替普酶", "rt-pa", "rtpa", "thrombolysis"]) else (
                "抗凝" if any(s in text for s in ["抗凝", "华法林", "anticoagul"]) else "双抗")
            calls.append(("contraindication_check", {"treatment": treatment, "patient_info": text}))

        # 4. TOAST 分型:存在血管/心脏/影像线索
        if any(s in text for s in ["房颤", "瓣膜", "心梗", "狭窄", "斑块", "闭塞", "夹层",
                                   "血管炎", "af", "atrial", "stenosis", "plaque", "occlu"]):
            calls.append(("toast_classify", {}))

        # 去重(同一工具保留第一次调用)
        seen: set = set()
        unique: List[tuple] = []
        for name, args in calls:
            if name not in seen:
                seen.add(name)
                unique.append((name, args))
        return unique
