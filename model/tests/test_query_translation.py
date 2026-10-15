"""查询扩展不得从证据类型推断用户未提及的干预或血管。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.services.query_translator import inject_evidence_keywords, translate_query


@pytest.mark.parametrize(
    "query,evidence_type,expected,forbidden",
    [
        ("房颤患者卒中后二级预防抗凝药物如何选择？", "prevention", "anticoagulation", ("antiplatelet", "抗血小板")),
        ("急性大血管闭塞机械取栓的适应证？", "treatment", "thrombectomy", ("thrombolysis", "溶栓")),
        ("急性缺血性卒中血压管理目标？", "treatment", "guideline", ("thrombolysis", "thrombectomy", "溶栓", "取栓")),
        ("大脑前动脉（ACA）供血区梗死有哪些表现？", "anatomy", "localization", ("mca", "大脑中动脉")),
        ("大脑后动脉（PCA）综合征的临床特征？", "anatomy", "localization", ("mca", "大脑中动脉")),
    ],
)
def test_expansion_uses_only_interventions_or_vessels_present_in_question(query, evidence_type, expected, forbidden):
    variants = translate_query(query, evidence_type)
    assert expected in variants[0].casefold()
    assert variants[0].startswith(query)
    for variant in variants:
        assert all(term.casefold() not in variant.casefold() for term in forbidden)


def test_chinese_thrombolysis_keeps_english_canonical_before_source_terms():
    query = "急性缺血性卒中静脉溶栓时间窗是多少？"
    enriched = inject_evidence_keywords(query, "treatment")
    assert enriched == f"{query} thrombolysis guideline 推荐"
    assert translate_query(query, "treatment")[0] == enriched


def test_english_query_still_prefers_pico_with_real_intervention():
    variants = translate_query("IV alteplase acute ischemic stroke", "treatment")
    assert variants[0].startswith('("')
    assert " AND " in variants[0]
    assert "thrombolysis" in variants[0]
    assert "thrombectomy" not in variants[0]


def test_bridge_treatment_keeps_both_real_interventions_with_shared_budget():
    query = "桥接治疗（溶栓后取栓）的适用情况？"
    enriched = inject_evidence_keywords(query, "treatment")
    assert enriched == f"{query} thrombolysis thrombectomy guideline"
    assert translate_query(query, "treatment")[0] == enriched


def test_existing_canonical_term_is_not_added_twice():
    query = "thrombolysis 静脉溶栓"
    enriched = inject_evidence_keywords(query, "treatment")
    assert enriched.count("thrombolysis") == 1
    assert enriched == f"{query} guideline 推荐 适应证"


@pytest.mark.parametrize("evidence_type", [None, "unknown"])
def test_unknown_evidence_type_preserves_query(evidence_type):
    query = "静脉溶栓时间窗"
    assert inject_evidence_keywords(query, evidence_type) == query
