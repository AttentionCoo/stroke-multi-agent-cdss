"""混合检索语料一致性、分页读取与请求级候选数量测试。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import chromadb
import pytest
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.rag import retrievers
from app.rag.retrievers import HybridRetriever, UnifiedSearchEngine, _load_bm25_documents


def test_load_bm25_documents_pages_actual_collection_and_preserves_qa(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    store = Chroma(client=client, collection_name="hybrid_test")
    metadata = {"source": "持久化指南.pdf", "page": 8, "category": "指南"}
    store._collection.add(
        ids=[f"chunk-{index}" for index in range(1000)],
        documents=[f"阿替普酶静脉溶栓证据 {index}" for index in range(1000)],
        metadatas=[metadata.copy() for _ in range(1000)],
        embeddings=[[1.0, 0.0] for _ in range(1000)],
    )
    qa_metadata = {"source": "持久化指南.pdf", "page": 9, "is_qa": True}
    store._collection.add(
        ids=["qa-document"],
        documents=["问：静脉溶栓的时间窗？答：依据相关指南评估。"],
        metadatas=[qa_metadata],
        embeddings=[[1.0, 0.0]],
    )
    store._collection.add(
        ids=["without-metadata", "blank-document"],
        documents=["无元数据的原文片段", "   "],
        embeddings=[[1.0, 0.0], [1.0, 0.0]],
    )
    reader = SimpleNamespace(get=Mock(wraps=store.get))
    fallback = [Document(page_content="PDF 中已经过期的片段")]

    loaded = _load_bm25_documents(reader, fallback)

    assert len(loaded) == 1002
    by_content = {doc.page_content: doc for doc in loaded}
    assert by_content["阿替普酶静脉溶栓证据 0"].metadata == metadata
    assert by_content["问：静脉溶栓的时间窗？答：依据相关指南评估。"].metadata == qa_metadata
    assert by_content["无元数据的原文片段"].metadata == {}
    assert fallback[0].page_content not in by_content
    assert [call.kwargs["offset"] for call in reader.get.call_args_list] == [0, 1000]
    assert all(
        call.kwargs == {
            "include": ["documents", "metadatas"], "limit": 1000, "offset": offset,
        }
        for call, offset in zip(reader.get.call_args_list, [0, 1000])
    )


def test_load_bm25_documents_without_reader_uses_independent_fallback_list():
    fallback = [Document(page_content="来自 PDF 的备用片段", metadata={"page": 2})]

    loaded = _load_bm25_documents(object(), fallback)

    assert loaded == fallback
    assert loaded is not fallback
    assert _load_bm25_documents(object(), None) == []


@pytest.mark.parametrize("failure_offset", [0, 1000])
def test_load_bm25_documents_read_failure_discards_partial_results(failure_offset, caplog):
    first_page = {
        "documents": [f"已读取的片段 {index}" for index in range(1000)],
        "metadatas": [{"source": "持久化指南.pdf"} for _ in range(1000)],
    }
    responses = [RuntimeError("collection 不可读")]
    if failure_offset:
        responses.insert(0, first_page)
    reader = SimpleNamespace(get=Mock(side_effect=responses))
    fallback = [Document(page_content="完整的 PDF 备用片段")]

    loaded = _load_bm25_documents(reader, fallback)

    # 中途失败时不混入已读取的部分 collection，保证备用语料自洽。
    assert loaded == fallback
    assert loaded is not fallback
    assert reader.get.call_args.kwargs["offset"] == failure_offset
    assert "回退 PDF 语料" in caplog.text


def test_load_bm25_documents_empty_collection_does_not_restore_stale_pdf():
    reader = SimpleNamespace(get=Mock(return_value={"documents": [], "metadatas": []}))

    assert _load_bm25_documents(reader, [Document(page_content="已删除的旧 PDF 片段")]) == []


class FakeVectorRetriever:
    def __init__(self, store, search_kwargs):
        self.store = store
        self.search_kwargs = search_kwargs.copy()

    def invoke(self, query):
        if self.store.barrier is not None:
            self.store.barrier.wait(timeout=5)
        limit = self.search_kwargs["k"]
        self.store.vector_calls.append((query, limit))
        # 每次返回独立文档，避免 RRF 元数据修改掩盖参数隔离测试。
        return [
            Document(page_content=doc.page_content, metadata=doc.metadata.copy())
            for doc in self.store.documents[:limit]
        ]


class FakeVectorStore:
    def __init__(self, documents, barrier=None):
        self.documents = documents
        self.barrier = barrier
        self.retriever_settings = []
        self.vector_calls = []

    def get(self, *, include, limit, offset):
        page = self.documents[offset:offset + limit]
        return {
            "documents": [doc.page_content for doc in page],
            "metadatas": [doc.metadata.copy() for doc in page],
        }

    def as_retriever(self, *, search_kwargs):
        self.retriever_settings.append(search_kwargs.copy())
        return FakeVectorRetriever(self, search_kwargs)


@pytest.fixture
def hybrid_factory(monkeypatch):
    monkeypatch.setenv("BM25_TOKENIZER", "jieba")
    monkeypatch.setattr(retrievers, "BGEReranker", lambda **kwargs: SimpleNamespace())

    def create(*, k=2, barrier=None):
        documents = [
            Document(
                page_content=f"阿替普酶静脉溶栓证据 {index}",
                metadata={"source": "持久化指南.pdf", "page": index, "category": "指南"},
            )
            for index in range(12)
        ]
        store = FakeVectorStore(documents, barrier=barrier)
        stale = [Document(page_content="未入库的旧 PDF 片段")]
        return HybridRetriever(store, stale, k=k), store

    return create


def test_hybrid_bm25_uses_collection_documents_instead_of_pdf_fallback(hybrid_factory):
    hybrid, store = hybrid_factory()

    assert hybrid.bm25.docs == store.documents
    assert all(doc.metadata["source"] == "持久化指南.pdf" for doc in hybrid.bm25.docs)
    assert hybrid.bm25.invoke("旧 PDF") == []
    assert len(hybrid.bm25.invoke("阿替普酶")) == 2


def test_raw_candidates_sets_both_route_limits_without_mutating_shared_settings(hybrid_factory):
    hybrid, store = hybrid_factory(k=2)
    shared_vector_retriever = hybrid.vector_retriever
    original_bm25_invoke = hybrid.bm25.invoke
    hybrid.bm25.invoke = Mock(wraps=original_bm25_invoke)
    query = '("阿替普酶" AND "静脉溶栓")'

    for limit in (7, 3, 2):
        candidates = hybrid._raw_candidates(query, k=limit)
        assert len(candidates) == limit
        assert len(original_bm25_invoke("阿替普酶 静脉溶栓", k=limit)) == limit

    assert store.vector_calls == [(query, 7), (query, 3), (query, 2)]
    assert store.retriever_settings == [{"k": 2}, {"k": 7}, {"k": 3}]
    assert hybrid.vector_retriever is shared_vector_retriever
    assert shared_vector_retriever.search_kwargs == {"k": 2}
    assert hybrid.bm25.k == 2
    assert [call.kwargs for call in hybrid.bm25.invoke.call_args_list] == [
        {"k": 7}, {"k": 3}, {"k": 2},
    ]
    assert all(
        call.args == ("阿替普酶 静脉溶栓",)
        for call in hybrid.bm25.invoke.call_args_list
    )


def test_raw_candidates_default_limit_reuses_configured_vector_retriever(hybrid_factory):
    hybrid, store = hybrid_factory(k=5)

    candidates = hybrid._raw_candidates("阿替普酶")

    assert len(candidates) == 5
    assert store.vector_calls == [("阿替普酶", 5)]
    assert store.retriever_settings == [{"k": 5}]
    assert hybrid.vector_retriever.search_kwargs == {"k": 5}


def test_raw_candidates_concurrent_requests_keep_independent_limits(hybrid_factory):
    hybrid, store = hybrid_factory(k=2, barrier=Barrier(2))

    with ThreadPoolExecutor(max_workers=2) as executor:
        small = executor.submit(hybrid._raw_candidates, "阿替普酶", k=3)
        large = executor.submit(hybrid._raw_candidates, "静脉溶栓", k=9)
        assert len(small.result(timeout=10)) == 3
        assert len(large.result(timeout=10)) == 9

    assert sorted(store.vector_calls) == sorted([("阿替普酶", 3), ("静脉溶栓", 9)])
    assert sorted(item["k"] for item in store.retriever_settings) == [2, 3, 9]
    assert hybrid.vector_retriever.search_kwargs == {"k": 2}
    assert hybrid.bm25.k == 2


class FakeAPIReranker:
    """模拟 API 的 top_n 会影响返回顺序，检测展示数量混入重排预算的回归。"""

    def __init__(self, **kwargs):
        self.api_requests = []

    def rerank(self, query, documents, *, top_k, evidence_type):
        self.api_requests.append({
            "query": query,
            "top_n": top_k,
            "document_count": len(documents),
            "evidence_type": evidence_type,
        })
        ordered = list(documents)
        if top_k >= 10 and "取栓" not in query:
            ordered.reverse()
        for index, document in enumerate(ordered):
            document.metadata["rerank_layer"] = "gte_api"
            document.metadata["relevance_score"] = 1.0 / (index + 1)
        return ordered[:top_k]


@pytest.fixture
def search_factory(monkeypatch):
    monkeypatch.setenv("BM25_TOKENIZER", "jieba")
    monkeypatch.setitem(retrievers.CONFIG, "retrieval_candidate_k", 80)
    monkeypatch.setitem(retrievers.CONFIG, "rerank_candidate_k", 12)
    monkeypatch.setattr(retrievers, "BGEReranker", FakeAPIReranker)

    def create(kind):
        def store_for(source):
            return FakeVectorStore([
                Document(
                    page_content=f"阿替普酶静脉溶栓证据 {source} {index}",
                    metadata={"source": f"{source}.pdf", "page": index, "category": "指南"},
                )
                for index in range(100)
            ])

        if kind == "hybrid":
            store = store_for("treatment")
            engine = HybridRetriever(store, [], k=8)
            collection_retrievers = [engine]
            stores = [store]
        else:
            stores_by_key = {key: store_for(key) for key in ("treatment", "guideline")}
            monkeypatch.setattr(retrievers, "COLLECTION_KEYS", list(stores_by_key))
            monkeypatch.setattr(
                retrievers, "build_multi_collection_vectorstores",
                lambda *args, **kwargs: stores_by_key,
            )
            engine = UnifiedSearchEngine("unused", top_k=3, read_only=True)
            collection_retrievers = list(engine.retrievers.values())
            stores = list(stores_by_key.values())
        for collection_retriever in collection_retrievers:
            original = collection_retriever.bm25.invoke
            collection_retriever.bm25.invoke = Mock(wraps=original)
        return engine, stores, collection_retrievers

    return create


@pytest.mark.parametrize("kind", ["hybrid", "unified"])
def test_display_count_preserves_ranking_prefix_and_fixed_api_budget(kind, search_factory):
    engine, stores, collection_retrievers = search_factory(kind)
    query = "阿替普酶静脉溶栓 guideline"

    short = engine.search(query, top_k_final=3, evidence_type="treatment")
    long = engine.search(query, top_k_final=20, evidence_type="treatment")

    assert len(short) == 3
    assert len(long) == 12
    assert [doc.page_content for doc in short] == [doc.page_content for doc in long[:3]]
    assert engine.reranker.api_requests == [
        {"query": query, "top_n": 12, "document_count": 12, "evidence_type": "treatment"},
        {"query": query, "top_n": 12, "document_count": 12, "evidence_type": "treatment"},
    ]
    for store, collection_retriever in zip(stores, collection_retrievers):
        assert store.vector_calls == [(query, 80), (query, 80)]
        assert [call.kwargs for call in collection_retriever.bm25.invoke.call_args_list] == [
            {"k": 80}, {"k": 80},
        ]
        assert all(doc.metadata["rerank_layer"] == "gte_api" for doc in long)


@pytest.mark.parametrize("kind", ["hybrid", "unified"])
def test_original_rerank_question_is_separate_from_expanded_query_and_cached(kind, search_factory):
    engine, stores, collection_retrievers = search_factory(kind)
    expanded = "阿替普酶 静脉溶栓 thrombolysis guideline"
    question = "静脉溶栓的适应证？"
    other_question = "机械取栓的适应证？"

    first = engine.search(expanded, top_k_final=3, rerank_query=question, evidence_type="treatment")
    second = engine.search(expanded, top_k_final=3, rerank_query=other_question, evidence_type="treatment")
    cached = engine.search(expanded, top_k_final=3, rerank_query=question, evidence_type="treatment")

    assert [doc.page_content for doc in first] != [doc.page_content for doc in second]
    assert [doc.page_content for doc in cached] == [doc.page_content for doc in first]
    assert [call["query"] for call in engine.reranker.api_requests] == [question, other_question]
    assert [call["top_n"] for call in engine.reranker.api_requests] == [12, 12]
    for store, collection_retriever in zip(stores, collection_retrievers):
        assert store.vector_calls == [(expanded, 80), (expanded, 80)]
        assert [call.args for call in collection_retriever.bm25.invoke.call_args_list] == [
            (expanded,), (expanded,),
        ]
        assert collection_retriever.bm25.invoke.call_count == 2


@pytest.mark.parametrize("kind", ["hybrid", "unified"])
@pytest.mark.parametrize("candidate_k, rerank_k", [(0, 12), (-1, 1), (80, 0), (80, -1), (5, 12)])
def test_invalid_candidate_budgets_fail_before_loading_documents(kind, candidate_k, rerank_k, monkeypatch):
    reader = Mock(side_effect=AssertionError("非法预算不得读取文档"))
    builder = Mock(side_effect=AssertionError("非法预算不得连接知识库"))
    reranker = Mock(side_effect=AssertionError("非法预算不得初始化重排器"))
    store = FakeVectorStore([])
    store.get = reader
    monkeypatch.setattr(retrievers, "load_pdfs_from_dir", reader)
    monkeypatch.setattr(retrievers, "build_multi_collection_vectorstores", builder)
    monkeypatch.setattr(retrievers, "BGEReranker", reranker)

    with pytest.raises(ValueError, match="候选预算"):
        if kind == "hybrid":
            HybridRetriever(store, [], candidate_k=candidate_k, rerank_k=rerank_k)
        else:
            UnifiedSearchEngine("unused", top_k=3, candidate_k=candidate_k, rerank_k=rerank_k)

    reader.assert_not_called()
    builder.assert_not_called()
    reranker.assert_not_called()


def test_rrf_results_do_not_modify_reused_bm25_document_metadata(hybrid_factory):
    hybrid, _store = hybrid_factory()
    original_documents = hybrid.bm25.invoke("阿替普酶", k=3)
    original_metadata = [document.metadata.copy() for document in original_documents]

    first = HybridRetriever._rrf_merge([original_documents, original_documents[::-1]])
    first_scores = [document.metadata["rrf_score"] for document in first]
    first[0].metadata["relevance_score"] = 0.9
    first[0].metadata["rerank_layer"] = "gte_api"
    second = HybridRetriever._rrf_merge([original_documents])

    assert [document.metadata for document in original_documents] == original_metadata
    assert [document.metadata["rrf_score"] for document in first] == first_scores
    assert all(document.metadata["rrf_score"] > 0 for document in second)
    assert all(
        result is not original
        for result in first + second
        for original in original_documents
    )
    assert "relevance_score" not in second[0].metadata
    assert "rerank_layer" not in second[0].metadata
