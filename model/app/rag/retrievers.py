import logging
import os
import sys
import hashlib
import time
from typing import List
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from http import HTTPStatus
import dashscope
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

# Monkey-patch chromadb to prevent ONNX embedding function initialization
import sys
import chromadb.utils.embedding_functions as ef_module
original_default = ef_module.DefaultEmbeddingFunction
ef_module.DefaultEmbeddingFunction = lambda: None

from langchain_chroma import Chroma

# Add parent directory to path to absolute imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.rag.data_loader import load_pdfs_from_dir, split_documents
from app.rag.qa_generator import QAGenerator


load_dotenv()
logger = logging.getLogger(__name__)

CONFIG = {
    # 向量库持久化目录:统一使用 /app/chroma_db_unified(容器卷挂载点)
    # __file__ 位于 <root>/app/rag/retrievers.py, 需上溯 3 层到项目根再拼 chroma_db_unified
    "persist_dir": os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "chroma_db_unified",
    ),
    "docs_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "documents"),
    "top_k_per_store": 4,
    "enable_qa_generation": True,
}


class DashScopeEmbeddings(Embeddings):
    def __init__(self, model: str = "text-embedding-v2"):
        self.model = model
        # 防御性加载:确保任何初始化时机都能拿到 API key(不依赖模块导入顺序)
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.error("❌ DASHSCOPE_API_KEY 未设置,embedding 将失败")
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        for i in range(0, len(texts), 25):
            batch = texts[i:i + 25]
            resp = dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )
            if resp.status_code == HTTPStatus.OK:
                for item in resp.output["embeddings"]:
                    result.append(item["embedding"])
            else:
                raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")
        return result

    def embed_query(self, text: str) -> List[float]:
        resp = dashscope.TextEmbedding.call(
            model=self.model,
            input=text,
            api_key=self.api_key,
        )
        if resp.status_code == HTTPStatus.OK:
            return resp.output["embeddings"][0]["embedding"]
        else:
            raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")


class BGEReranker:
    def __init__(self, top_k: int = 5):
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，Rerank 功能已禁用")
        self.top_k = top_k
        self.model = "gte-rerank"
        self.enabled = bool(self.api_key)  # 根据API密钥是否存在决定是否启用

    def rerank(self, query: str, docs: List[Document], top_k: int = None,
               evidence_type: str = None) -> List[Document]:
        if not docs:
            return []

        actual_top_k = top_k if top_k is not None else self.top_k

        # 如果Rerank未启用或API密钥无效，直接返回原始结果
        if not self.enabled:
            logger.info(f"ℹ️  Rerank 功能已禁用，直接返回原始结果")
            return docs[:actual_top_k]

        try:
            doc_contents = [doc.page_content for doc in docs]
            resp = dashscope.TextReRank.call(
                model=self.model,
                query=query,
                documents=doc_contents,
                top_n=actual_top_k,
                return_documents=True,
                api_key=self.api_key,
            )
            if resp.status_code == HTTPStatus.OK:
                reranked = []
                for item in resp.output.results:
                    original_doc = docs[item.index]
                    original_doc.metadata["relevance_score"] = item.relevance_score
                    reranked.append(original_doc)
                # Medical Evidence Score:语义分 + 证据类型匹配 + 指南权威 + 时效 + 人群
                reranked = self._apply_medical_score(reranked, query, evidence_type)
                logger.info(f"✅ Rerank 完成，{len(docs)} → {len(reranked)} 条")
                return reranked[:actual_top_k]
            else:
                logger.warning(f"⚠️  Rerank API 失败 ({resp.code}): {resp.message}，使用原始结果")
                return docs[:actual_top_k]
        except Exception as e:
            logger.warning(f"⚠️  Rerank 异常: {type(e).__name__} - {str(e)}，使用原始结果")
            return docs[:actual_top_k]

    def _apply_medical_score(self, docs: List[Document], query: str,
                             evidence_type: str | None) -> List[Document]:
        """
        Medical Evidence Score 重排(医学化):

        Final Score = 0.35 语义相似度
                    + 0.25 证据类型匹配
                    + 0.20 指南权威
                    + 0.10 时效性
                    + 0.10 人群/主题匹配

        依据 chunk 的 metadata(evidence_type/subtopic/authority/year) 加权,
        淘汰血脂/二级预防等与决策类型不匹配的内容。
        """
        if not docs:
            return docs

        query_lower = query.lower()
        expected_type = (evidence_type or "").strip().lower()

        # 证据类型 → 期望的 metadata evidence_type
        type_map = {
            "treatment": {"guideline", "consensus", "rct", "meta-analysis"},
            "diagnosis": {"guideline", "review", "criteria"},
            "etiology": {"guideline", "review", "criteria"},
            "anatomy": {"textbook"},
            "prognosis": {"guideline", "review"},
            "prevention": {"guideline", "consensus"},
        }
        expected_types = type_map.get(expected_type, set())

        for doc in docs:
            meta = doc.metadata or {}
            score = 0.0
            reasons = []

            # 1. 语义相似度(0.35, 来自 rerank relevance_score 或 RRF)
            semantic = float(meta.get("relevance_score", 0.0) or 0.0)
            score += 0.35 * min(1.0, semantic)

            # 2. 证据类型匹配(0.25)
            ev_type = str(meta.get("evidence_type", "") or "").lower()
            if expected_types and ev_type in expected_types:
                score += 0.25
            elif not expected_types:
                score += 0.15  # 无期望类型时给基础分

            # 3. 指南权威(0.20, authority 3-5 → 0-1)
            authority = int(meta.get("authority", 3) or 3)
            score += 0.20 * min(1.0, (authority - 2) / 3.0)

            # 4. 时效性(0.10, 年份越新越高)
            year = meta.get("year")
            if isinstance(year, int) and year >= 2015:
                score += 0.10 * min(1.0, (year - 2015) / 10.0)
            else:
                score += 0.03

            # 5. 人群/主题匹配(0.10):查询关键词命中 chunk 的 subtopic
            subtopics_raw = meta.get("subtopic", "")
            if isinstance(subtopics_raw, str):
                subtopics = [s.strip() for s in subtopics_raw.split(",") if s.strip()]
            elif isinstance(subtopics_raw, list):
                subtopics = subtopics_raw
            else:
                subtopics = []
            if subtopics:
                matched_kw = sum(1 for s in subtopics if str(s).lower() in query_lower)
                score += 0.10 * min(1.0, matched_kw / 2.0)

            # 淘汰惩罚:与决策类型不匹配的 subtopic 减分
            excluded = {
                "treatment": ["secondary_prevention", "lipid_management"],
                "anatomy": ["secondary_prevention", "lipid_management", "antiplatelet", "anticoagulation"],
                "etiology": ["secondary_prevention", "lipid_management"],
                "diagnosis": ["secondary_prevention", "lipid_management"],
            }.get(expected_type, [])
            if any(s in excluded for s in subtopics):
                score -= 0.3

            doc.metadata["medical_score"] = round(score, 4)
            doc.metadata["score_reasons"] = reasons

        # 按 Medical Evidence Score 降序
        docs.sort(key=lambda d: float(d.metadata.get("medical_score", 0.0)), reverse=True)
        return docs


