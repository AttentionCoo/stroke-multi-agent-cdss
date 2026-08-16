import logging
import os
import sys
import re
import hashlib
import time
from typing import List, Dict
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from http import HTTPStatus
import dashscope
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

# Monkey-patch chromadb to prevent ONNX embedding function initialization
# chromadb 1.x 中该模块结构可能变化, patch 失败时静默降级(本项目始终显式传入 embedding_function)
try:
    import chromadb
    import chromadb.utils.embedding_functions as ef_module
    original_default = ef_module.DefaultEmbeddingFunction
    ef_module.DefaultEmbeddingFunction = lambda: None
except Exception:
    pass

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
    # QA 衍生需数百次 LLM 调用, 冷启动耗时长; 默认开启(保持既有行为), 可通过环境变量关闭
    "enable_qa_generation": os.getenv("ENABLE_QA_GENERATION", "true").strip().lower() in ("1", "true", "yes"),
}


class DashScopeEmbeddings(Embeddings):
    """DashScope 文本向量 + 批量缓存(相同文本批不再重复调用 API)。"""

    # 缓存上限: 超过后整体清空(简单 LRU 近似, 避免内存无限增长)
    CACHE_MAX_ENTRIES = 512

    def __init__(self, model: str = "text-embedding-v2"):
        self.model = model
        # 防御性加载:确保任何初始化时机都能拿到 API key(不依赖模块导入顺序)
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.error("❌ DASHSCOPE_API_KEY 未设置,embedding 将失败")
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
        self._cache: dict = {}

    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        resp = dashscope.TextEmbedding.call(
            model=self.model,
            input=batch,
            api_key=self.api_key,
        )
        if resp.status_code != HTTPStatus.OK:
            raise ValueError(f"DashScope embedding 失败: {resp.code} - {resp.message}")
        return [item["embedding"] for item in resp.output["embeddings"]]

    def _cached_batch(self, batch: List[str]) -> List[List[float]]:
        key = tuple(batch)
        if key in self._cache:
            logger.debug("⚡ [EmbeddingCache] 命中 %d 条文本", len(batch))
            return self._cache[key]
        if len(self._cache) >= self.CACHE_MAX_ENTRIES:
            self._cache.clear()
            logger.info("🗑️ [EmbeddingCache] 缓存满(%d), 已清空", self.CACHE_MAX_ENTRIES)
        result = self._embed_batch(batch)
        self._cache[key] = result
        return result

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = []
        for i in range(0, len(texts), 25):
            batch = texts[i:i + 25]
            result.extend(self._cached_batch(batch))
        return result

    def embed_query(self, text: str) -> List[float]:
        return self._cached_batch([text])[0]

    def clear_cache(self):
        self._cache.clear()


