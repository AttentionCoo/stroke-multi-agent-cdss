# Agent/qwen/qwenAgent.py — 极速版 v2：进一步优化速度

import logging
import asyncio
import json
from typing import Generator, List, Dict, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from config.config_loader import PromptManager, ReportTemplateManager

logger = logging.getLogger(__name__)

MAX_SUB_QUESTIONS = 3
# 喂给 Proposer / Critic / 最终报告的证据最大字符数
MAX_EVIDENCE_CHARS = 3000
# 喂给最终报告的 Proposer / Critic 最大字符数
MAX_PROPOSAL_CHARS = 3000
MAX_CRITIQUE_CHARS = 3000


class qwenAgent:

    def __init__(
        self,
        llm_proposer,
        llm_critic,
        medical_assistant,
        prompt_manager: PromptManager,
        report_manager: ReportTemplateManager
    ):
        self.llm_proposer = llm_proposer
        self.llm_critic = llm_critic
        self.medical_assistant = medical_assistant
        self.prompts = prompt_manager
        self.reports = report_manager

    # =========================================================
    # 工具方法
    # =========================================================

    def _get_prompt(self, key, fallback, **kwargs):
        prompt = None
        if self.prompts:
            prompt = self.prompts.get(key, **kwargs)
        if not prompt:
            try:
                prompt = fallback.format(**kwargs)
            except KeyError:
                prompt = fallback
        return prompt

    def _emit_thinking(self, step, title, content) -> dict:
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)

        logger.info(f"[{step}] {title}")
        logger.info(
            content_str[:500] + ("..." if len(content_str) > 500 else "")
        )
        return {
            "type": "thinking",
            "step": step,
            "title": title,
            "content": content_str
        }

    def _parse_json(self, text, default=None):
        content = text.strip()
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

    def _truncate(self, text: str, max_chars: int) -> str:
        """智能截断：保留开头和结尾"""
        if not text or len(text) <= max_chars:
            return text
        half = max_chars // 2
        return (
            text[:half]
            + f"\n\n... [已截断 {len(text) - max_chars} 字符] ...\n\n"
            + text[-half:]
        )

    # =========================================================
    # 对外入口
    # =========================================================

    def run_clinical_reasoning(
        self,
        case_text: str,
        all_info: str = "",
        report_mode: str = "emergency",
        show_thinking: bool = True
    ) -> Generator[dict, None, None]:

        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # ══════════════════════════════════════
            # 意图路由：使用 Qwen-Plus 过滤无关询问，并区分问诊 vs 通用知识
            # ══════════════════════════════════════
            intent_prompt = f"""你是意图分类专家。请判断以下输入的类型：
- consultation: 具体患者问诊或病例分析（包含患者症状、检查等细节）
- knowledge: 脑卒中通用知识询问（如症状、药品作用、禁忌、预防等，无具体患者细节）
- irrelevant: 非脑卒中医疗相关

输入：{case_text}

输出 JSON：
{{
    "type": "consultation/knowledge/irrelevant",
    "reason": "简要原因"
}}

严格区分：如果有患者具体信息，为consultation；如果是一般性问题，为knowledge；否则irrelevant。"""
            logging.info(f"=== 开始意图分类，输入: {case_text[:100]}... ===")
            intent_response = loop.run_until_complete(
                self.llm_critic.ainvoke([HumanMessage(content=intent_prompt)])
            )
            logging.info(f"=== 意图分类原始响应: {intent_response.content} ===")
            intent_result = self._parse_json(intent_response.content, {"type": "irrelevant"})
            logging.info(f"=== 意图分类解析结果: {intent_result} ===")
            intent_type = intent_result.get("type", "irrelevant")
            logging.info(f"=== 最终意图类型: {intent_type} ===")

            if intent_type == "irrelevant":
                logging.info("=== 意图被分类为 irrelevant，返回拒绝消息 ===")
                yield {"type": "result", "content": "请提供脑卒中医疗临床相关查询，此输入无关。"}
                return
            elif intent_type == "knowledge":
                logging.info("=== 意图被分类为 knowledge，进入知识问答流程 ===")
                if show_thinking:
                    yield self._emit_thinking(
                        "Intent", "✅ 意图验证：通用知识问题", "使用 Qwen-Max 直接回答"
                    )

                # 使用 qwen-max (假设 llm_proposer 是 qwen-max) 直接回答
                knowledge_prompt = f"""你是三甲医院神经内科主任医师。请基于循证医学知识，直接回答以下脑卒中相关通用问题。
                问题：{case_text}
                
                回答要求：
                - 用中文，简洁专业
                - 禁止确诊语气
                - 禁止具体剂量
                - 如果需要，引用权威指南"""

                knowledge_stream = self.llm_proposer.astream([
                    HumanMessage(content=knowledge_prompt)
                ])

                async def consume_knowledge():
                    async for chunk in knowledge_stream:
                        yield chunk

                agen_knowledge = consume_knowledge()
                while True:
                    try:
                        chunk = loop.run_until_complete(agen_knowledge.__anext__())
                        if isinstance(chunk, str) and chunk:
                            yield {"type": "result", "content": chunk}
                        elif hasattr(chunk, "content") and chunk.content:
                            yield {"type": "result", "content": chunk.content}
                    except StopAsyncIteration:
                        break
                return

            # 如果是 consultation，继续完整流程
            if show_thinking:
                yield self._emit_thinking(
                    "Intent", "✅ 意图验证通过", "输入为问诊相关查询"
                )

            # ══════════════════════════════════════
            # LLM #1: 统一分析（用快速模型）
            # ══════════════════════════════════════
            if show_thinking:
                yield self._emit_thinking(
                    "Step 1", "🏥 病例分析中...",
                    "结构化提取 + 复杂度评估 + 临床问题生成"
                )

            analysis = loop.run_until_complete(
                self._unified_analysis(case_text, all_info)
            )

            context = analysis.get(
                "structured_context", {"原始病例": case_text}
            )
            clinical_questions = analysis.get("clinical_questions", [])
            key_risks = analysis.get("key_risks", [])
            complexity = analysis.get("complexity", "high")

            if not clinical_questions:
                clinical_questions = ["该患者当前最紧急的临床问题和处置要点"]
            clinical_questions = clinical_questions[:MAX_SUB_QUESTIONS]

            if show_thinking:
                yield self._emit_thinking(
                    "Step 1", "✅ 病例分析完成", {
                        "complexity": complexity,
                        "questions": clinical_questions,
                        "key_risks": key_risks
                    }
                )

            yield {
                "type": "meta",
                "content": {
                    "complexity": complexity,
                    "report_mode": report_mode,
                    "key_risks": key_risks
                }
            }

            # ══════════════════════════════════════
            # Step 2: 并行 RAG 检索（0 次 LLM）
            # ══════════════════════════════════════
            if show_thinking:
                yield self._emit_thinking(
                    "Step 2", "🔍 并行证据检索中...",
                    f"检索 {len(clinical_questions)} 个子问题"
                )

            evidence = self.medical_assistant.fast_parallel_retrieve(
                clinical_questions
            )
            # 截断证据，减少后续 token
            evidence_truncated = self._truncate(evidence, MAX_EVIDENCE_CHARS)

            if show_thinking:
                yield self._emit_thinking(
                    "Step 2", "✅ 证据检索完成",
                    f"{len(evidence)} 字符 → 截断为 {len(evidence_truncated)} 字符"
                )

            # ══════════════════════════════════════
            # LLM #2 + #3: Proposer 和 Critic 并行
            # ══════════════════════════════════════
            if show_thinking:
                yield self._emit_thinking(
                    "Step 3", "🧠 Proposer + Critic 并行推理中...",
                    "主任医师推理和质控审查同时进行"
                )

            proposal, critique = loop.run_until_complete(
                self._parallel_propose_and_critique(
                    context, evidence_truncated, all_info
                )
            )

            if show_thinking:
                yield self._emit_thinking(
                    "Step 3a", "✅ Proposer 推理完成",
                    proposal[:800] + "..." if len(proposal) > 800 else proposal
                )
                yield self._emit_thinking(
                    "Step 3b", "✅ Critic 批判完成",
                    critique[:800] + "..." if len(critique) > 800 else critique
                )

            # ══════════════════════════════════════
            # LLM #4: 流式生成最终报告
            # ══════════════════════════════════════
            if show_thinking:
                yield self._emit_thinking(
                    "Step 4",
                    f"📝 生成最终报告 (模式={report_mode})...",
                    "融合推理 + 批判 → 最终临床报告"
                )

            # 截断 proposal 和 critique 减少最终报告输入 token
            proposal_truncated = self._truncate(proposal, MAX_PROPOSAL_CHARS)
            critique_truncated = self._truncate(critique, MAX_CRITIQUE_CHARS)

            final_stream = self.medical_assistant.stream_final_report(
                context=context,
                proposal=proposal_truncated,
                critique=critique_truncated,
                evidence=evidence_truncated,
                all_info=all_info,
                report_mode=report_mode
            )

            async def consume():
                async for chunk in final_stream:
                    yield chunk

            agen = consume()
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    if isinstance(chunk, str) and chunk:
                        yield {"type": "result", "content": chunk}
                    elif hasattr(chunk, "content") and chunk.content:
                        yield {"type": "result", "content": chunk.content}
                except StopAsyncIteration:
                    break

            if show_thinking:
                yield self._emit_thinking(
                    "Done", "✅ 全部完成", "临床推理管线执行完毕"
                )

        except Exception as e:
            logging.error(f"=== 临床推理管线异常: {e} ===")
            logging.error(f"=== 异常类型: {type(e).__name__} ===")
            import traceback
            logging.error(f"=== 详细堆栈: {traceback.format_exc()} ===")
            yield {"type": "error", "content": f"管线异常: {str(e)}"}

        finally:
            if loop:
                loop.close()

    # =========================================================
    # LLM #1: 统一分析（用快速模型，节省 ~5s）
    # =========================================================

    async def _unified_analysis(
        self, case_text: str, all_info: str
    ) -> Dict[str, Any]:

        prompt = f"""你是神经急诊专家。请对以下病例完成三项任务，一次性输出。

【病例】
{case_text}

【历史上下文】
{all_info if all_info else "无"}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "structured_context": {{
        "基本信息": {{"年龄": "", "性别": ""}},
        "起病方式": "",
        "主要症状": [],
        "神经系统查体": {{}},
        "意识水平": "",
        "生命体征": {{}},
        "既往史": [],
        "用药史": [],
        "危险因素": [],
        "非卒中线索": []
    }},
    "complexity": "low/medium/high/critical",
    "key_risks": ["最危险的问题1", "最危险的问题2"],
    "clinical_questions": [
        "需查证的中文临床问题1（30字以内）",
        "需查证的中文临床问题2",
        "需查证的中文临床问题3"
    ]
}}

要求：
- structured_context: 提取所有临床信息
- complexity: critical=危及生命
- clinical_questions: 3个最需要查证的问题，用于检索医学文献，必须用中文"""

        # 用快速模型（qwen-plus），比 qwen-max 快 2-3 倍
        response = await self.llm_critic.ainvoke([
            HumanMessage(content=prompt)
        ])

        result = self._parse_json(response.content, None)
        if result and isinstance(result, dict):
            return result

        return {
            "structured_context": {"原始病例": case_text},
            "complexity": "high",
            "key_risks": [],
            "clinical_questions": ["该患者当前最紧急的临床问题和处置要点"]
        }

    # =========================================================
    # LLM #2 + #3: Proposer 和 Critic 真正并行
    # =========================================================

    async def _parallel_propose_and_critique(
        self,
        context: Dict,
        evidence: str,
        all_info: str
    ) -> tuple:

        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        evidence_str = evidence if evidence else "未检索到相关证据"
        all_info_str = all_info if all_info else "无"

        # Proposer prompt
        proposer_prompt = self._get_prompt(
            "proposer",
            _FALLBACK_PROPOSER,
            context=context_str,
            all_info=all_info_str,
            evidence=evidence_str
        )

        # Critic prompt（预批判模式）
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

对每个风险给出严重程度和建议。请精简输出，重点突出。

请额外输出：

- 当前最可能被忽视但致命的风险（仅1项）
- 若未处理，最可能导致的后果
- 建议优先级
"""

        # asyncio.gather 真正并行
        proposer_task = self.llm_proposer.ainvoke([
            HumanMessage(content=proposer_prompt)
        ])
        critic_task = self.llm_critic.ainvoke([
            HumanMessage(content=pre_critic_prompt)
        ])

        proposer_resp, critic_resp = await asyncio.gather(
            proposer_task, critic_task
        )

        return proposer_resp.content, critic_resp.content


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