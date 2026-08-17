import logging
import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
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
from app.agents.streaming.translator import StreamEventTranslator, _NODE_DISPLAY

logger = logging.getLogger(__name__)

# 流事件翻译已拆至 app.agents.streaming.translator(StreamEventTranslator)
# _NODE_DISPLAY 由 translator 模块导出, 此处复用其绑定以兼容外部引用


class QwenAgent:
    """Qwen Agent 编排器 Facade"""

    def __init__(
        self,
        llm_proposer,
        llm_critic,
        medical_assistant,
        prompt_manager,
        report_manager,
        llm_turbo=None,
        llm_consensus=None,
        checkpointer=None,
    ):
        self.llm_proposer = llm_proposer
        self.llm_critic = llm_critic
        self.llm_turbo = llm_turbo or llm_critic
        self.medical_assistant = medical_assistant
        self.prompts = prompt_manager
        self.reports = report_manager
        # 流事件翻译器(思考链/用量/缺口事件), 与图执行解耦
        self.translator = StreamEventTranslator()

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
        self.consensus_node = ConsensusNode(llm_consensus or self.llm_critic)
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
            checkpointer=checkpointer,
        ).build()

    async def run_clinical_reasoning(
        self,
        case_text: str,
        all_info: str = "",
        patient_memory: Dict[str, str] | None = None,
        report_mode: str = "emergency",
        show_thinking: bool = True,
        human_review: bool = False,
        thread_id: str | None = None,
    ) -> AsyncGenerator[Dict, None]:
        """运行临床推理。

        human_review=True 时在报告生成前 interrupt 挂起(阶段3 HITL),
        流内会产出 {"type": "human_review", "thread_id": ...} 事件, 由 /model/resume 续跑。
        """
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
            "router_evidence_types": [],
            "router_categories": [],
            "router_keywords": [],
            "router_routes": [],
            # 阶段3 HITL 人工复核
            "human_review_required": bool(human_review),
            "review_decision": {},
            "review_approved": False,
            "review_feedback": "",
            "human_review_done": False,
            "review_count": 0,
            # 合规审计(validate 之后)
            "compliance_passed": True,
            "compliance_issues": [],
            "compliance_warnings": [],
            "compliance_audit": {},
        }

        # 为每次请求生成唯一 thread_id(检查点持久化 + HITL 续跑依赖它)
        tid = thread_id or uuid.uuid4().hex
        config = {
            "recursion_limit": 60,  # 提高递归上限,避免反思/检索循环超限
            "configurable": {
                "thread_id": tid
            }
        }

        try:
            # LangGraph 1.x 已移除 astream_events, 改用 astream 三流模式:
            #   updates  节点完成时产出 {node: output} → node_start/node_done
            #   messages 节点内 LLM token 流 (chunk, metadata) → token 事件(报告打字机)
            #   custom   各节点 astream_text 实时写入的生成过程 → node_token 事件(思考链实时打印)
            stream = self.graph.astream(
                initial_state, config=config, stream_mode=["updates", "messages", "custom"]
            )
            async for item in self._consume_graph_stream(stream, show_thinking, tid):
                yield item
        except Exception as e:
            logger.error(f"临床推理管线异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    async def resume_clinical_reasoning(
        self,
        thread_id: str,
        decision: Dict | None = None,
    ) -> AsyncGenerator[Dict, None]:
        """续跑被 HITL 中断挂起的临床推理(阶段3)。

        decision = {"approved": bool, "feedback": str} —— 医生复核决定。
        批准 → 生成报告; 驳回 → 携反馈重新会诊(可能再次 interrupt 挂起)。
        """
        config = {
            "recursion_limit": 60,
            "configurable": {"thread_id": thread_id},
        }
        resume_value = decision if isinstance(decision, dict) else {"approved": False, "feedback": ""}
        try:
            stream = self.graph.astream(
                Command(resume=resume_value),
                config=config,
                stream_mode=["updates", "messages", "custom"],
            )
            async for item in self._consume_graph_stream(stream, True, thread_id):
                yield item
        except Exception as e:
            logger.error(f"临床推理续跑异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    async def _consume_graph_stream(
        self,
        stream_iterable,
        show_thinking: bool,
        thread_id: str,
    ) -> AsyncGenerator[Dict, None]:
        """统一的流翻译循环(初始运行与 HITL 续跑共用)。

        - updates 中的 __interrupt__ → human_review 事件(记录 thread_id, 供 /model/resume);
        - 正常结束后删除线程检查点(仅待复核线程保留);
        - 咨询类会话结束后产出信息缺口追问(ask_doctor)。
        """
        streamed_nodes: set = set()
        started_nodes: set = set()
        # 各节点实时生成缓冲: {node: {expert_or_node: 累计文本}}, 供思考链实时打印
        self.translator._live_buffers = {}
        # 信息缺口追问: 记录会诊路径与各节点最终输出
        is_consultation = False
        last_outputs: dict = {}
        pending_review = False

        try:
            async for stream_mode, chunk in stream_iterable:
                if stream_mode == "messages":
                    events = self.translator._on_message_chunk(chunk, show_thinking, started_nodes, streamed_nodes)
                elif stream_mode == "custom":
                    events = self.translator._on_custom_event(chunk, show_thinking, started_nodes)
                else:  # updates
                    events = []
                    for name, output in chunk.items():
                        if name == "__interrupt__":
                            # HITL 挂起: 产出复核事件(thread_id 供前端/后端续跑)
                            pending_review = True
                            for item in output:
                                payload = getattr(item, "value", None)
                                yield {
                                    "type": "human_review",
                                    "status": "pending",
                                    "thread_id": thread_id,
                                    "payload": payload if isinstance(payload, dict) else {},
                                }
                        elif isinstance(output, dict):
                            last_outputs[name] = output
                            if name == "intent" and output.get("intent_type") == "consultation":
                                is_consultation = True
                    events += self.translator._on_node_updates(chunk, show_thinking, started_nodes, streamed_nodes)
                for item in events:
                    yield item

            # ── 信息缺口追问闭环: 会诊结束后列出关键信息缺口, 供前端"补充后重新会诊" ──
            if is_consultation and not pending_review:
                for item in self._ask_doctor_events(last_outputs):
                    yield item
        finally:
            # 仅 HITL 待复核线程保留检查点(等待 /model/resume); 其余即时清理, 防 sqlite 膨胀
            if not pending_review:
                await self._cleanup_thread(thread_id)

    @staticmethod
    def _ask_doctor_events(last_outputs: dict) -> list[Dict]:
        """由各节点输出提炼信息缺口, 生成 ask_doctor 追问事件。"""
        missing = []
        evidence_judge = last_outputs.get("evidence_judge") or {}
        if not evidence_judge.get("need_retrieve", True) and evidence_judge.get("missing_information"):
            missing = [str(x).strip() for x in evidence_judge["missing_information"] if str(x).strip()]
        if not missing:
            research_plan = last_outputs.get("research_plan") or {}
            missing = [str(x).strip() for x in research_plan.get("missing_information", []) if str(x).strip()]
        if not missing:
            validate = last_outputs.get("validate") or {}
            feedback = str(validate.get("validation_feedback", "") or "").strip()
            if not validate.get("validation_passed", True) and feedback:
                missing = [feedback[:300]]
        if not missing:
            return []
        return [{
            "type": "ask_doctor",
            "questions": missing[:6],
            "message": "以下信息缺口影响决策质量，补充后可重新发起会诊：",
        }]

    async def _cleanup_thread(self, thread_id: str):
        """删除已结束推理线程的检查点(兼容同步/异步 delete_thread 两种实现)。"""
        try:
            saver = getattr(self.graph, "checkpointer", None)
            if saver is None:
                return
            delete = getattr(saver, "adelete_thread", None) or getattr(saver, "delete_thread", None)
            if not callable(delete):
                return
            result = delete(thread_id)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:  # noqa: BLE001 - 清理失败不影响主流程
            logger.warning(f"[checkpoint] 清理线程 {thread_id} 失败: {e}")

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