def build_or_load_vectorstore(chunks, persist_dir: str, enable_qa: bool = False):
    logger.info(f"🔌 [VectorStore] 连接: {persist_dir}")
    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    vectordb = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )
    try:
        count = vectordb._collection.count()
        if count == 0 and chunks:
            docs_to_insert = chunks
            if enable_qa:
                logger.info(f"⚠️ 向量库为空，准备为 {len(chunks)} 条切片生成扩展QA对...")
                qa_gen = QAGenerator()
                qa_docs = qa_gen.generate_qa_for_chunks(chunks)
                docs_to_insert = chunks + qa_docs
                logger.info(f"入库总计：{len(chunks)}条原文 + {len(qa_docs)}条QA对 = {len(docs_to_insert)}条")
            else:
                logger.info(f"⚠️ 向量库为空，写入 {len(chunks)} 条...")

            batch_size = 32
            total_docs = len(docs_to_insert)
            for i in range(0, total_docs, batch_size):
                batch = docs_to_insert[i:i + batch_size]
                try:
                    # 清理 metadata 中的 None 值(Chroma 不接受)
                    for doc in batch:
                        if doc.metadata:
                            doc.metadata = {
                                k: (v if v is not None else "")
                                for k, v in doc.metadata.items()
                            }
                    vectordb.add_documents(documents=batch)
                    current_processed = min(i + batch_size, total_docs)
                    # 每 5 个批次或是最后一批时打印进度
                    if (i // batch_size + 1) % 5 == 0 or current_processed == total_docs:
                        logger.info(f"  ⏳ 正在写入向量库... 已完成: {current_processed} / {total_docs} 条")
                except Exception as e:
                    logger.error(f"❌ 批次写入失败 (起始索引 {i}): {e}")
            logger.info("✅ 向量库写入完成")
        else:
            logger.info(f"✅ 向量库已有 {count} 条数据")
    except Exception as e:
        logger.warning(f"⚠️ 检查向量库状态异常: {e}")
    return vectordb


# 按证据类型路由到的目标类别(与 EVIDENCE_CATEGORY_ROUTING 一致, 供 Multi-Collection 使用)
EVIDENCE_TYPE_TO_CATEGORY = {
    "treatment": ["指南", "专家共识", "规范"],
    "diagnosis": ["指南", "专家共识", "规范"],
    "etiology": ["指南", "专家共识"],
    "anatomy": ["教材"],
    "prognosis": ["指南", "专家共识"],
    "prevention": ["指南", "专家共识", "规范"],
}


class HybridRetriever:
    def __init__(self, vectordb, documents, k=20):
        self.vector_retriever = vectordb.as_retriever(search_kwargs={"k": k})
        self.reranker = BGEReranker(top_k=CONFIG.get("top_k_final", 3))

        if documents and len(documents) > 0:
            self.bm25 = BM25Retriever.from_documents(documents)
            self.bm25.k = k
        else:
            self.bm25 = None
            logger.warning("⚠️ [HybridRetriever] 文档为空，BM25 未初始化")

        self._cache: dict = {}
        self._cache_ttl = 300

    @staticmethod
    def _rrf_merge(ranked_lists: List[List[Document]], k: int = 60) -> List[Document]:
        doc_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for ranked in ranked_lists:
            for rank, doc in enumerate(ranked, start=1):
                key = doc.page_content
                doc_scores[key] = doc_scores.get(key, 0.0) + 1.0 / (k + rank)
                doc_map[key] = doc

        sorted_keys = sorted(doc_scores, key=lambda x: doc_scores[x], reverse=True)
        result = []
        for key in sorted_keys:
            doc = doc_map[key]
            doc.metadata['rrf_score'] = doc_scores[key]
            result.append(doc)
        return result

    def search(self, query: str, top_k_final: int = 3, category_filter: List[str] = None,
               evidence_type: str = None) -> List[Document]:
        """检索。

        Args:
            query: 检索式
            top_k_final: 返回条数
            category_filter: Evidence Router 的类别过滤
                - 提供允许类别列表(如 ['指南']):只检索这些类别的文档
                - 提供排除类别(以 '!' 开头,如 ['!教材']):排除这些类别
            evidence_type: 决策类型(treatment/anatomy/...),用于 Medical Evidence Score
        """
        cache_key = hashlib.md5(f"{query}_{top_k_final}_{category_filter}_{evidence_type}".encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            result, ts = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.info(f"⚡ [Cache Hit] 跳过重复检索: {query[:50]}...")
                return result
            del self._cache[cache_key]

        logger.info(f"🔍 [HybridRetriever] 检索: {query[:60]}... filter={category_filter}")

        v_docs = self.vector_retriever.invoke(query)
        b_docs = self.bm25.invoke(query) if self.bm25 else []

        # Evidence Router:按类别过滤(向量 + BM25 结果)
        if category_filter:
            allow = [c for c in category_filter if not c.startswith("!")]
            exclude = [c[1:] for c in category_filter if c.startswith("!")]
            if allow:
                v_docs = [d for d in v_docs if d.metadata.get("category") in allow]
                b_docs = [d for d in b_docs if d.metadata.get("category") in allow]
            if exclude:
                v_docs = [d for d in v_docs if d.metadata.get("category") not in exclude]
                b_docs = [d for d in b_docs if d.metadata.get("category") not in exclude]

        ranked_lists = [v_docs]
        if b_docs:
            ranked_lists.append(b_docs)

        candidates = HybridRetriever._rrf_merge(ranked_lists, k=60)

        if not candidates:
            logger.warning("⚠️ 检索结果为空")
            self._cache[cache_key] = ([], time.time())
            return []

        rrf_top_k = min(len(candidates), top_k_final * 4)
        candidates = candidates[:rrf_top_k]

        logger.info(f"🔍 RRF 融合 {len(candidates)} 条，开始 rerank...")

        result = self.reranker.rerank(query, candidates, top_k=top_k_final,
                                      evidence_type=evidence_type)

        self._cache[cache_key] = (result, time.time())
        return result

    def clear_cache(self):
        count = len(self._cache)
        self._cache.clear()
        if count > 0:
            logger.info(f"🗑️ [HybridRetriever] 清空 {count} 条检索缓存")


class UnifiedSearchEngine:
    def __init__(self, persist_dir: str, top_k: int, docs_dir=None):
        logger.info("🔧 初始化 UnifiedSearchEngine...")

        self.docs_dir = (
                docs_dir
                or os.getenv("MEDICAL_DOCS_DIR")
                or CONFIG.get("docs_dir", "./data/documents")
        )
        logger.info(f"📂 文档目录: {self.docs_dir}")

        try:
            raw_docs = load_pdfs_from_dir(self.docs_dir)
        except Exception as e:
            logger.error(f"❌ 加载文档失败: {e}")
            raw_docs = []

        self.chunks = split_documents(raw_docs)
        self.vectorstore = build_or_load_vectorstore(
            self.chunks,
            persist_dir,
            enable_qa=bool(CONFIG.get("enable_qa_generation", False))
        )
        self.retriever = HybridRetriever(
            self.vectorstore,
            raw_docs,
            k=CONFIG.get("reranker_initial_k", 8)
        )


    def search(self, query: str, top_k_final: int = 3, category_filter: List[str] = None,
               evidence_type: str = None) -> List[Document]:
        try:
            logger.info(f"🔍 执行检索: {query[:60]}... filter={category_filter}")
            docs = self.retriever.search(query, top_k_final=top_k_final,
                                         category_filter=category_filter, evidence_type=evidence_type)
            logger.info(f"🏆 检索完成，命中 {len(docs)} 条")
            return docs
        except Exception as e:
            logger.error(f"❌ 检索失败: {e}")
            return []

    def clear_cache(self):
        self.retriever.clear_cache()