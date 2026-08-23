# 查询生成服务：调用 LLM 将临床问题拆解为面向文献数据库的中文检索查询，
# 供 RAG 检索阶段使用；未配置 prompt 管理器时回退到类内 FALLBACK_PROMPT。
import logging
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


# 查询生成服务：把临床问题拆解为最多 2 条中文检索关键词组合，供 RAG 检索阶段使用。
class QueryGenerationService:

    FALLBACK_PROMPT = """你是医学检索专家。
根据以下临床问题生成2个精准中文检索关键词组合。
每行一个。
临床问题：{question}"""

    def __init__(
        self,
        llm,
        prompt_manager=None
    ):
        self.llm = llm
        self.prompts = prompt_manager

    def generate(self, question: str) -> List[str]:
        # 把临床问题拆解为最多 2 条中文检索查询，返回字符串列表

        prompt = None

        if self.prompts:
            prompt = self.prompts.get(
                "search_query_generation",
                question=question
            )

        if not prompt:
            prompt = self.FALLBACK_PROMPT.format(
                question=question
            )

        response = self.llm.invoke([
            SystemMessage(content="你是医学检索专家"),
            HumanMessage(content=prompt)
        ])

        content = response.content

        lines = [
            line.strip()
            for line in content.split("\n")
            if line.strip()
        ]

        # 过滤中文行
        chinese_lines = [
            line for line in lines
            if any('\u4e00' <= c <= '\u9fff' for c in line)
        ]

        candidates = chinese_lines if chinese_lines else lines
        return candidates[:2] if candidates else [question[:50]]