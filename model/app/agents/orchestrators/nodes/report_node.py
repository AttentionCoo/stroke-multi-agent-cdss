import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_PROPOSAL_CHARS, MAX_CRITIQUE_CHARS
from app.agents.utils.text_utils import truncate_text

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

        if state['user_questions']:
            logger.info(f"[report] 存在用户问题，直接返回提案")
            report = state['proposal']
            if warning_block:
                report = f"{warning_block}\n\n{report}"
            return {"report": report}

        # 如果没有提案，生成默认报告
        if not state['proposal']:
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
        report_template = self.report_manager.get_template(state['report_mode'])
        prompt_text = report_template.format(
            context=context_str,
            all_info=state.get('active_memory') or state['all_info'] or "无历史记录",
            evidence=evidence_context,
            proposal=truncate_text(state['proposal'], MAX_PROPOSAL_CHARS) or "无",
            critique=truncate_text(state['critique'], MAX_CRITIQUE_CHARS) or "无批判意见",
        )
        
        if warning_block:
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
            report = f"## 临床报告\n\n{state['proposal']}"

        if warning_block and not report.lstrip().startswith("## 安全警告"):
            report = f"{warning_block}\n\n{report}"
        
        logger.info(f"[report] 报告生成完成，长度: {len(report)}, 块数: {chunk_count}")
        return {"report": report}
