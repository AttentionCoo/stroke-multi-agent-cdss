"""召回变体和恢复查询必须共享原始问题的排序意图。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.services.retrieval_service import EvidenceRetrievalService
from app.agents.assistant import MedicalAssistant
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode


def document():
    return SimpleNamespace(page_content="临床证据", metadata={"source": "指南.pdf", "category": "指南", "page": 1})


def service(search=None):
    retriever = SimpleNamespace(search=search or Mock(return_value=[document()]))
    return EvidenceRetrievalService(retriever), retriever.search


def test_omitted_rerank_query_keeps_legacy_search_signature():
    def legacy_search(query, top_k, category_filter=None, evidence_type=None, collections=None):
        assert query == "原问题"
        return [document()]

    retrieval, _ = service(legacy_search)
    assert "临床证据" in retrieval.retrieve_single("原问题")
    assert "临床证据" in asyncio.run(retrieval.aretrieve_single("原问题"))


def test_single_retrieval_forwards_original_intent_without_replacing_recall_query():
    retrieval, search = service()
    retrieval.retrieve_single("扩展查询 guideline", evidence_type="treatment", rerank_query="原始治疗问题")
    assert search.call_args.args == ("扩展查询 guideline", 3)
    assert search.call_args.kwargs == {
        "category_filter": None,
        "evidence_type": "treatment",
        "collections": ["treatment"],
        "rerank_query": "原始治疗问题",
    }


def test_async_single_retrieval_keeps_original_intent():
    retrieval, search = service()
    asyncio.run(retrieval.aretrieve_single("召回变体", rerank_query="原问题"))
    assert search.call_args.args[0] == "召回变体"
    assert search.call_args.kwargs["rerank_query"] == "原问题"


def test_sync_parallel_preserves_one_call_per_question_and_original_intent():
    retrieval, search = service()
    result = retrieval.parallel_retrieve(["问题甲", "问题乙"])
    assert search.call_count == 2
    assert {(call.args[0], call.kwargs["rerank_query"]) for call in search.call_args_list} == {
        ("问题甲", "问题甲"), ("问题乙", "问题乙"),
    }
    assert "### 检索维度1: 问题甲" in result
    assert "### 检索维度2: 问题乙" in result


def test_async_parallel_variants_share_their_original_question(monkeypatch):
    monkeypatch.setattr(
        "app.agents.services.query_translator.translate_query",
        lambda query, _type: [f"{query} 变体甲", f"{query} 变体乙"],
    )
    retrieval, search = service()
    asyncio.run(retrieval.aparallel_retrieve(["问题甲", "问题乙"]))
    assert search.call_count == 4
    assert {(call.args[0], call.kwargs["rerank_query"]) for call in search.call_args_list} == {
        ("问题甲 变体甲", "问题甲"), ("问题甲 变体乙", "问题甲"),
        ("问题乙 变体甲", "问题乙"), ("问题乙 变体乙", "问题乙"),
    }


def test_router_keywords_only_affect_recall_through_production_chain(monkeypatch):
    monkeypatch.setattr(
        "app.agents.services.query_translator.translate_query",
        lambda query, _type: [f"{query} 变体甲", f"{query} 变体乙"],
    )
    search = Mock(return_value=[document()])
    assistant = MedicalAssistant(retriever=SimpleNamespace(search=search))
    node = RetrieveNode(assistant)
    questions = ["机械取栓的适应证？", "抗凝治疗的适应证？"]
    state = {
        "retrieval_queries": questions,
        "router_evidence_types": ["treatment", "prevention"],
        "router_categories": [[], []],
        # 使用与原问题不同的干预词，确保测试能识别排序意图污染。
        "router_keywords": [["thrombolysis"], ["antiplatelet"]],
    }

    first = asyncio.run(node.run(state))

    assert search.call_count == 4
    assert {(call.args[0], call.kwargs["rerank_query"]) for call in search.call_args_list} == {
        (f"{questions[0]} thrombolysis 变体甲", questions[0]),
        (f"{questions[0]} thrombolysis 变体乙", questions[0]),
        (f"{questions[1]} antiplatelet 变体甲", questions[1]),
        (f"{questions[1]} antiplatelet 变体乙", questions[1]),
    }
    assert first["retrieved_queries"] == questions
    assert "临床证据" in first["evidence"]

    # 下一轮原问题仍能命中历史查询，Router 富化不破坏跨轮去重。
    second = asyncio.run(node.run({**state, **first}))
    assert search.call_count == 4
    assert second["need_retrieve"] is False
    assert second["retrieved_queries"] == questions


@pytest.mark.parametrize("route_format", ["legacy_raw", "legacy_nonempty", "named_routes"])
def test_history_filter_preserves_router_alignment_through_production_chain(monkeypatch, route_format):
    monkeypatch.setattr(
        "app.agents.services.query_translator.translate_query",
        lambda query, _type: [query],
    )
    old_question = "机械取栓的适应证？"
    new_question = "左侧大脑中动脉梗死如何定位？"
    state = {
        "retrieval_queries": [old_question, " ", new_question],
        "retrieved_queries": [old_question],
    }
    if route_format == "legacy_raw":
        state.update({
            "router_evidence_types": ["treatment", "prevention", "anatomy"],
            "router_categories": [["指南"], ["专家共识"], ["教材"]],
            "router_keywords": [["thrombolysis"], ["antiplatelet"], ["localization"]],
        })
    elif route_format == "legacy_nonempty":
        # EvidenceRouter 会先移除空查询，这类旧数组仍应与保留问题正确对应。
        state.update({
            "router_evidence_types": ["treatment", "anatomy"],
            "router_categories": [["指南"], ["教材"]],
            "router_keywords": [["thrombolysis"], ["localization"]],
        })
    else:
        # 具名路由不依赖输出顺序，与历史问题的路由隔离。
        state["router_routes"] = [
            {"query": new_question, "evidence_type": "anatomy",
             "target_categories": ["教材"], "keywords": ["localization"]},
            {"query": old_question, "evidence_type": "treatment",
             "target_categories": ["指南"], "keywords": ["thrombolysis"]},
        ]
    search = Mock(return_value=[document()])
    assistant = MedicalAssistant(retriever=SimpleNamespace(search=search))
    retrieval = assistant.rag_pipeline.retrieval
    retrieval.retrieve_single = Mock(wraps=retrieval.retrieve_single)

    result = asyncio.run(RetrieveNode(assistant).run(state))

    assert retrieval.retrieve_single.call_args.args[3] == ["教材"]
    search.assert_called_once_with(
        f"{new_question} localization", 3,
        category_filter=None, evidence_type="anatomy", collections=["anatomy"],
        rerank_query=new_question,
    )
    assert result["retrieved_queries"] == [old_question, new_question]


@pytest.mark.parametrize("task_format", ["positional", "named"])
def test_history_filter_preserves_task_fallback_alignment(monkeypatch, task_format):
    monkeypatch.setattr(
        "app.agents.services.query_translator.translate_query",
        lambda query, _type: [query],
    )
    old_question, new_question = "旧治疗问题", "新解剖定位问题"
    tasks = [{"evidence_type": "treatment"}, {"evidence_type": "anatomy"}]
    if task_format == "named":
        tasks = [
            {"query": new_question, "evidence_type": "anatomy"},
            {"query": old_question, "evidence_type": "treatment"},
        ]
    search = Mock(return_value=[document()])
    assistant = MedicalAssistant(retriever=SimpleNamespace(search=search))
    state = {
        "retrieval_queries": [old_question, new_question],
        "retrieved_queries": [old_question],
        "retrieval_tasks": tasks,
    }

    result = asyncio.run(RetrieveNode(assistant).run(state))

    search.assert_called_once_with(
        new_question, 3, category_filter=None, evidence_type="anatomy",
        collections=["anatomy"], rerank_query=new_question,
    )
    assert result["retrieved_queries"] == [old_question, new_question]


def test_assistant_without_original_questions_keeps_legacy_service_signature():
    async def legacy_retrieve(queries, round_number=1, evidence_types=None, category_filters=None):
        assert queries == ["原问题"]
        return "旧服务证据"

    assistant = MedicalAssistant(retriever=SimpleNamespace(search=Mock()))
    assistant.rag_pipeline.retrieval.aparallel_retrieve = legacy_retrieve
    assert asyncio.run(assistant.afast_parallel_retrieve(["原问题"])) == "旧服务证据"


def test_node_without_router_keywords_keeps_legacy_assistant_signature():
    async def legacy_retrieve(queries, round_number=1, evidence_types=None, category_filters=None):
        assert queries == ["原问题"]
        return "旧门面证据"

    node = RetrieveNode(SimpleNamespace(afast_parallel_retrieve=legacy_retrieve))
    result = asyncio.run(node.run({"retrieval_queries": ["原问题"]}))
    assert result["evidence"] == "旧门面证据"


def test_original_questions_must_align_with_recall_queries():
    retrieval, search = service()
    with pytest.raises(ValueError, match="数量一致"):
        asyncio.run(retrieval.aparallel_retrieve(["召回甲", "召回乙"], rerank_queries=["原问题"]))
    search.assert_not_called()


def test_recovery_without_collection_filter_keeps_original_intent():
    retrieval, search = service(Mock(side_effect=[[], [document()]]))
    retrieval.retrieve_single("召回变体", evidence_type="treatment", rerank_query="原问题")
    assert [call.kwargs["collections"] for call in search.call_args_list] == [["treatment"], None]
    assert all(call.kwargs["rerank_query"] == "原问题" for call in search.call_args_list)


def test_synonym_recovery_keeps_original_intent(monkeypatch):
    monkeypatch.setattr("app.agents.services.query_translator.extract_medical_concepts", lambda _query: {"概念": ["术语"]})
    monkeypatch.setattr("app.agents.services.query_translator.build_or_and_query", lambda _concepts: "同义词组合")
    retrieval, search = service(Mock(side_effect=[[], [document()]]))
    retrieval.retrieve_single("召回变体", rerank_query="原问题")
    assert [call.args[0] for call in search.call_args_list] == ["召回变体", "同义词组合"]
    assert all(call.kwargs["rerank_query"] == "原问题" for call in search.call_args_list)


def test_core_concept_subset_recovery_keeps_original_intent(monkeypatch):
    monkeypatch.setattr(
        "app.agents.services.query_translator.extract_medical_concepts",
        lambda _query: {"甲": ["甲"], "乙": ["乙"], "丙": ["丙"]},
    )
    monkeypatch.setattr(
        "app.agents.services.query_translator.build_or_and_query",
        lambda concepts: "完整概念" if len(concepts) == 3 else "核心概念",
    )
    monkeypatch.setattr("app.agents.services.query_translator.expand_synonyms", lambda query: [query])
    retrieval, search = service(Mock(side_effect=[[], [], [document()]]))
    retrieval.retrieve_single("召回变体", rerank_query="原问题")
    assert [call.args[0] for call in search.call_args_list] == ["召回变体", "完整概念", "核心概念"]
    assert all(call.kwargs["rerank_query"] == "原问题" for call in search.call_args_list)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_parallel_does_not_hide_search_parameter_errors(asynchronous):
    retrieval, _ = service(Mock(side_effect=TypeError("检索器参数契约不兼容")))
    with pytest.raises(TypeError, match="参数契约"):
        if asynchronous:
            asyncio.run(retrieval.aparallel_retrieve(["原问题"]))
        else:
            retrieval.parallel_retrieve(["原问题"])
