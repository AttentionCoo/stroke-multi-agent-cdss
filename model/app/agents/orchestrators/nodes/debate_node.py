"""多专家交叉质询与共识节点。"""

import asyncio
import logging
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.text_utils import format_numbered_questions
from app.config.config_loader import get_expert_manager


logger = logging.getLogger(__name__)


class DebateNode(BaseNode):
    """让每位专家阅读其他专家意见并完成有证据依据的交叉质询。"""

    def __init__(self, llm, expert_config=None):
        self.llm = llm
        self.expert_manager = expert_config or get_expert_manager()
        self.experts = self.expert_manager.get_experts()

    async def run(self, state: ClinicalState) -> Dict:
        opinions = state.get("expert_opinions", {})
        if not opinions:
            return {"debate_transcript": "未获得可供质询的专家意见。"}

        tasks = [self._challenge(expert, state, opinions) for expert in self.experts]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        transcript_parts = []
        for expert, response in zip(self.experts, responses):
            role = expert.get("role", "专家")
            if isinstance(response, Exception):
                logger.warning("%s 交叉质询失败: %s", role, response)
                text = "未能完成本轮交叉质询。"
            else:
                text = response or "未提出补充意见。"
            transcript_parts.append(f"【{role}交叉质询】\n{text}")

        return {"debate_transcript": "\n\n".join(transcript_parts)}

    async def _challenge(self, expert: Dict, state: ClinicalState, opinions: Dict[str, str]) -> str:
        role = expert.get("role", "临床专家")
        questions_text = format_numbered_questions(state.get("user_questions", [])) or "无明确问题清单"
        peer_text = "\n\n".join(
            f"【{peer_role}初始意见】\n{opinion}"
            for peer_role, opinion in opinions.items()
        )
        prompt = f"""你是本次多学科会诊中的{role}。请阅读所有专家的初始意见，完成交叉质询。

【病例】
{state.get('case_text', '')}

【用户原始问题】
{questions_text}

【检索证据】
{state.get('evidence', '')}

【专家初始意见】
{peer_text}

请明确输出：
1. 你同意的判断及理由
2. 你质疑的判断、冲突点或遗漏
3. 你根据其他专家意见修正后的结论
4. 仍需人工确认的不确定性

必须检查意见是否逐项回答了用户原始问题；即使某项处置应被拒绝，也不能用拒绝结论代替对问题本身的回答。
每项医学判断必须尽量引用证据编号，例如【证据 R1-Q1-E1】；不得虚构证据。"""
        response = await self.llm.ainvoke([
            SystemMessage(content=f"你是严谨的{role}，正在参与真实多学科会诊。"),
            HumanMessage(content=prompt),
        ])
        return str(getattr(response, "content", "") or "").strip()


class ConsensusNode(BaseNode):
    """由会诊主持人解决冲突并形成最终共识。"""

    def __init__(self, llm, expert_config=None):
        self.llm = llm
        manager = expert_config or get_expert_manager()
        self.synthesis_config = manager.get_synthesis_config()

    async def run(self, state: ClinicalState) -> Dict:
        questions_text = format_numbered_questions(state.get("user_questions", [])) or "无明确问题清单"
        prompt = f"""你是卒中多学科会诊主持人。请基于独立意见和交叉质询形成可审计共识。

【病例】
{state.get('case_text', '')}

【用户原始问题】
{questions_text}

【患者记忆】
{state.get('active_memory', '')}

【检索证据】
{state.get('evidence', '')}

【证据质量】
{state.get('evidence_quality', 0.0)}；{state.get('evidence_assessment', '')}

【初始专家意见】
{state.get('expert_opinions', {})}

【交叉质询记录】
{state.get('debate_transcript', '')}

请严格使用以下格式：
### CONSENSUS ###
说明已达成的共识、被否决的分歧及原因。
### PROPOSAL ###
按用户原始问题的顺序逐项回答；每项先给直接结论，再说明理由、风险和信息缺口。即使结论是拒绝某项处置，也不得漏答或改答其他问题。关键判断引用真实证据编号。
### CRITIQUE ###
列出证据不足、信息缺口、禁忌证和需要人工裁决的风险。

禁止确诊语气，禁止虚构证据，禁止给出未经个体化核验的具体药物剂量。"""

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是中立、保守、循证的多学科会诊主持人。"),
                HumanMessage(content=prompt),
            ])
            content = str(getattr(response, "content", "") or "").strip()
        except Exception as exc:
            logger.error("会诊共识生成失败: %s", exc)
            content = (
                "### CONSENSUS ###\n未能形成稳定共识。\n"
                "### PROPOSAL ###\n建议补充关键信息后由临床团队评估。\n"
                "### CRITIQUE ###\n自动共识生成失败，需要人工复核。"
            )

        consensus, proposal, critique = self._split(content)
        return {
            "consensus": consensus,
            "proposal": proposal,
            "critique": critique,
        }

    @staticmethod
    def _split(content: str) -> tuple[str, str, str]:
        consensus_marker = "### CONSENSUS ###"
        proposal_marker = "### PROPOSAL ###"
        critique_marker = "### CRITIQUE ###"

        consensus = ""
        proposal = ""
        critique = ""
        if consensus_marker in content:
            after_consensus = content.split(consensus_marker, 1)[1]
            consensus = after_consensus.split(proposal_marker, 1)[0].strip()
        if proposal_marker in content:
            after_proposal = content.split(proposal_marker, 1)[1]
            proposal = after_proposal.split(critique_marker, 1)[0].strip()
        if critique_marker in content:
            critique = content.split(critique_marker, 1)[1].strip()

        return (
            consensus or "会诊意见存在分歧，需人工复核。",
            proposal or "建议结合临床资料进一步评估。",
            critique or "当前未生成完整风险审查，需人工复核。",
        )
