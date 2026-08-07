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

                # 临床量表优先:病例已明确给出分数时,跳过计算,以临床输入为准
                if self._should_use_clinical_score(state.get("case_text", ""), name):
                    clinical_verdict = self._clinical_score_verdict(state.get("case_text", ""), name)
                    result = clinical_verdict
                    logger.info(f"[tool_use] 病例已明确给出 {name} 分数, 跳过计算: {clinical_verdict}")
                elif tool is None:
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

                # 量表工具未由临床分数覆盖(实际执行了计算) → 标注为估算, 避免冒充临床评估
                if (
                    name in ("nihss_score", "mrs_score", "gcs_score")
                    and isinstance(result, dict)
                    and "error" not in result
                    and result.get("source") != "clinical_input"
                ):
                    result["source"] = "estimated"
                    result.setdefault("note", "")
                    result["note"] += (
                        "【估算提示】本分数由系统根据病例文本症状描述估算,"
                        "非临床实际评估结果,仅供参考,建议以医生实际量表评分为准。"
                    )

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
                    # 量表工具兜底执行 → 标注为估算(非临床实际评估)
                    if (
                        name in ("nihss_score", "mrs_score", "gcs_score")
                        and isinstance(result, dict)
                        and "error" not in result
                        and result.get("source") != "clinical_input"
                    ):
                        result["source"] = "estimated"
                        result.setdefault("note", "")
                        result["note"] += (
                            "【估算提示】本分数由系统根据病例文本症状描述估算,"
                            "非临床实际评估结果,仅供参考,建议以医生实际量表评分为准。"
                        )
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

            # 临床一致性校验:工具计算结果与病例明确输入的分数冲突时附加警示
            consistency_warnings = self._check_clinical_consistency(
                state.get("case_text", ""), tool_records
            )
            if consistency_warnings:
                warning_block = "\n\n【临床一致性校验警示】\n" + "\n".join(consistency_warnings)
                tool_results_text += warning_block
                logger.warning(f"[tool_use] 临床一致性校验发现 {len(consistency_warnings)} 处冲突")
        else:
            tool_results_text = ""

        logger.info(f"[tool_use] 工具调用完成, 共 {len(tool_records)} 次调用, 结果长度: {len(tool_results_text)}")

        return {
            "tool_results": tool_results_text,
            "tool_calls": tool_records,
        }

    def _check_clinical_consistency(self, case_text: str, tool_records: List[Dict]) -> List[str]:
        """
        临床一致性校验:对比病例文本中明确给出的量表分数与工具计算结果。

        原则:医生结构化输入优先于工具估算。若工具结果与临床输入冲突,
        返回警示信息,reason 节点应以临床输入为准。
        """
        warnings: List[str] = []
        if not case_text:
            return warnings

        for rec in tool_records:
            tool_name = rec.get("tool", "")
            result = rec.get("result", {}) or {}

            # NIHSS:病例明确总分 vs 工具计算结果
            if tool_name == "nihss_score":
                m = re.search(r"nihss\s*(评分)?\s*[:：=]?\s*(\d{1,2})", case_text.lower())
                if m and isinstance(result, dict) and "total_score" in result:
                    clinical = int(m.group(2))
                    computed = result["total_score"]
                    if clinical != computed:
                        warnings.append(
                            f"⚠️ NIHSS 冲突: 病例明确给出 {clinical} 分, 工具按症状估算 {computed} 分。"
                            f"临床评估优先, 请以 {clinical} 分为准。"
                        )

            # GCS:病例明确总分 vs 工具计算结果
            if tool_name == "gcs_score":
                m = re.search(r"gcs\s*(评分)?\s*[:：=]?\s*(\d{1,2})", case_text.lower())
                if m and isinstance(result, dict) and "total_score" in result:
                    clinical = int(m.group(2))
                    computed = result["total_score"]
                    if clinical != computed:
                        warnings.append(
                            f"⚠️ GCS 冲突: 病例明确给出 {clinical} 分, 工具估算 {computed} 分。"
                            f"临床评估优先, 请以 {clinical} 分为准。"
                        )
        return warnings

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
            # 临床已明确给出 NIHSS 总分时,以临床输入为准,不重新计算(避免覆盖医生评估)
            if not self._should_use_clinical_score(text, "nihss_score"):
                nihss_args = self._extract_nihss_args(text)
                calls.append(("nihss_score", nihss_args))
            # 临床已明确给出 mRS 时,同样以临床输入为准
            if not self._should_use_clinical_score(text, "mrs_score"):
                mrs_args = self._extract_mrs_args(text)
                if mrs_args is not None:
                    calls.append(("mrs_score", mrs_args))
        # GCS:仅在明确意识障碍时才评估(意识下降/昏迷/镇静/气道风险)
        # 神志清楚/无意识障碍 → 禁止调用, 避免产生"意识障碍"错误语义
        gcs_triggers = ["意识障碍", "昏迷", "昏睡", "嗜睡", "镇静", "气道风险", "格拉斯哥评分低", "gcs评分低"]
        gcs_clear = any(s in text for s in ["神志清楚", "意识清醒", "无意识障碍", "定向力正常", "神清语利"])
        if any(s in text for s in gcs_triggers) and not gcs_clear:
            # 临床已明确给出 GCS 时,以临床输入为准
            if not self._should_use_clinical_score(text, "gcs_score"):
                gcs_args = self._extract_gcs_args(text)
                calls.append(("gcs_score", gcs_args))

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
            # 急性卒中场景默认优先溶栓评估(时间窗内)；仅在文本明确指向抗凝/双抗时切换
            if any(s in text for s in ["抗凝", "华法林", "anticoagul", "低分子肝素", "肝素"]):
                treatment = "抗凝"
            elif any(s in text for s in ["双抗", "阿司匹林", "氯吡格雷", "替格瑞洛", "双联抗血小板"]):
                treatment = "双抗"
            else:
                treatment = "溶栓"
            calls.append(("contraindication_check", {"treatment": treatment, "patient_info": text}))

        # 4. TOAST 分型:存在血管/心脏/影像线索
        if any(s in text for s in ["房颤", "瓣膜", "心梗", "狭窄", "斑块", "闭塞", "夹层",
                                   "血管炎", "af", "atrial", "stenosis", "plaque", "occlu"]):
            calls.append(("toast_classify", {}))

        # 5. LVO 筛查:失语+偏瘫+皮层体征, 或 NIHSS≥6 且肢体无力
        has_lvo_features = (
            (any(s in text for s in ["失语", "言语困难", "aphasia"]) and any(s in text for s in ["偏瘫", "瘫痪", "无力", "hemiparesis", "hemiplegia"]))
            or any(s in text for s in ["凝视偏移", "偏视", "忽视", "单侧忽略"])
        )
        if has_lvo_features:
            lvo_args = self._extract_lvo_args(text)
            calls.append(("lvo_screening", lvo_args))

        # 去重(同一工具保留第一次调用)
        seen: set = set()
        unique: List[tuple] = []
        for name, args in calls:
            if name not in seen:
                seen.add(name)
                unique.append((name, args))
        return unique

    def _extract_nihss_args(self, text: str) -> Dict:
        """
        从病例文本提取 NIHSS 分项(基于明确症状描述,不臆测未提及的分项)。

        注意:本方法只为规则兜底提供"文本中明确存在"的症状映射,
        未提及的分项保持默认 0,不代表临床正常——reason 节点应结合全文判断。
        """
        t = text.lower()
        args: Dict = {}

        # 1a 意识水平
        if any(s in t for s in ["昏迷", "深度昏迷", "无反应"]):
            args["level_of_consciousness"] = 3
        elif any(s in t for s in ["昏睡", "昏沉", "嗜睡但能唤醒", "刺激可唤醒"]):
            args["level_of_consciousness"] = 2
        elif any(s in t for s in ["嗜睡", "倦怠", "唤醒后应答"]):
            args["level_of_consciousness"] = 1
        elif "无意识障碍" in t or "意识清醒" in t or "神志清楚" in t:
            args["level_of_consciousness"] = 0

        # 1b 意识提问(语言理解)
        if any(s in t for s in ["完全失语", "缄默", "不能理解", "完全不能理解"]):
            args["loc_questions"] = 2
        elif any(s in t for s in ["理解困难", "言语混乱", "答非所问", "部分理解"]):
            args["loc_questions"] = 1
        elif any(s in t for s in ["言语不清", "构音障碍", "表达困难", "找词困难"]):
            args["loc_questions"] = 1

        # 2 凝视
        if any(s in t for s in ["凝视麻痹", "同向偏视", "双眼向一侧"]):
            args["gaze"] = 2
        elif "凝视" in t:
            args["gaze"] = 1

        # 3 视野
        if any(s in t for s in ["偏盲", "视野缺损", "看不见一侧"]):
            args["visual"] = 2

        # 4 面瘫
        if any(s in t for s in ["口角歪斜", "面部歪斜", "面瘫", "口角下垂", "鼻唇沟变浅"]):
            args["facial"] = 2
        elif any(s in t for s in ["面部麻木", "轻微面瘫"]):
            args["facial"] = 1

        # 5/6 肢体运动:区分左右侧
        motor = 0
        if any(s in t for s in ["完全瘫痪", "不能抬起", "无法抬起", "无运动", "肌力0级", "肌力 0"]):
            motor = 4
        elif any(s in t for s in ["不能抗重力", "肌力2级", "肌力 2", "仅能水平移动"]):
            motor = 3
        elif any(s in t for s in ["抗重力", "肌力3级", "肌力 3", "可抬离床面"]):
            motor = 2
        elif any(s in t for s in ["肌力4级", "肌力 4", "轻度无力", "肢体无力"]):
            motor = 1

        if "右侧" in t or "右肢" in t or "右上下肢" in t or "右半身" in t:
            args["motor_arm"] = max(args.get("motor_arm", 0), motor)
            args["motor_leg"] = max(args.get("motor_leg", 0), motor)
        elif "左侧" in t or "左肢" in t or "左上下肢" in t or "左半身" in t:
            args["motor_arm"] = max(args.get("motor_arm", 0), motor)
            args["motor_leg"] = max(args.get("motor_leg", 0), motor)
        elif motor > 0:
            # 未指明侧别但明确无力
            args["motor_arm"] = max(args.get("motor_arm", 0), motor)
            args["motor_leg"] = max(args.get("motor_leg", 0), motor)

        # 7 共济失调
        if any(s in t for s in ["共济失调", "指鼻试验", "跟膝胫", "辨距不良"]):
            args["ataxia"] = 2

        # 8 感觉
        if any(s in t for s in ["感觉减退", "麻木", "针刺感减退", "痛觉减退"]):
            args["sensory"] = 1
        elif any(s in t for s in ["感觉丧失", "完全麻木", "无感觉"]):
            args["sensory"] = 2

        # 9 语言
        if any(s in t for s in ["完全失语", "缄默", "不能说话"]):
            args["language"] = 3
        elif any(s in t for s in ["严重失语", "不能表达", "表达不能"]):
            args["language"] = 2
        elif any(s in t for s in ["失语", "言语困难", "言语障碍", "不能正确表达", "表达困难", "找词困难"]):
            args["language"] = 1

        # 10 构音障碍
        if any(s in t for s in ["构音障碍", "言语含糊", "吐字不清", "说话不清"]):
            args["dysarthria"] = 1

        # 11 忽视
        if any(s in t for s in ["忽视", "忽略一侧", "单侧忽略", "偏侧忽略"]):
            args["extinction"] = 2

        return args

    def _extract_gcs_args(self, text: str) -> Dict:
        """从病例文本提取 GCS 三部分(仅当提及意识障碍时才调用,按描述映射)。"""
        t = text.lower()
        # 默认按明显意识障碍设置,避免"昏迷"却返回满分
        eye, verbal, motor = 1, 1, 1
        if any(s in t for s in ["神志清楚", "意识清醒", "无意识障碍", "定向力正常"]):
            eye, verbal, motor = 4, 5, 6
        elif any(s in t for s in ["嗜睡", "倦怠", "唤醒后应答", "唤醒后可回答"]):
            eye, verbal, motor = 3, 4, 5
        elif any(s in t for s in ["昏睡", "昏沉", "刺激可唤醒", "疼痛刺激睁眼"]):
            eye, verbal, motor = 2, 3, 4
        elif any(s in t for s in ["昏迷", "深度昏迷", "无反应", "刺痛无反应"]):
            eye, verbal, motor = 1, 1, 1
        return {"eye": eye, "verbal": verbal, "motor": motor}

    @staticmethod
    def _should_use_clinical_score(text: str, tool_name: str) -> bool:
        """
        判断病例文本是否已明确给出该量表的分数。

        原则:临床量表只要给出分数,就用给出的,不自行计算。
        覆盖 NIHSS / mRS / GCS 三种量表(含 LLM 主动调用与规则兜底两条路径)。
        """
        t = text.lower()
        if tool_name == "nihss_score":
            return bool(
                re.search(r"nihss\s*(评分)?\s*[:：=]?\s*(\d{1,2})", t)
                or re.search(r"卒中量表评分\s*[:：=]?\s*(\d{1,2})", t)
            )
        if tool_name == "mrs_score":
            return bool(
                re.search(r"mrs\s*(评分|分级)?\s*[:：=]?\s*(\d{1,2})", t)
                or re.search(r"改良\s*rank(in)?\s*(评分|量表)?\s*[:：=]?\s*(\d{1,2})", t)
                or re.search(r"rank(in)?\s*评分\s*[:：=]?\s*(\d{1,2})", t)
            )
        if tool_name == "gcs_score":
            return bool(
                re.search(r"gcs\s*(评分)?\s*[:：=]?\s*(\d{1,2})", t)
                or re.search(r"格拉斯哥(昏迷)?(评分|量表)?\s*[:：=]?\s*(\d{1,2})", t)
            )
        return False

    @staticmethod
    def _clinical_score_verdict(text: str, tool_name: str) -> Dict:
        """
        返回临床已给出的量表分数(以临床输入为准,不覆盖)。

        返回结构与对应计算工具一致,便于 reason 节点统一消费。
        """
        t = text.lower()
        if tool_name == "nihss_score":
            m = re.search(r"nihss\s*(评分)?\s*[:：=]?\s*(\d{1,2})", t) or re.search(
                r"卒中量表评分\s*[:：=]?\s*(\d{1,2})", t)
            score = int(m.group(2)) if m else None
            if score is None:
                return {"error": "未提取到临床 NIHSS 分数"}
            if score <= 4:
                severity = "轻度(0-4)"
            elif score <= 15:
                severity = "中度(5-15)"
            elif score <= 20:
                severity = "中重度(16-20)"
            else:
                severity = "重度(21-42)"
            return {
                "total_score": score,
                "severity": severity,
                "source": "clinical_input",
                "note": "临床已明确给出 NIHSS 分数,直接采用,未重新计算。",
            }
        if tool_name == "mrs_score":
            m = re.search(r"mrs\s*(评分|分级)?\s*[:：=]?\s*(\d{1,2})", t) or re.search(
                r"改良\s*rank(in)?\s*(评分|量表)?\s*[:：=]?\s*(\d{1,2})", t) or re.search(
                r"rank(in)?\s*评分\s*[:：=]?\s*(\d{1,2})", t)
            score = int(m.group(2)) if m else None
            if score is None:
                return {"error": "未提取到临床 mRS 分数"}
            descriptions = {
                0: "完全无症状", 1: "无明显功能障碍", 2: "轻度残疾", 3: "中度残疾",
                4: "中重度残疾", 5: "重度残疾", 6: "死亡",
            }
            return {
                "score": score,
                "description": descriptions.get(score, "未知"),
                "source": "clinical_input",
                "note": "临床已明确给出 mRS 分级,直接采用,未重新计算。",
            }
        if tool_name == "gcs_score":
            m = re.search(r"gcs\s*(评分)?\s*[:：=]?\s*(\d{1,2})", t) or re.search(
                r"格拉斯哥(昏迷)?(评分|量表)?\s*[:：=]?\s*(\d{1,2})", t)
            score = int(m.group(2)) if m else None
            if score is None:
                return {"error": "未提取到临床 GCS 分数"}
            if score >= 13:
                severity = "正常/轻度意识障碍(13-15)"
            elif score >= 9:
                severity = "中度意识障碍(9-12)"
            else:
                severity = "重度意识障碍(≤8)"
            return {
                "total_score": score,
                "severity": severity,
                "source": "clinical_input",
                "note": "临床已明确给出 GCS 分数,直接采用,未重新计算。",
            }
        return {"error": f"不支持的量表: {tool_name}"}

    @staticmethod
    def _extract_mrs_args(text: str):
        """
        从病例文本提取 mRS 分级(仅当病例明确描述功能状态且未给分时)。
        无法可靠判断时返回 None(不调用,避免伪造)。
        """
        t = text.lower()
        # 明确描述重度依赖/卧床
        if any(s in t for s in ["卧床", "长期卧床", "完全依赖", "不能自理"]):
            return {"score": 5}
        # 需要帮助行走
        if any(s in t for s in ["需他人帮助行走", "扶行", "需搀扶"]):
            return {"score": 4}
        # 生活需部分帮助
        if any(s in t for s in ["部分依赖", "需人照料"]):
            return {"score": 3}
        # 无明显描述 → 不调用
        return None

    @staticmethod
    def _extract_lvo_args(text: str) -> Dict:
        """从病例文本提取 LVO 筛查输入(失语/偏瘫/皮层体征/凝视/忽视/NIHSS)。"""
        t = text.lower()
        args: Dict = {"aphasia": False, "hemiplegia": False, "cortical_signs": False,
                      "gaze_deviation": False, "neglect": False}

        # NIHSS(临床给分或估算)
        m = re.search(r"nihss\s*(评分)?\s*[:：=]?\s*(\d{1,2})", t)
        args["nihss_score"] = int(m.group(2)) if m else 0

        # 失语/言语障碍
        if any(s in t for s in ["失语", "言语困难", "言语障碍", "不能表达", "aphasia", "表达困难"]):
            args["aphasia"] = True
        # 偏瘫/肢体无力
        if any(s in t for s in ["偏瘫", "瘫痪", "不能抬起", "无力", "hemiparesis", "hemiplegia", "肌力"]):
            args["hemiplegia"] = True
        # 皮层体征(凝视/忽视/视野/意识下降)
        if any(s in t for s in ["凝视偏移", "偏视", "同向偏视", "忽视", "单侧忽略", "视野缺损", "偏盲", "意识下降", "意识障碍"]):
            args["cortical_signs"] = True
        if any(s in t for s in ["凝视偏移", "偏视", "同向偏视", "gaze"]):
            args["gaze_deviation"] = True
        if any(s in t for s in ["忽视", "单侧忽略", "忽略一侧", "neglect"]):
            args["neglect"] = True
        return args
