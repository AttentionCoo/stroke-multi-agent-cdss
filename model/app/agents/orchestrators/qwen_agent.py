import logging
import asyncio
import json
from typing import AsyncGenerator, Dict
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.clinical_graph import ClinicalGraphBuilder
from app.agents.orchestrators.nodes.intent_node import IntentNode
from app.agents.orchestrators.nodes.memory_node import MemoryNode
from app.agents.orchestrators.nodes.analysis_node import AnalysisNode
from app.agents.orchestrators.nodes.research_node import ResearchPlanNode
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.nodes.evidence_node import EvidenceJudgeNode, QueryRewriteNode
from app.agents.orchestrators.nodes.reason_node import ReasonNode
from app.agents.orchestrators.nodes.tool_use_node import ToolUseNode
from app.agents.orchestrators.nodes.evidence_router_node import EvidenceRouterNode
from app.agents.orchestrators.nodes.debate_node import DebateNode, ConsensusNode
from app.agents.orchestrators.nodes.validate_node import ValidateNode
from app.agents.orchestrators.nodes.report_node import ReportNode
from app.utils.error_codes import build_error_event, format_error_log

logger = logging.getLogger(__name__)

_NODE_DISPLAY: Dict[str, Dict[str, str]] = {
    "intent": {"running": "正在判断问题类型...", "done": "问题类型判断"},
    "reject": {"running": "正在处理回复...", "done": "请求处理"},
    "memory": {"running": "正在激活患者分层记忆...", "done": "患者分层记忆"},
    "analysis": {"running": "正在分析病例结构...", "done": "病例结构化分析"},
    "tool_use": {"running": "正在调用脑卒中医疗工具...", "done": "医疗工具调用"},
    "research_plan": {"running": "正在规划循证检索任务...", "done": "主动检索规划"},
    "retrieve": {"running": "正在检索循证医学证据...", "done": "循证医学证据检索"},
    "evidence_judge": {"running": "正在评估证据充分性...", "done": "证据质量评估"},
    "query_rewrite": {"running": "正在改写医学检索式...", "done": "医学查询重写"},
    "reason": {"running": "正在生成专家独立意见...", "done": "多专家独立推理"},
    "debate": {"running": "正在进行专家交叉质询...", "done": "多专家交叉质询"},
    "consensus_agent": {"running": "正在形成会诊共识...", "done": "会诊主持人共识"},
    "validate": {"running": "正在进行校验反思...", "done": "安全校验与反思"},
    "generate_report": {"running": "正在生成临床报告...", "done": "临床报告生成"},
    "knowledge_answer": {"running": "正在回答知识问题...", "done": "医学知识回答"},
}

_INTENT_LABELS: Dict[str, str] = {
    "consultation": "临床问诊",
    "knowledge": "医学知识问答",
    "irrelevant": "非脑卒中医疗问题",
}


