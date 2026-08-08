"""Medical Evidence Reranker 测试"""
import sys

import pytest

sys.path.insert(0, ".")

from langchain_core.documents import Document
from app.rag.retrievers import BGEReranker


def _make_docs():
    return [
        Document(page_content="alteplase IV thrombolysis",
                 metadata={"evidence_type": "guideline", "authority": 5, "year": 2023,
                           "subtopic": ["thrombolysis"], "relevance_score": 0.8}),
        Document(page_content="血脂管理他汀LDL",
                 metadata={"evidence_type": "guideline", "authority": 4, "year": 2021,
                           "subtopic": ["lipid_management", "secondary_prevention"], "relevance_score": 0.7}),
    ]


def test_medical_score_ranks_thrombolysis_over_lipid():
    """Medical Evidence Score 应给溶栓指南更高分, 血脂指南被降权。"""
    r = BGEReranker.__new__(BGEReranker)
    docs = _make_docs()
    out = r._apply_medical_score(docs, "alteplase acute ischemic stroke treatment", "treatment")
    assert out[0].metadata["subtopic"] == ["thrombolysis"]
    assert out[0].metadata["medical_score"] > out[1].metadata["medical_score"]
    # 血脂指南因 subtopic 不匹配被显著降分
    assert out[1].metadata["medical_score"] < 0.5


def test_medical_score_excludes_lipid_subtopic():
    """treatment 查询中 lipid_management 应被淘汰惩罚。"""
    r = BGEReranker.__new__(BGEReranker)
    docs = [
        Document(page_content="溶栓", metadata={"evidence_type": "guideline", "authority": 5,
                                               "year": 2023, "subtopic": ["thrombolysis"], "relevance_score": 0.9}),
        Document(page_content="血脂", metadata={"evidence_type": "guideline", "authority": 5,
                                               "year": 2023, "subtopic": ["lipid_management"], "relevance_score": 0.9}),
    ]
    out = r._apply_medical_score(docs, "alteplase treatment", "treatment")
    assert out[0].metadata["subtopic"] == ["thrombolysis"]
    assert out[1].metadata["subtopic"] == ["lipid_management"]
    assert out[0].metadata["medical_score"] - out[1].metadata["medical_score"] >= 0.29
