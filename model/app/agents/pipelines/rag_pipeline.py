# RAG 管道：按 查询生成 → 证据检索 → 证据合成 三个阶段组装三大服务，
# 将临床问题转化为结构化证据结论，供 MedicalAssistant 门面层调用。
import logging
from app.agents.services.query_service import QueryGenerationService
from app.agents.services.retrieval_service import EvidenceRetrievalService
from app.agents.services.synthesis_service import EvidenceSynthesisService

logger = logging.getLogger(__name__)


# 将查询生成、证据检索、证据合成三个服务按顺序串联为一条 RAG 流水线。
class RAGPipeline:
    """RAG 管道，组装查询生成、证据检索、证据合成服务"""

    def __init__(
        self,
        query_gen: QueryGenerationService,
        retrieval: EvidenceRetrievalService,
        synthesis: EvidenceSynthesisService
    ):
        # 注入三大服务：查询生成（拆解问题）、证据检索（并行召回）、证据合成（归纳结论）
        self.query_gen = query_gen
        self.retrieval = retrieval
        self.synthesis = synthesis

    def run(self, question: str) -> str:
        """执行 RAG 管道"""
        try:
            logger.info(f"RAG 管道启动: {question[:60]}")
            
            # 1. 生成检索查询
            queries = self.query_gen.generate(question)
            logger.info(f"已生成检索查询: {queries}")
            
            # 2. 并行检索证据
            evidence = self.retrieval.parallel_retrieve(queries)
            if not evidence:
                return "未检索到相关医学文献。"
            
            # 3. 合成证据
            result = self.synthesis.synthesize(question, evidence)
            logger.info("RAG 管道执行完成")
            
            return result
            
        except Exception as e:
            logger.error(f"RAG 管道异常: {e}")
            return "证据层运行异常。"
