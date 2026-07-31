import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_PROPOSAL_CHARS, MAX_CRITIQUE_CHARS
from app.agents.utils.text_utils import format_numbered_questions, truncate_text

logger = logging.getLogger(__name__)


class ReportNode(BaseNode):
    """报告生成节点"""

    def __init__(self, llm_proposer, report_manager):
        self.llm_proposer = llm_proposer
        self.report_manager = report_manager

    async def run(self, state: ClinicalState) -> Dict:
        logger.info(f"[report] 开始执行报告生成节点")
        logger.info(f"[report] 报告模式: {state['report_mode']}")
        logger.info(f"[report] 提案长度: {len(state['proposal']) if state['proposal'] else 0}")
        logger.info(f"[report] 批判长度: {len(state['critique']) if state['critique'] else 0}")
        logger.info(f"[report] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[report] 校验状态: {state['validation_passed']}")
        logger.info(f"[report] 反思次数: {state['reflection_count']}")
        logger.info(f"[report] 校验反馈: {state['validation_feedback'][:100] if state['validation_feedback'] else '无'}")

        warning_block = ""
        if not state['validation_passed'] and state['validation_feedback']:
            warning_block = (
                "## 安全警告\n\n"
                f"{state['validation_feedback']}\n\n"
                "该方案未通过全部自动质控，必须由临床医生人工复核。"
            )

        user_questions = state.get('user_questions') or []

        # 没有明确问题且没有提案时，生成默认报告
        if not user_questions and not state['proposal']:
            logger.warning(f"[report] 没有提案，生成默认报告")
            default_report = f"""## 临床分析报告

### 患者情况
{state['case_text']}

### 分析结果
系统已完成初步分析，但未能生成具体的治疗提案。

### 可能原因
- 检测到潜在的禁忌症或风险因素
- 需要进一步的临床评估
- 建议咨询专业医师进行详细评估

### 建议
请提供更详细的临床信息，或咨询专业医师进行评估。
"""
            if warning_block:
                default_report = f"{warning_block}\n\n{default_report}"
            return {"report": default_report}

        context_str = (
            json.dumps(state['context'], ensure_ascii=False, indent=2)
            if isinstance(state['context'], dict) else str(state['context'])
        )
        
        logger.info(f"[report] 上下文长度: {len(context_str)}")
        
        evidence_context = (
            f"证据质量评分：{state.get('evidence_quality', 0.0):.2f}\n"
            f"证据评估：{state.get('evidence_assessment', '未评估')}\n\n"
            f"{state['evidence'] or '未检索到相关证据'}"
        )
        if user_questions:
            questions_text = format_numbered_questions(user_questions)
            validation_context = (
                truncate_text(state.get('validation_feedback', ''), MAX_CRITIQUE_CHARS)
                if not state.get('validation_passed', False)
                else "自动质控已通过"
            ) or "自动质控未提供具体反馈"
            prompt_text = f"""你需要直接回答用户针对病例提出的原始问题。

【用户原始问题】
{questions_text}

【患者结构化信息】
{context_str}

【历史上下文记忆】
{state.get('active_memory') or state.get('all_info') or '无历史记录'}

【循证检索证据】
{evidence_context}

【多学科会诊提案】
{truncate_text(state.get('proposal', ''), MAX_PROPOSAL_CHARS) or '未形成稳定提案'}

【批判性审查意见】
{truncate_text(state.get('critique', ''), MAX_CRITIQUE_CHARS) or '无批判意见'}

【自动质控反馈，仅用于修正答案】
{validation_context}

请严格遵守以下回答契约：
1. 按【用户原始问题】的顺序逐项回答，每个问题都必须有直接结论和理由。
2. 每节使用“### 问题N：原问题”作为标题，不得合并、遗漏或改写问题含义。
3. 即使某项治疗建议被拒绝、证据不足或需要人工复核，也必须先回答该问题，再说明拒绝原因、信息缺口和可行的下一步。
4. 不得用 REJECT、安全警告、免责声明或内部质控过程代替对问题的回答。
5. 只回答原问题需要的内容，不扩展无关章节；不得虚构证据或给出未经个体化核验的具体药物剂量。
6. 正文不要输出“安全警告”章节，系统会在答案末尾追加必要的复核提示。"""
        else:
            report_template = self.report_manager.get_template(state['report_mode'])
            prompt_text = report_template.format(
                context=context_str,
                all_info=state.get('active_memory') or state['all_info'] or "无历史记录",
                evidence=evidence_context,
                proposal=truncate_text(state['proposal'], MAX_PROPOSAL_CHARS) or "无",
                critique=truncate_text(state['critique'], MAX_CRITIQUE_CHARS) or "无批判意见",
            )

        if warning_block and not user_questions:
            prompt_text = (
                "以下自动会诊未通过全部质控。最终报告必须首先完整保留安全警告，"
                "不得弱化或省略：\n\n"
                f"{warning_block}\n\n{prompt_text}"
            )
        
        logger.info(f"[report] Prompt长度: {len(prompt_text)}")
        logger.info(f"[report] 开始生成报告")
        
        messages = [
            SystemMessage(content=self.report_manager.system_role),
            HumanMessage(content=prompt_text),
        ]
        report = ""
        chunk_count = 0
        try:
            async for chunk in self.llm_proposer.astream(messages):
                c = chunk.content if hasattr(chunk, "content") else str(chunk)
                report += c
                chunk_count += 1
        except Exception as e:
            logger.error(f"[report] 报告生成失败: {type(e).__name__} - {str(e)}")
            # 如果生成失败，返回提案本身
            if user_questions:
                report = f"## 针对原问题的综合答复\n\n{state.get('proposal') or '暂未形成可用答复。'}"
            else:
                report = f"## 临床报告\n\n{state['proposal']}"

        if warning_block:
            if user_questions:
                report = f"{report.rstrip()}\n\n{warning_block}"
            elif not report.lstrip().startswith("## 安全警告"):
                report = f"{warning_block}\n\n{report}"
        
        logger.info(f"[report] 报告生成完成，长度: {len(report)}, 块数: {chunk_count}")
        return {"report": report}
