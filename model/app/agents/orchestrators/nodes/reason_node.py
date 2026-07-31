"""
临床推理节点 - 多专家独立立场生成模块

功能说明：
- 负责多专家并行形成独立、可引用证据的初始意见
- 采用"多Agent协作 + 意见综合"的架构模式
- 实现了类似医疗会诊的多专家协同决策机制

工作流程：
1. 并行调用多位专家进行独立推理
2. 收集各专家意见，交由后续 DebateNode 和 ConsensusNode 处理

设计模式：
- 并行执行模式：多位专家同时推理，提高效率
- 反思机制：支持基于校验反馈的重新推理
- 动态配置模式：专家角色和职责可配置化
"""

import logging
import asyncio
from typing import Dict
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from langchain_core.messages import HumanMessage, SystemMessage
from app.config.config_loader import get_expert_manager
from app.agents.utils.text_utils import format_numbered_questions

logger = logging.getLogger(__name__)


class ReasonNode(BaseNode):
    """
    临床推理节点（中层：领域专家独立立场）

    职责：
    - 协调多专家并行推理
    - 为后续交叉质询保留独立观点和证据依据

    输入状态：
    - case_text: 患者病例文本
    - all_info: 历史上下文信息
    - evidence: 检索到的医学证据
    - validation_feedback: 之前的校验反馈（用于反思）

    输出状态：
    - expert_opinions: 按专家角色组织的独立建议
    - 以及各专家的独立建议（兼容旧事件摘要）

    特色功能：
    - 动态专家配置：从配置文件加载专家角色和职责
    - 专家启用/禁用：支持选择性启用特定专家
    - 可扩展架构：易于添加新的专家角色
    """

    def __init__(self, llm, expert_config=None):
        """
        初始化推理节点

        参数：
        - llm: 底层大语言模型，用于专家推理和意见综合
        - expert_config: 专家配置管理器（可选，默认使用全局单例）
        """
        self.llm = llm
        self.expert_manager = expert_config or get_expert_manager()
        
        # 加载专家配置
        self.experts = self.expert_manager.get_experts()
        
        logger.info(f"[reason] 已加载 {len(self.experts)} 位专家配置")
        for expert in self.experts:
            logger.info(f"  - {expert.get('role')} (优先级: {expert.get('priority', 'N/A')})")

    async def run(self, state: ClinicalState) -> Dict:
        """
        执行多专家并行推理

        工作流程：
        1. 构建病例信息上下文（包含历史反馈）
        2. 并行调用多位专家进行推理
        3. 综合专家意见生成最终提案和批判
        4. 返回结构化结果

        参数：
        - state: 临床状态对象，包含病例信息、上下文、证据等

        返回：
        - Dict: 包含各专家建议和综合结果的字典
        """
        logger.info(f"[reason] 开始执行推理节点")
        logger.info(f"[reason] 病例文本长度: {len(state['case_text'])}")
        logger.info(f"[reason] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[reason] 反思次数: {state['reflection_count']}")
        
        # 步骤1: 构建完整的病例上下文信息
        memory_context = state.get("active_memory") or state.get("all_info", "")
        case_info = (
            f"病例：{state['case_text']}\n"
            f"患者记忆：{memory_context}\n"
            f"检索证据：{state['evidence']}\n"
            f"证据质量：{state.get('evidence_quality', 0.0):.2f}\n"
            f"证据评估：{state.get('evidence_assessment', '')}"
        )

        questions_text = format_numbered_questions(state.get("user_questions", []))
        if questions_text:
            case_info += (
                "\n\n【用户原始问题】\n"
                f"{questions_text}\n"
                "独立意见必须逐项覆盖这些问题；即使反对某项处置，也要给出直接结论和理由。"
            )
        
        # 如果存在之前的校验反馈，添加到上下文中用于反思
        if state['validation_feedback']:
            case_info += f"\n\n【之前被驳回的反馈，请反思】：{state['validation_feedback']}"
            logger.info(f"[reason] 存在校验反馈，进入反思模式")
        
        logger.info(f"[reason] 开启多专家并行推理 (Reflection Count: {state['reflection_count']})")
        
        # 步骤2: 动态创建专家任务并并行执行
        # 使用asyncio.gather实现真正的并行推理，提高效率
        tasks = []
        expert_roles = []
        
        for expert in self.experts:
            role = expert.get("role")
            instruction = expert.get("instruction")
            expert_roles.append(role)
            
            tasks.append(self._ask_expert(role, instruction, case_info))
        
        logger.info(f"[reason] 已创建 {len(tasks)} 个专家推理任务")
        
        # 并行执行所有专家推理任务
        results = await asyncio.gather(*tasks)
        
        logger.info(f"[reason] 专家推理完成，收到 {len(results)} 个结果")
        
        # 构建专家建议字典
        expert_advices = {}
        legacy_role_fields = {}
        successful_experts = 0
        for role, advice in zip(expert_roles, results):
            expert_advices[role] = advice
            if "全科" in role:
                legacy_role_fields["generalist_advice"] = advice
            elif "神经" in role:
                legacy_role_fields["specialist_advice"] = advice
            elif "药师" in role:
                legacy_role_fields["pharmacist_advice"] = advice
            if advice and not advice.startswith("未能获取"):
                successful_experts += 1
                logger.info(f"[reason] {role} 推理成功，建议长度: {len(advice)}")
            else:
                logger.warning(f"[reason] {role} 推理失败或返回空结果")
        
        logger.info(f"[reason] 成功推理专家数: {successful_experts}/{len(expert_roles)}")
        
        # 后续节点会让专家互相质询，再由主持人形成共识。
        result = {"expert_opinions": expert_advices}
        
        # 添加各专家的独立建议
        result.update(legacy_role_fields)
        
        logger.info("[reason] 独立专家意见生成完成，进入交叉质询")
        return result

    async def _ask_expert(self, role: str, instruction: str, case_info: str) -> str:
        """
        向单个专家咨询意见

        参数：
        - role: 专家角色名称（如"全科医生"、"神经专科医生"等）
        - instruction: 专家的具体任务指令
        - case_info: 病例信息上下文

        返回：
        - str: 专家的建议意见

        异常处理：
        - 如果专家推理失败，返回错误信息并记录日志
        """
        # 获取专家的系统提示词
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = expert_config.get("system_prompt", f"你是专业的{role}") if expert_config else f"你是专业的{role}"
        
        # 构建专家专用的prompt，包含角色设定和任务指令
        prompt = f"""你目前是【{role}】。
{instruction}

【病历资料】
{case_info}

请形成可供其他专家质询的独立意见：
1. 核心判断与不确定性
2. 支持或反对某项处置的证据
3. 你认为其他专业必须复核的问题

关键医学判断必须尽量引用检索证据中的真实编号，例如【证据 R1-Q1-E1】；不得虚构证据编号。"""
        
        try:
            # 调用LLM进行专家推理
            # SystemMessage设定专家角色，HumanMessage提供具体任务
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt), 
                HumanMessage(content=prompt)
            ])
            return getattr(res, "content", "")
        except Exception as e:
            # 异常处理：记录错误并返回友好的错误信息
            logger.error(f"{role} 推理失败: {e}")
            return f"未能获取{role}建议。"