class QwenAgent:
    """Qwen Agent 编排器 Facade"""

    _STREAMING_NODES = {"knowledge_answer", "generate_report"}

    def __init__(
        self,
        llm_proposer,
        llm_critic,
        medical_assistant,
        prompt_manager,
        report_manager,
        llm_turbo=None,
    ):
        self.llm_proposer = llm_proposer
        self.llm_critic = llm_critic
        self.llm_turbo = llm_turbo or llm_critic
        self.medical_assistant = medical_assistant
        self.prompts = prompt_manager
        self.reports = report_manager

        # 初始化所有节点
        self.intent_node = IntentNode(self.llm_turbo)
        self.memory_node = MemoryNode()
        self.analysis_node = AnalysisNode(self.llm_critic)
        self.tool_use_node = ToolUseNode(self.llm_turbo)
        self.research_plan_node = ResearchPlanNode(self.llm_critic)
        self.evidence_router_node = EvidenceRouterNode(self.llm_critic)
        self.retrieve_node = RetrieveNode(medical_assistant)
        self.evidence_judge_node = EvidenceJudgeNode(self.llm_critic)
        self.query_rewrite_node = QueryRewriteNode(self.llm_critic)
        self.reason_node = ReasonNode(self.llm_proposer)
        self.debate_node = DebateNode(self.llm_proposer)
        self.consensus_node = ConsensusNode(self.llm_critic)
        self.validate_node = ValidateNode(self.llm_critic)
        self.report_node = ReportNode(self.llm_proposer, report_manager)

        # 构建图
        self.graph = ClinicalGraphBuilder(
            intent_node=self.intent_node,
            memory_node=self.memory_node,
            analysis_node=self.analysis_node,
            research_plan_node=self.research_plan_node,
            retrieve_node=self.retrieve_node,
            evidence_judge_node=self.evidence_judge_node,
            query_rewrite_node=self.query_rewrite_node,
            reason_node=self.reason_node,
            debate_node=self.debate_node,
            consensus_node=self.consensus_node,
            validate_node=self.validate_node,
            report_node=self.report_node,
            tool_use_node=self.tool_use_node,
            evidence_router_node=self.evidence_router_node,
            llm_critic=self.llm_critic,
            report_manager=self.reports,
        ).build()

    async def run_clinical_reasoning(
        self,
        case_text: str,
        all_info: str = "",
        patient_memory: Dict[str, str] | None = None,
        report_mode: str = "emergency",
        show_thinking: bool = True,
    ) -> AsyncGenerator[Dict, None]:
        """运行临床推理"""
        initial_state: ClinicalState = {
            "case_text": case_text,
            "all_info": all_info,
            "patient_memory": patient_memory or {},
            "active_memory": "",
            "report_mode": report_mode,
            "intent_type": "",
            "context": {},
            "clinical_questions": [],
            "retrieval_tasks": [],
            "retrieval_queries": [],
            "retrieved_queries": [],
            "hypothetical_document": "",
            "need_retrieve": True,
            "evidence_quality": 0.0,
            "evidence_assessment": "",
            "missing_information": [],
            "retrieval_round": 0,
            "key_risks": [],
            "complexity": "high",
            "evidence": "",
            "proposal": "",
            "critique": "",
            "user_questions": [],
            "report": "",
            "generalist_advice": "",
            "specialist_advice": "",
            "pharmacist_advice": "",
            "expert_opinions": {},
            "debate_transcript": "",
            "consensus": "",
            "validation_passed": True,
            "validation_feedback": "",
            "reflection_count": 0,
            "tool_results": "",
            "tool_calls": [],
            "clinical_decisions": [],
        }
        streamed_nodes: set = set()

        try:
            # 为每次请求生成唯一的thread_id
            import uuid
            config = {
                "configurable": {
                    "thread_id": uuid.uuid4().hex
                }
            }
            
            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                translated = self._translate_event(event, show_thinking, streamed_nodes)
                if isinstance(translated, list):
                    for item in translated:
                        yield item
                elif translated:
                    yield translated

        except Exception as e:
            logger.error(f"临床推理管线异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    def _translate_event(
        self,
        event: dict,
        show_thinking: bool,
        streamed_nodes: set,
    ) -> Dict | list[Dict] | None:
        """翻译 LangGraph 事件"""
        evt = event.get("event", "")
        name = event.get("name", "")
        meta = event.get("metadata", {})
        langgraph_node = meta.get("langgraph_node", "")

        logger.info(f"[event] 事件类型: {evt}, 节点名称: {name}, langgraph_node: {langgraph_node}")

        if evt == "on_chain_start" and name in _NODE_DISPLAY and show_thinking:
            return {
                "type": "node_start",
                "node": name,
                "label": _NODE_DISPLAY[name]["running"],
                "status": "running",
            }

        if evt == "on_chain_end" and name in _NODE_DISPLAY:
            output = event.get("data", {}).get("output", {})
            report_text = output.get("report", "") if isinstance(output, dict) else ""
            
            logger.info(f"[event] 节点 {name} 完成，输出类型: {type(output)}")
            if isinstance(output, dict):
                logger.info(f"[event] 节点 {name} 输出键: {list(output.keys())}")
                if "report" in output:
                    logger.info(f"[event] 节点 {name} 报告长度: {len(output['report'])}")

            translated_events = []
            if show_thinking:
                translated_events.append(self._node_done_event(name, output))

                # tool_use 节点:将每次工具调用展开为独立步骤事件,前端可逐条展示
                if name == "tool_use" and isinstance(output, dict):
                    tool_calls = output.get("tool_calls", []) or []
                    for i, call in enumerate(tool_calls[:10]):  # 防止刷屏,最多展示 10 次
                        if not isinstance(call, dict):
                            continue
                        tool_name = call.get("tool", "未知工具")
                        args = call.get("arguments", {}) or {}
                        result = call.get("result", {}) or {}
                        translated_events.append({
                            "type": "node_done",
                            "node": f"tool_call_{i}",
                            "label": f"工具调用: {tool_name}",
                            "summary": (
                                f"参数: {self._short_text(json.dumps(args, ensure_ascii=False), 200)}\n"
                                f"结果: {self._short_text(json.dumps(result, ensure_ascii=False), 300)}"
                            ),
                            "status": "done",
                        })

            needs_fallback_token = name == "reject" or (
                name in self._STREAMING_NODES and name not in streamed_nodes
            )
            if needs_fallback_token and report_text:
                logger.info(f"[event] 节点 {name} 输出报告内容，长度: {len(report_text)}")
                streamed_nodes.add(name)
                translated_events.append({"type": "token", "content": report_text})

            if len(translated_events) == 1:
                return translated_events[0]
            if translated_events:
                return translated_events

        if evt == "on_chat_model_stream" and langgraph_node in self._STREAMING_NODES:
            chunk = event.get("data", {}).get("chunk")
            content = getattr(chunk, "content", "") if chunk else ""
            if content:
                streamed_nodes.add(langgraph_node)
                return {"type": "token", "content": content}

        return None

    def _node_done_event(self, node: str, output: dict) -> Dict:
        """构造节点完成事件。"""
        return {
            "type": "node_done",
            "node": node,
            "label": _NODE_DISPLAY[node]["done"],
            "summary": self._node_summary(node, output),
            "status": "done",
        }

    def _node_summary(self, node: str, output: dict) -> str:
        """生成适合通过 SSE 展示的节点结果摘要。"""
        if not isinstance(output, dict):
            output = {}

        summary = {}
        if node == "intent":
            intent_type = str(output.get("intent_type", ""))
            summary = {"判断结果": _INTENT_LABELS.get(intent_type, intent_type or "未知类型")}
        elif node == "memory":
            memory = output.get("patient_memory", {})
            summary = {
                "已激活记忆层": [
                    key for key, value in memory.items() if value
                ],
                "有效上下文": self._short_text(output.get("active_memory", ""), 320),
            }
        elif node == "analysis":
            summary = {
                "病例复杂度": output.get("complexity", "未知"),
                "关键风险": self._short_list(output.get("key_risks", []), 4, 100),
                "检索子问题": self._short_list(output.get("clinical_questions", []), 5, 120),
            }
        elif node == "tool_use":
            calls = output.get("tool_calls", [])
            summary = {
                "工具调用次数": len(calls) if isinstance(calls, list) else 0,
                "工具列表": self._short_list(
                    [f"{c.get('tool', '')}: {json.dumps(c.get('result', {}), ensure_ascii=False)[:120]}" for c in calls if isinstance(c, dict)],
                    5,
                    160,
                ) or "未调用工具",
            }
        elif node == "research_plan":
            decisions = output.get("clinical_decisions", [])
            summary = {
                "需要检索": bool(output.get("need_retrieve", False)),
                "临床决策节点(按优先级)": self._short_list(
                    [
                        f"[{d.get('priority', '?')}] {d.get('decision_name', '')}"
                        for d in decisions
                        if isinstance(d, dict) and d.get("decision_name")
                    ],
                    6,
                    80,
                ) or "未生成决策节点",
                "检索任务": self._short_list(
                    [task.get("question", "") for task in output.get("retrieval_tasks", []) if isinstance(task, dict)],
                    5,
                    100,
                ),
                "扩展查询": self._short_list(output.get("retrieval_queries", []), 6, 120),
                "信息缺口": self._short_list(output.get("missing_information", []), 5, 100),
            }
        elif node == "retrieve":
            ev = output.get("evidence", "")
            count = ev.count("【证据 ") if str(ev).strip() else 0
            summary = {
                "检索轮次": output.get("retrieval_round", 0),
                "证据条数": count,
                "证据摘要": self._short_text(ev, 420) or "未检索到相关证据",
            }
        elif node == "evidence_judge":
            summary = {
                "证据质量": output.get("evidence_quality", 0.0),
                "是否继续检索": bool(output.get("need_retrieve", False)),
                "评估结论": self._short_text(output.get("evidence_assessment", ""), 280),
                "剩余缺口": self._short_list(output.get("missing_information", []), 5, 100),
            }
        elif node == "query_rewrite":
            summary = {
                "重写后查询": self._short_list(output.get("retrieval_queries", []), 6, 120),
                "继续检索": bool(output.get("need_retrieve", False)),
            }
        elif node == "reason":
            expert_summaries = {
                role: self._short_text(advice, 180)
                for role, advice in list(output.get("expert_opinions", {}).items())[:4]
            }
            if not expert_summaries:
                for key, value in output.items():
                    if key.endswith("_advice") and value and len(expert_summaries) < 4:
                        expert_summaries[key.removesuffix("_advice")] = self._short_text(value, 180)
            summary = {
                "专家意见摘要": expert_summaries,
            }
            if output.get("proposal") or output.get("critique"):
                summary.update({
                    "综合方案摘要": self._short_text(output.get("proposal", ""), 360),
                    "风险审查摘要": self._short_text(output.get("critique", ""), 260),
                })
        elif node == "debate":
            summary = {
                "交叉质询摘要": self._short_text(output.get("debate_transcript", ""), 620),
            }
        elif node == "consensus_agent":
            summary = {
                "会诊共识": self._short_text(output.get("consensus", ""), 260),
                "综合方案摘要": self._short_text(output.get("proposal", ""), 360),
                "风险审查摘要": self._short_text(output.get("critique", ""), 260),
            }
        elif node == "validate":
            passed = bool(output.get("validation_passed", False))
            summary = {
                "校验结果": "通过" if passed else "需要反思修正",
                "反思次数": output.get("reflection_count", 0),
                "校验反馈": self._short_text(output.get("validation_feedback", ""), 360)
                or "规则引擎与医学逻辑审查均未发现严重冲突",
            }
        elif node == "generate_report":
            report = output.get("report", "")
            summary = {"报告状态": "已生成", "报告长度": f"{len(str(report))} 字符"}
        elif node == "knowledge_answer":
            report = output.get("report", "")
            summary = {"回答状态": "已生成", "回答长度": f"{len(str(report))} 字符"}
        elif node == "reject":
            summary = {"处理结果": self._short_text(output.get("report", ""), 240)}

        if not summary:
            summary = {"执行结果": "步骤已完成"}
        return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _short_text(value, limit: int) -> str:
        """压缩空白并限制单项摘要长度。"""
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[:limit - 3].rstrip() + "..."

    @classmethod
    def _short_list(cls, values, max_items: int, item_limit: int) -> list:
        """限制列表项数量和每项长度，防止思考事件过大。"""
        if not isinstance(values, list):
            return []
        return [cls._short_text(value, item_limit) for value in values[:max_items] if value]

    # 保留原有的方法以兼容现有代码
    async def _parallel_propose_and_critique(
        self,
        context: Dict,
        evidence: str,
        all_info: str,
        user_questions: list,
    ) -> tuple:
        """并行提案和批判（保留以兼容现有代码）"""
        # 这里应该调用 ProposalEngine 和 CriticEngine
        # 暂时保留原有逻辑
        import json
        from langchain_core.messages import SystemMessage, HumanMessage

        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        evidence_str = evidence or "未检索到相关证据"
        all_info_str = all_info or "无"

        _FALLBACK_PROPOSER = """你是三甲医院神经内科主任医师，拥有 20 年急诊经验。

【患者结构化信息】
{context}

【历史上下文】
{all_info}

【检索到的循证医学证据】
{evidence}

请给出完整临床推理：
1. 鉴别诊断排序（至少3个，含概率区间和依据）
2. 当前最危险的生理问题
3. 立即行动建议（分钟级、小时级、24h内）
4. 关键风险分析
5. 缺失的关键信息
6. 不确定性声明
7. 证据支持说明

禁止确诊语气。禁止具体药物剂量。"""

        if user_questions:
            questions_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(user_questions))
            proposer_prompt = f"""
你是三甲医院神经内科专家。

【患者信息】
{context_str}

【医学证据】
{evidence_str}

用户提出了以下问题：

{questions_text}

请严格遵守：

1 只回答这些问题
2 禁止扩展额外章节
3 禁止提出行动计划
4 禁止输出无关分析

回答格式：

### 问题1
回答

### 问题2
回答
"""
        else:
            proposer_prompt = _FALLBACK_PROPOSER.format(
                context=context_str,
                all_info=all_info_str,
                evidence=evidence_str
            )

        pre_critic_prompt = f"""你是临床质量控制专家和医疗安全审查员。

        请基于以下患者信息和医学证据，预先识别所有潜在的临床风险和容易遗漏的问题。

        【患者信息】
        {context_str}

        【医学证据】
        {evidence_str}

        请从以下角度系统性识别风险：
        1. 容易被忽视的鉴别诊断（非卒中可能）
        2. 气道与呼吸的隐性风险
        3. 时间窗判断的陷阱
        4. 合并症对治疗决策的影响
        5. 可能的治疗禁忌
        6. 致命性遗漏风险

        对每个风险给出严重程度和建议。请精简输出，重突出。

        请额外输出：
        - 当前最可能被忽视但致命的风险（仅1项）
        - 若未处理，最可能导致的后果
        - 建议优先级
        """

        proposer_task = self.llm_critic.ainvoke([
            SystemMessage(content=self.reports.system_role),
            HumanMessage(content=proposer_prompt),
        ])
        critic_task = self.llm_critic.ainvoke([
            SystemMessage(content=self.reports.system_role),
            HumanMessage(content=pre_critic_prompt),
        ])
        logger.info("[propose] 开始等待 asyncio.gather (proposer + critic)...")
        proposer_resp, critic_resp = await asyncio.gather(proposer_task, critic_task)
        logger.info(f"[propose] gather 完成，proposer_len={len(proposer_resp.content)}, critic_len={len(critic_resp.content)}")
        proposal_text = proposer_resp.content
        critic_text = critic_resp.content

        if user_questions:
            return proposal_text, critic_text

        final_prompt = f"""
        你是临床质量审查专家。

        以下是两个内容：

        【初步回答】
        {proposal_text}

        【风险审查意见】
        {critic_text}

        任务：

        1 如果回答存在医学风险或逻辑错误 → 修改
        2 如果回答已经合理 → 保持原结构
        3 仅进行必要修改
        4 保持回答简洁

        输出最终答案。
        """

        logger.info(f"[propose] 开始第三次 ainvoke (integration)，prompt_len={len(final_prompt)}")
        final_resp = await self.llm_critic.ainvoke([
            SystemMessage(content=self.reports.system_role),
            HumanMessage(content=final_prompt),
        ])
        logger.info(f"[propose] integration 完成，result_len={len(final_resp.content)}")
        return final_resp.content, critic_text

    async def analyze_patient_risk_fast(self, patient_data: str) -> Dict[str, str]:
        """快速分析患者风险（保留以兼容现有代码）"""
        prompt = f"""你是资深临床风险评估医生。请基于以下患者信息，快速给出健康风险结论。

    患者信息：{patient_data}

    请直接输出 JSON，不要任何解释、不要 markdown 代码块：

    {{
        "riskLevel": "低风险/中风险/高风险",
        "suggestion": "一句到两句实用干预建议，不要写具体药物剂量",
        "analysisDetails": "简要说明主要风险依据（控制在80字以内）"
    }}

    要求：
    - riskLevel 必须是：低风险、中风险、高风险之一
    - suggestion 简洁、可执行
    - analysisDetails 聚焦关键症状和已知病史，不要给出明确诊断"""

        try:
            response = await self.llm_critic.ainvoke([HumanMessage(content=prompt)])
            result = self._parse_json(getattr(response, "content", ""), {}) or {}
            payload = {
                "riskLevel": result.get("riskLevel", "中风险"),
                "suggestion": result.get("suggestion", "建议结合临床检查进一步评估，如有不适及时就医。"),
                "analysisDetails": result.get("analysisDetails", "基于患者提供的信息完成初步风险评估。"),
            }
            # 归一化简写
            normalize = {"高": "高风险", "中": "中风险", "低": "低风险"}
            if payload["riskLevel"] in normalize:
                payload["riskLevel"] = normalize[payload["riskLevel"]]
            logger.info(f"[AIAnalyzeFast] riskLevel={payload['riskLevel']}")
            return payload
        except Exception as e:
            logger.error(f"[AIAnalyzeFast] failed: {e}")
            return {
                "riskLevel": "中风险",
                "suggestion": "建议结合线下检查结果进一步评估，如症状加重请及时就医。",
                "analysisDetails": "系统已完成基础风险评估，但详细分析生成失败，请结合临床实际判断。",
            }

    def _parse_json(self, text: str, default=None):
        """解析 JSON（保留以兼容现有代码）"""
        content = (text or "").strip()
        try:
            return json.loads(content)
        except Exception:
            pass
        for marker in ["```json", "```"]:
            if marker in content:
                try:
                    s = content.split(marker)[1].split("```")[0].strip()
                    return json.loads(s)
                except Exception:
                    pass
        for sc, ec in [("{", "}"), ("[", "]")]:
            si, ei = content.find(sc), content.rfind(ec)
            if si != -1 and ei > si:
                try:
                    return json.loads(content[si:ei + 1])
                except Exception:
                    pass
        return default
