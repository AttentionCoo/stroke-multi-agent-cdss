"""
意图分类节点 - 用户输入类型识别模块

功能说明：
- 作为临床推理图的入口节点，负责识别用户输入的意图类型
- 根据输入内容路由到不同的处理流程
- 实现了类似医疗分诊的意图识别机制

工作流程：
1. 接收用户输入文本
2. 通过LLM判断输入类型（问诊/知识/无关）
3. 返回意图类型用于后续路由决策

设计模式：
- 分类器模式：将输入映射到预定义的类别
- 路由模式：为不同类型的输入选择不同的处理路径
"""

import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode, make_structured_runner, try_get_stream_writer
from app.agents.schemas import IntentResult

logger = logging.getLogger(__name__)

# 意图分类的Prompt模板（硬编码，建议移至配置文件）
_INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("human", """你是意图分类专家。请判断以下输入的类型：

- consultation: 具体患者问诊、病例分析，或对历史上下文中该患者的追问（即使本条输入没有重复患者细节）
- knowledge: 脑卒中通用知识询问（如症状、药品作用、禁忌、预防等，无具体患者细节，也未引用历史患者）
- irrelevant: 非脑卒中医疗相关

【历史上下文（同一对话中此前的问答，可能包含该患者信息；无则为"无"）】
{all_info}

输入：{case_text}

输出 JSON：

{{
    "type": "consultation/knowledge/irrelevant",
    "reason": "简要原因"
}}

严格区分：
- 输入包含患者具体信息 → consultation；
- 输入引用历史患者（如"该患者/这个患者/这个病人/此患者/他/她"等指代）且历史上下文含患者信息 → consultation（对该患者的追问，不能因本条缺少患者细节而误判为知识问答）；
- 输入是完全通用的医学问题、未引用任何患者 → knowledge；
- 否则 → irrelevant。""")
])


class IntentNode(BaseNode):
    """
    意图分类节点 - 临床推理图的入口守门人

    职责：
    - 识别用户输入的意图类型
    - 为后续处理提供路由决策依据
    - 过滤无关输入，提高系统效率

    输入状态：
    - case_text: 用户输入的文本内容

    输出状态：
    - intent_type: 意图类型（consultation/knowledge/irrelevant）

    路由规则：
    - consultation → 进入完整临床推理流程
    - knowledge → 直接回答知识问题
    - irrelevant → 拒绝处理
    """

    def __init__(self, llm):
        """
        初始化意图分类节点

        参数：
        - llm: 大语言模型，用于意图分类
        """
        # 构建处理链：Prompt → LLM → 输出解析器(回退路径)
        self.chain = _INTENT_PROMPT | llm | StrOutputParser()
        # 阶段3: 结构化输出快路径(LLM 支持时), 失败自动回退文本解析
        self._structured_runner = make_structured_runner(llm, IntentResult)

    async def run(self, state: ClinicalState) -> Dict:
        """
        执行意图分类

        工作流程：
        1. 优先调用结构化输出(JSON Schema 约束, 无解析脆弱性)
        2. 失败/不支持时回退: 调用LLM进行意图分类 + 解析JSON
        3. 规则兜底: 引用历史患者的追问强制走 consultation(该患者/这个患者等 + 有历史上下文)
        4. 返回意图类型用于路由决策
        """
        case_text = state["case_text"]
        all_info = str(state.get("all_info") or state.get("active_memory") or "").strip()
        messages = _INTENT_PROMPT.format_messages(case_text=case_text, all_info=all_info or "无")

        # ── 快路径: 结构化输出(Literal 校验, 非法枚举自动触发回退) ──
        if self._structured_runner is not None:
            result = None
            try:
                result = await self._structured_runner.ainvoke(messages)
            except Exception as exc:  # noqa: BLE001 - 校验失败/接口异常 → 回退
                logger.warning("[intent] 结构化输出失败, 回退文本解析: %s", exc)
            if isinstance(result, IntentResult):
                intent_type = result.type
                if intent_type != "consultation":
                    intent_type = self._force_consultation(case_text, all_info, intent_type)
                writer = try_get_stream_writer()
                if writer is not None:
                    writer({"node": "intent", "chunk": f"分类: {intent_type} ({result.reason})"})
                logger.info(f"[intent] 结构化分类结果: {intent_type}")
                return {"intent_type": intent_type}

        # ── 回退路径: 流式生成 + JSON 解析(保留原有行为) ──
        pieces = []
        writer = try_get_stream_writer()
        async for piece in self.chain.astream({"case_text": case_text, "all_info": all_info or "无"}):
            if piece:
                pieces.append(str(piece))
                if writer is not None:
                    writer({"node": "intent", "chunk": str(piece)})
        content = "".join(pieces)

        # 解析JSON格式的分类结果
        result = self._parse_json(content)
        intent_type = result.get("type", "irrelevant")
        intent_type = self._force_consultation(case_text, all_info, intent_type)

        # 记录分类结果
        logger.info(f"[intent] 分类结果: {intent_type}")
        return {"intent_type": intent_type}

    @staticmethod
    def _force_consultation(case_text: str, all_info: str, intent_type: str) -> str:
        """规则兜底: 输入引用了历史患者且历史上下文含患者信息时, 强制视为对该患者的追问。"""
        if intent_type == "consultation":
            return intent_type
        if all_info and any(
            ref in case_text for ref in ("该患者", "这个患者", "这个病人", "此患者", "该病人", "他", "她")
        ):
            logger.info("[intent] 检测到对历史患者的追问(有历史上下文), 强制 consultation")
            return "consultation"
        return intent_type

    def _parse_json(self, text: str):
        """
        解析LLM返回的JSON结果

        参数：
        - text: LLM返回的文本内容

        返回：
        - dict: 解析后的JSON对象，解析失败时返回默认值

        异常处理：
        - 如果JSON解析失败，默认返回"irrelevant"类型
        """
        try:
            return json.loads(text)
        except:
            # JSON解析失败，默认返回无关类型
            return {"type": "irrelevant"}