class BGEReranker:
    def __init__(self, top_k: int = 5):
        load_dotenv()
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，Rerank 功能已禁用")
        self.top_k = top_k
        self.model = "gte-rerank"
        self.enabled = bool(self.api_key)  # 根据API密钥是否存在决定是否启用

    @staticmethod
    def _normalize_rrf_to_relevance(docs: List[Document]) -> List[Document]:
        """Rerank API 不可用时的回退: 将 RRF score 归一化为 relevance_score(0-1)。

        使 _apply_medical_score 的语义分项在无 API 时仍然有区分度。
        """
        scores = [float(d.metadata.get("rrf_score", 0.0) or 0.0) for d in docs]
        max_s = max(scores) if scores else 1.0
        if max_s <= 0:
            max_s = 1.0
        for d, s in zip(docs, scores):
            d.metadata["relevance_score"] = round(s / max_s, 4)
        return docs

    @staticmethod
    def _mark_layer(docs: List[Document], layer: str) -> None:
        """降级链标记: 记录本次重排实际使用的层级, 供检索质量看板/日志追溯。"""
        for d in docs:
            d.metadata["rerank_layer"] = layer

    def _fallback_medical_rank(self, docs: List[Document], query: str,
                               evidence_type: str | None,
                               actual_top_k: int) -> List[Document]:
        """Rerank 不可用时的回退: RRF 归一化 + Medical Evidence Score 规则排序。

        Medical Evidence Score 是纯规则加权(证据类型/权威/时效/主题/干预匹配),
        不依赖外部 API, 保证即使 gte-rerank 失败, 排序也不退化为纯 embedding 相似度。
        """
        self._normalize_rrf_to_relevance(docs)
        reranked = self._apply_medical_score(docs, query, evidence_type)
        self._mark_layer(reranked, "rule_fallback")
        logger.info(f"⚠️ 使用规则回退排序(无 Rerank API): {len(docs)} → {len(reranked)} 条")
        return reranked[:actual_top_k]

    def rerank(self, query: str, docs: List[Document], top_k: int = None,
               evidence_type: str = None) -> List[Document]:
        if not docs:
            return []

        actual_top_k = top_k if top_k is not None else self.top_k

        # 如果Rerank未启用或API密钥无效，用规则回退排序(而非原始顺序)
        if not self.enabled:
            logger.info(f"ℹ️  Rerank 功能已禁用，使用规则回退排序")
            return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)

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
                self._mark_layer(reranked, "gte_api")
                logger.info(f"✅ Rerank 完成，{len(docs)} → {len(reranked)} 条")
                return reranked[:actual_top_k]
            elif resp.code == "Throttling.RateQuota":
                # 限流: 退避重试一次(并行检索打爆配额时常见)
                logger.warning(f"⚠️  Rerank 限流 ({resp.message})，1s 后重试一次")
                time.sleep(1)
                try:
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
                        reranked = self._apply_medical_score(reranked, query, evidence_type)
                        self._mark_layer(reranked, "gte_api")
                        logger.info(f"✅ Rerank 重试成功，{len(docs)} → {len(reranked)} 条")
                        return reranked[:actual_top_k]
                except Exception as e2:
                    logger.warning(f"⚠️  Rerank 重试异常: {type(e2).__name__} - {e2}")
                logger.warning(f"⚠️  Rerank 限流重试仍失败，使用规则回退排序")
                return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)
            else:
                logger.warning(f"⚠️  Rerank API 失败 ({resp.code}): {resp.message}，使用规则回退排序")
                return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)
        except Exception as e:
            logger.warning(f"⚠️  Rerank 异常: {type(e).__name__} - {str(e)}，使用规则回退排序")
            return self._fallback_medical_rank(docs, query, evidence_type, actual_top_k)

    def _apply_medical_score(self, docs: List[Document], query: str,
                             evidence_type: str | None) -> List[Document]:
        """
        Medical Evidence Score 重排(医学化):

        Final Score = 0.20 语义相似度
                    + 0.15 证据类型匹配
                    + 0.10 指南权威
                    + 0.10 证据等级(evidence_level A/B/C)
                    + 0.10 时效性
                    + 0.10 主题(subtopic)匹配
                    + 0.10 决策节点(decision_node)匹配
                    + 0.10 干预(intervention)匹配
                    + 0.05 时间窗(time_window)匹配
                    − 0.30 不匹配 subtopic 惩罚

        依据 chunk 的 metadata(evidence_type/subtopic/decision_node/
        intervention/time_window/evidence_level/authority/year) 加权。
        决策节点/干预/时间窗匹配保证"IV alteplase 4.5h"查询优先召回
        对应决策与时限的证据, 而非仅 embedding 相似的其他指南段落。
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

        # 干预/决策节点/时间窗 标签 → 关键词(别名匹配, 如 query "rt-pa" 命中标签 alteplase)
        from app.rag.data_loader import INTERVENTION_RULES, DECISION_NODE_RULES, TIME_WINDOW_RULES
        intervention_kws = {label: kws for label, kws in INTERVENTION_RULES}
        decision_node_kws = {label: kws for label, kws in DECISION_NODE_RULES}
        time_window_kws = {label: kws for label, kws in TIME_WINDOW_RULES}

        def _label_list(raw) -> List[str]:
            if isinstance(raw, str):
                return [s.strip() for s in raw.split(",") if s.strip()]
            if isinstance(raw, list):
                return [str(s).strip() for s in raw if str(s).strip()]
            return []

        def _labels_match(labels: List[str], kws_map: dict) -> int:
            """标签或其别名关键词命中查询的次数。"""
            matched = 0
            for label in labels:
                if label in query_lower:
                    matched += 1
                elif any(str(kw).lower() in query_lower for kw in kws_map.get(label, [])):
                    matched += 1
            return matched

        for doc in docs:
            meta = doc.metadata or {}
            score = 0.0
            reasons = []

            # 1. 语义相似度(0.20, 来自 rerank relevance_score 或 RRF 归一化)
            semantic = float(meta.get("relevance_score", 0.0) or 0.0)
            score += 0.20 * min(1.0, semantic)

            # 2. 证据类型匹配(0.15)
            ev_type = str(meta.get("evidence_type", "") or "").lower()
            if expected_types and ev_type in expected_types:
                score += 0.15
            elif not expected_types:
                score += 0.09  # 无期望类型时给基础分

            # 3. 指南权威(0.10, authority 3-5 → 0-1)
            authority = int(meta.get("authority", 3) or 3)
            score += 0.10 * min(1.0, (authority - 2) / 3.0)

            # 4. 证据等级(0.10, A/B/C/NA)
            ev_level = str(meta.get("evidence_level", "") or "").upper()
            score += {"A": 0.10, "B": 0.05, "C": 0.02}.get(ev_level, 0.02)

            # 5. 时效性(0.10, 年份越新越高)
            year = meta.get("year")
            if isinstance(year, int) and year >= 2015:
                score += 0.10 * min(1.0, (year - 2015) / 10.0)
            else:
                score += 0.03

            # 6. 主题匹配(0.10):查询关键词命中 chunk 的 subtopic
            subtopics = _label_list(meta.get("subtopic"))
            if subtopics:
                matched_kw = sum(1 for s in subtopics if str(s).lower() in query_lower)
                score += 0.10 * min(1.0, matched_kw / 2.0)

            # 7. 决策节点匹配(0.10)
            decision_nodes = _label_list(meta.get("decision_node"))
            if decision_nodes:
                score += 0.10 * min(1.0, _labels_match(decision_nodes, decision_node_kws))

            # 8. 干预匹配(0.10)
            interventions = _label_list(meta.get("intervention"))
            if interventions:
                score += 0.10 * min(1.0, _labels_match(interventions, intervention_kws))

            # 9. 时间窗匹配(0.05):查询提及时间窗且 chunk 标签一致(数字边界防误判)
            time_windows = _label_list(meta.get("time_window"))
            if time_windows:
                from app.rag.data_loader import time_window_hit
                matched_window = 0
                for label in time_windows:
                    if label in query_lower or time_window_hit(
                            query_lower, time_window_kws.get(label, [])):
                        matched_window = 1
                        break
                score += 0.05 * matched_window

            # 10. 临床意图匹配(evidence_type → 期望 clinical_intent)
            #     LLM 语义标签: 高压氧(treatment)在 etiology 查询时应减分;
            #     "general"(泛化意图)不惩罚, 避免有标签 chunk 系统性吃亏
            intent = str(meta.get("clinical_intent", "") or "").strip().lower()
            if intent and intent != "general":
                expected_intents = {
                    "treatment": {"treatment", "management", "intervention", "rehabilitation"},
                    "etiology": {"classification", "etiology", "diagnosis"},
                    "anatomy": {"localization", "anatomy"},
                    "prevention": {"prevention", "secondary_prevention"},
                    "diagnosis": {"diagnosis", "assessment", "classification"},
                }.get(expected_type, set())
                if expected_intents and intent in expected_intents:
                    score += 0.10
                elif expected_intents:
                    score -= 0.10

            # 淘汰惩罚:仅当 chunk 的所有 subtopic 均为不匹配主题时减分
            # (避免 "thrombolysis,lipid_management" 这类含相关主题的 chunk 被误杀)
            excluded = {
                "treatment": ["secondary_prevention", "lipid_management"],
                "anatomy": ["secondary_prevention", "lipid_management", "antiplatelet", "anticoagulation"],
                "etiology": ["secondary_prevention", "lipid_management"],
                "diagnosis": ["secondary_prevention", "lipid_management"],
            }.get(expected_type, [])
            if subtopics and excluded and all(s in excluded for s in subtopics):
                score -= 0.3

            doc.metadata["medical_score"] = round(score, 4)
            doc.metadata["score_reasons"] = reasons

        # 按 Medical Evidence Score 降序
        docs.sort(key=lambda d: float(d.metadata.get("medical_score", 0.0)), reverse=True)
        return docs


def _clean_bm25_query(query: str) -> str:
    """BM25 词袋清洗: 去除布尔语法(引号/括号/独立 AND/OR/NOT), 保留医学词。

    translate_query 生成的 PICO 式(如 ("mca" OR "middle cerebral artery"))对
    embedding 有效, 但 BM25 会把引号括号当字面 token, 导致召回退化。
    仅剥离前后有空白的 AND/OR/NOT(布尔连接词), 避免误删医学缩写
    如比值比 "OR=1.5, 95%CI"。
    """
    cleaned = re.sub(r'["()]', ' ', query)
    cleaned = re.sub(r'\s+(?:AND|OR|NOT)\s+', ' ', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', cleaned).strip()


def _default_bm25_tokenize(text: str) -> List[str]:
    """与 langchain BM25Retriever 默认预处理等价: 小写 + 空白分词。"""
    return str(text).lower().split()


class BM25RetrieverCompat:
    """langchain-community BM25Retriever 的等价实现(基于 rank_bm25)。

    langchain-community 已 sunset, 本类按原行为(默认空白分词/k 参数/invoke 接口)
    平替, 保证检索结果不变。默认空白分词对中文不敏感, 中文分词增强在阶段2单独做。
    """

    def __init__(self, documents: List[Document], k: int = 4):
        self.docs = list(documents)
        self.k = k
        self._corpus = [_default_bm25_tokenize(d.page_content) for d in self.docs]
        self._bm25 = BM25Okapi(self._corpus) if self._corpus else None

    def invoke(self, query: str, **kwargs) -> List[Document]:
        if self._bm25 is None or not query:
            return []
        tokens = _default_bm25_tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # 与 langchain 原版一致: 直接取 top-k, 不过滤非正分(负 IDF 时原版仍返回)
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.k]
        return [self.docs[i] for i in top]


def _add_docs_in_batches(vectordb, docs_to_insert, batch_size: int = 32):
    """批量写入文档到 collection(清理 None metadata, 打印进度)。"""
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


def build_or_load_vectorstore(chunks, persist_dir: str, enable_qa: bool = False,
                              collection_name: str = "langchain"):
    logger.info(f"🔌 [VectorStore] 连接: {persist_dir} collection={collection_name}")
    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    # langchain-chroma 1.x: 显式传入 chromadb 客户端(旧 persist_directory 参数已移除)
    chroma_client = chromadb.PersistentClient(path=persist_dir)
    vectordb = Chroma(
        client=chroma_client,
        embedding_function=embeddings,
        collection_name=collection_name,
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

            _add_docs_in_batches(vectordb, docs_to_insert)
            logger.info("✅ 向量库写入完成")
        else:
            logger.info(f"✅ 向量库已有 {count} 条数据")
    except Exception as e:
        logger.warning(f"⚠️ 检查向量库状态异常: {e}")
    return vectordb


def build_multi_collection_vectorstores(chunks, persist_dir: str, enable_qa: bool = False):
    """构建/加载 5 个主题隔离的 collection(Multi-Collection 架构)。

    chunks 按 route_collection 分桶;每个 collection 独立判断是否为空,
    为空则写入对应桶(可为桶内 chunks 生成 QA 对,QA 对继承桶内 subtopic)。
    返回 {collection_key: Chroma}。
    """
    embeddings = DashScopeEmbeddings(model="text-embedding-v2")
    buckets = bucket_chunks_by_collection(chunks)
    stores = {}
    chroma_client = chromadb.PersistentClient(path=persist_dir)
    for key in COLLECTION_KEYS:
        docs = buckets.get(key, [])
        name = COLLECTION_NAMES[key]
        logger.info(f"🔌 [VectorStore] 连接: {persist_dir} collection={name} (待入库 {len(docs)} 条)")
        vectordb = Chroma(
            client=chroma_client,
            embedding_function=embeddings,
            collection_name=name,
        )
        try:
            count = vectordb._collection.count()
        except Exception as e:
            logger.warning(f"⚠️ 检查 collection {name} 状态异常: {e}")
            count = 0
        if count == 0 and docs:
            docs_to_insert = docs
            if enable_qa:
                logger.info(f"  ⚠️ {name} 为空, 为 {len(docs)} 条切片生成扩展QA对...")
                qa_docs = QAGenerator().generate_qa_for_chunks(docs)
                docs_to_insert = docs + qa_docs
                logger.info(f"  📦 {name} 入库总计: {len(docs)}条原文 + {len(qa_docs)}条QA对 = {len(docs_to_insert)}条")
            else:
                logger.info(f"  ⚠️ {name} 为空, 写入 {len(docs)} 条...")
            _add_docs_in_batches(vectordb, docs_to_insert)
            logger.info(f"  ✅ {name} 写入完成")
        else:
            logger.info(f"  ✅ {name} 已有 {count} 条数据")
        stores[key] = vectordb
    return stores


# 按证据类型路由到的目标类别(与 EVIDENCE_CATEGORY_ROUTING 一致, 供 Multi-Collection 使用)
EVIDENCE_TYPE_TO_CATEGORY = {
    "treatment": ["指南", "专家共识", "规范"],
    "diagnosis": ["指南", "专家共识", "规范"],
    "etiology": ["指南", "专家共识"],
    "anatomy": ["教材"],
    "prognosis": ["指南", "专家共识"],
    "prevention": ["指南", "专家共识", "规范"],
}

# ============ Multi-Collection 设计 ============
# 将单一 Chroma collection(langchain) 拆分为 5 个主题隔离的 collection:
#   anatomy_collection     解剖教材(Neuroanatomy / MCA syndrome 等)
#   guideline_collection   无明确主题的指南/共识/规范内容(总论、通用诊疗原则等)
#   etiology_collection    病因相关(TOAST 分型 / 影像评估 / LVO)
#   treatment_collection   急性期治疗(溶栓 / 取栓 / 血压管理)
#   prevention_collection  二级预防(抗凝 / 抗血小板 / 血脂 / 复发预防)
# Router(evidence_type) 决定检索哪些 collection,物理隔离避免"血脂指南"等
# 无关内容进入 anatomy/treatment 等检索。
COLLECTION_KEYS = ["anatomy", "guideline", "etiology", "treatment", "prevention"]
COLLECTION_NAMES = {k: f"{k}_collection" for k in COLLECTION_KEYS}

# subtopic 标签 → collection 归属(命中即归;类内按标签顺序取首个)
TREATMENT_SUBTOPICS = {"thrombolysis", "thrombectomy", "blood_pressure"}
PREVENTION_SUBTOPICS = {"anticoagulation", "antiplatelet", "lipid_management", "secondary_prevention"}
ETIOLOGY_SUBTOPICS = {"toast_classification", "lvo_assessment", "imaging"}
# 注意:stroke_identification / nihss_assessment 过于宽泛(指南几乎每页都命中),
# 不作为分桶依据,避免所有指南内容都涌入 etiology_collection。

# 文档类别 → collection(优先级最高)
CATEGORY_TO_COLLECTION = {"教材": "anatomy"}

# LLM 语义 domain → collection(规则无法置信的 chunk 由 LLM 分类决定归属)
# diagnosis 归 etiology(影像/分型内容), rehabilitation 归 treatment(治疗/康复)
DOMAIN_TO_COLLECTION = {
    "etiology": "etiology",
    "treatment": "treatment",
    "prevention": "prevention",
    "anatomy": "anatomy",
    "diagnosis": "etiology",
    "rehabilitation": "treatment",
}


def _extract_subtopics(metadata: dict, content: str = None) -> List[str]:
    """从 metadata.subtopic(逗号分隔字符串)提取主题标签;缺失时从内容关键词提取。

    用于 QA 对等缺少结构化标签的文档,保证迁移与重建归属一致。
    """
    from app.rag.data_loader import SUBTOPIC_RULES
    subtopics = []
    raw = (metadata or {}).get("subtopic", "")
    if isinstance(raw, str):
        subtopics = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list):
        subtopics = [str(s).strip() for s in raw if str(s).strip()]
    if not subtopics and content:
        lower = content.lower()
        for label, kws in SUBTOPIC_RULES:
            if any(str(kw).lower() in lower for kw in kws):
                subtopics.append(label)
    return subtopics


def route_collection(metadata: dict, content: str = None) -> str:
    """按 metadata/content 将 chunk 归属到 collection(物理隔离规则)。

    优先级: 教材 → anatomy; LLM 语义 domain(如有) → 对应 collection;
    治疗主题 → treatment; 病因主题 → etiology; 预防主题 → prevention;
    其余(无主题/宽泛主题) → guideline。
    病因(etiology)优先于预防(prevention): 避免 TOAST 分型等病因内容
    被同 chunk 的二级预防标签抢归到 prevention_collection。
    """
    meta = metadata or {}
    category = str(meta.get("category", "") or "")
    if category in CATEGORY_TO_COLLECTION:
        return CATEGORY_TO_COLLECTION[category]

    # LLM 语义标签优先(仅对 LLM 标注过的 chunk 生效)
    domain = str(meta.get("domain", "") or "").strip().lower()
    if domain in DOMAIN_TO_COLLECTION:
        return DOMAIN_TO_COLLECTION[domain]

    subtopics = _extract_subtopics(meta, content)
    for label in subtopics:
        if label in TREATMENT_SUBTOPICS:
            return "treatment"
    for label in subtopics:
        if label in ETIOLOGY_SUBTOPICS:
            return "etiology"
    for label in subtopics:
        if label in PREVENTION_SUBTOPICS:
            return "prevention"
    return "guideline"


def bucket_chunks_by_collection(chunks: List[Document]) -> Dict[str, List[Document]]:
    """按归属规则将 chunks 分桶到各 collection(保留原始顺序)。"""
    buckets = {key: [] for key in COLLECTION_KEYS}
    for doc in chunks:
        key = route_collection(doc.metadata or {}, doc.page_content)
        buckets.setdefault(key, []).append(doc)
    return buckets


class HybridRetriever:
    def __init__(self, vectordb, documents, k=20):
        self.vector_retriever = vectordb.as_retriever(search_kwargs={"k": k})
        self.reranker = BGEReranker(top_k=CONFIG.get("top_k_final", 3))

        if documents and len(documents) > 0:
            self.bm25 = BM25RetrieverCompat(documents, k=k)
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

    def _raw_candidates(self, query: str, k: int = None,
                        category_filter: List[str] = None) -> List[Document]:
        """单 collection 的原始候选: 向量 + BM25 双路检索, 按类别过滤后 RRF 融合。

        k: 每路召回条数(默认用构造时的 k)。供跨 collection 汇总时复用。
        """
        if k is None:
            k = self.vector_retriever.search_kwargs.get("k", 20)
        v_docs = self.vector_retriever.invoke(query)
        # BM25 不解析布尔语法(引号/括号/AND/OR), 用词袋形式检索
        b_docs = self.bm25.invoke(_clean_bm25_query(query)) if self.bm25 else []

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
        if k:
            candidates = candidates[:k]
        return candidates

    def search(self, query: str, top_k_final: int = 3, category_filter: List[str] = None,
               evidence_type: str = None, collections: List[str] = None) -> List[Document]:
        """检索(单 collection 语义, 兼容旧接口)。

        Args:
            query: 检索式
            top_k_final: 返回条数
            category_filter: Evidence Router 的类别过滤
                - 提供允许类别列表(如 ['指南']):只检索这些类别的文档
                - 提供排除类别(以 '!' 开头,如 ['!教材']):排除这些类别
            evidence_type: 决策类型(treatment/anatomy/...),用于 Medical Evidence Score
            collections: Multi-Collection 路由参数; 本类为单 collection 检索器,
                仅接受 None(本 collection)或包含本 collection key 的列表, 其他值忽略。
        """
        cache_key = hashlib.md5(f"{query}_{top_k_final}_{category_filter}_{evidence_type}".encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            result, ts = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.info(f"⚡ [Cache Hit] 跳过重复检索: {query[:50]}...")
                return result
            del self._cache[cache_key]

        logger.info(f"🔍 [HybridRetriever] 检索: {query[:60]}... filter={category_filter}")

        candidates = self._raw_candidates(query, k=top_k_final * 4,
                                          category_filter=category_filter)

        if not candidates:
            logger.warning("⚠️ 检索结果为空")
            self._cache[cache_key] = ([], time.time())
            return []

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
        logger.info("🔧 初始化 UnifiedSearchEngine (Multi-Collection)...")

        self.persist_dir = persist_dir
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

        # 构建/加载 5 个主题隔离的 collection
        self.collections = build_multi_collection_vectorstores(
            self.chunks,
            persist_dir,
            enable_qa=bool(CONFIG.get("enable_qa_generation", False))
        )

        # 每个 collection 一个 HybridRetriever(向量 + 对应桶的 BM25)
        buckets = bucket_chunks_by_collection(self.chunks)
        self.retrievers = {
            key: HybridRetriever(
                self.collections[key],
                buckets.get(key, []),
                k=CONFIG.get("reranker_initial_k", 8)
            )
            for key in COLLECTION_KEYS
        }

        # 跨 collection 汇总时的统一 reranker(无状态, 可共享)
        self.reranker = BGEReranker(top_k=CONFIG.get("top_k_final", 3))
        self._cache: dict = {}
        self._cache_ttl = 300

        # 向量库健康检查: 分块数与 collection 条数一致性(防"库空但服务正常"的静默故障)
        self.health_warnings = self._check_store_health(buckets)

    def _check_store_health(self, buckets: Dict[str, List[Document]]) -> List[str]:
        """校验各 collection 条数与该桶分块数是否一致, 返回告警列表。"""
        warnings = []
        for key in COLLECTION_KEYS:
            expected = len(buckets.get(key, []))
            try:
                actual = self.collections[key]._collection.count()
            except Exception:
                actual = -1
            if actual < 0:
                warnings.append(f"{key}: collection 不可读")
            elif expected == 0 and actual > 0:
                warnings.append(f"{key}: 分块为空但库中有 {actual} 条(可能残留旧文档)")
            elif expected > 0 and actual == 0:
                logger.error(f"❌ [KB健康] {key}: 分块 {expected} 条但库为空 —— 检索将静默失效!")
                warnings.append(f"{key}: 分块 {expected} 条但库为空(检索静默失效)")
            elif actual < expected:
                logger.warning(f"⚠️ [KB健康] {key}: 库中 {actual} 条 < 分块 {expected} 条(可能写入不完整)")
                warnings.append(f"{key}: 库中 {actual} 条 < 分块 {expected} 条")
            else:
                logger.debug(f"✅ [KB健康] {key}: {actual} 条 ✓")
        return warnings

    def reload(self) -> dict:
        """知识库热更新: 重新加载文档、重建分块/向量库/BM25, 返回最新统计。"""
        logger.info("🔄 [KB] 知识库热更新开始...")
        raw_docs = load_pdfs_from_dir(self.docs_dir)
        self.chunks = split_documents(raw_docs)
        self.collections = build_multi_collection_vectorstores(
            self.chunks,
            self.persist_dir,
            enable_qa=bool(CONFIG.get("enable_qa_generation", False))
        )
        buckets = bucket_chunks_by_collection(self.chunks)
        self.retrievers = {
            key: HybridRetriever(
                self.collections[key],
                buckets.get(key, []),
                k=CONFIG.get("reranker_initial_k", 8)
            )
            for key in COLLECTION_KEYS
        }
        self.clear_cache()
        self.health_warnings = self._check_store_health(buckets)
        logger.info("✅ [KB] 知识库热更新完成")
        return self.stats()

    def stats(self) -> dict:
        """知识库统计: 文档列表、分块数、各 collection 向量条数。"""
        doc_names = sorted({str(c.metadata.get("source", "") or "") for c in self.chunks if c.metadata.get("source")})
        collection_counts = {}
        for key, store in self.collections.items():
            try:
                collection_counts[key] = store._collection.count()
            except Exception:
                collection_counts[key] = 0
        return {
            "documents": doc_names,
            "document_count": len(doc_names),
            "chunk_count": len(self.chunks),
            "collections": collection_counts,
            "health_warnings": list(getattr(self, "health_warnings", [])),
        }

    def search(self, query: str, top_k_final: int = 3, category_filter: List[str] = None,
               evidence_type: str = None, collections: List[str] = None) -> List[Document]:
        """检索(支持 Multi-Collection 路由)。

        Args:
            query: 检索式
            top_k_final: 返回条数
            category_filter: Evidence Router 的类别过滤(collection 内后过滤)
            evidence_type: 决策类型(treatment/anatomy/...),用于 Medical Evidence Score
            collections: 限定检索的 collection key 列表(如 ['treatment']),
                None=检索全部 collection。由 Router 决定,物理隔离无关内容。
        """
        keys = collections if collections else COLLECTION_KEYS
        keys = [k for k in keys if k in self.retrievers]

        cache_key = hashlib.md5(
            f"{query}_{top_k_final}_{category_filter}_{evidence_type}_{sorted(keys)}".encode("utf-8")
        ).hexdigest()
        if cache_key in self._cache:
            result, ts = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                logger.info(f"⚡ [Cache Hit] 跳过重复检索: {query[:50]}... collections={keys}")
                return result
            del self._cache[cache_key]

        try:
            logger.info(f"🔍 执行检索: {query[:60]}... filter={category_filter} collections={keys}")
            # 每个选中的 collection 出候选(向量 + BM25 + 类别过滤), 跨 collection 统一 RRF 融合
            ranked_lists = [
                r._raw_candidates(query, k=top_k_final * 4, category_filter=category_filter)
                for key in keys
                for r in [self.retrievers[key]]
            ]
            candidates = HybridRetriever._rrf_merge(ranked_lists, k=60)
            if not candidates:
                logger.warning("⚠️ 检索结果为空")
                self._cache[cache_key] = ([], time.time())
                return []

            candidates = candidates[:top_k_final * 4]
            result = self.reranker.rerank(query, candidates, top_k=top_k_final,
                                          evidence_type=evidence_type)
            logger.info(f"🏆 检索完成，命中 {len(result)} 条 (collections={keys})")
            self._cache[cache_key] = (result, time.time())
            return result
        except Exception as e:
            logger.error(f"❌ 检索失败: {e}")
            return []

    def clear_cache(self):
        count = len(self._cache)
        self._cache.clear()
        for retriever in self.retrievers.values():
            retriever.clear_cache()
        if count > 0:
            logger.info(f"🗑️ [UnifiedSearchEngine] 清空 {count} 条检索缓存")