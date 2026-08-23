# 证据合成服务：把检索到的医学证据与临床问题一起交给 LLM，生成循证医学总结；
# 未配置 prompt 管理器时回退到类内 FALLBACK_PROMPT。
from langchain_core.messages import HumanMessage, SystemMessage


# 证据合成服务：将临床问题 + 检索证据合成为循证医学总结文本。
class EvidenceSynthesisService:

    FALLBACK_PROMPT = """你是循证医学专家。

临床问题：{question}

医学证据：
{evidence}

请进行循证医学总结。"""

    def __init__(
        self,
        llm,
        prompt_manager=None
    ):
        # llm：负责合成的模型；prompts：提示词管理器，可为空（空时走回退模板）
        self.llm = llm
        self.prompts = prompt_manager

    def synthesize(
        self,
        question: str,
        evidence: str
    ) -> str:

        prompt = None

        if self.prompts:
            prompt = self.prompts.get(
                "evidence_synthesis",
                question=question,
                evidence=evidence
            )

        if not prompt:
            prompt = self.FALLBACK_PROMPT.format(
                question=question,
                evidence=evidence
            )

        response = self.llm.invoke([
            SystemMessage(content="你是循证医学专家"),
            HumanMessage(content=prompt)
        ])

        return response.content