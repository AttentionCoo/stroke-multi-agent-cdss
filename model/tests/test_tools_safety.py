"""DDI 药物交互 与 ICD-10 编码工具测试(纯规则, 无需真实 API)。

运行: pytest tests/test_tools_safety.py -v
"""
import sys

import pytest

sys.path.insert(0, ".")

from app.agents.tools.registry import call_tool, get_all_tools


# ── DDI 药物交互 ──

def test_ddi_detects_severe_pair():
    r = call_tool("drug_interaction_check", {"drugs": ["阿司匹林", "华法林"]})
    assert r["ok"] is True
    result = r["result"]
    assert result["interaction_count"] >= 1
    severe = [i for i in result["interactions"] if i["severity"] == "严重"]
    assert any("华法林" in i["drug_a"] + i["drug_b"] and "阿司匹林" in i["drug_a"] + i["drug_b"] for i in severe)


def test_ddi_aliases_resolved():
    """英文名/商品名别名应解析到规范名并命中交互。"""
    r = call_tool("drug_interaction_check", {"drugs": ["aspirin", "warfarin"]})
    result = r["result"]
    assert "阿司匹林" in result["checked_drugs"]
    assert "华法林" in result["checked_drugs"]
    assert result["interaction_count"] >= 1


def test_ddi_multiple_drugs_and_sort():
    """多药列表应两两检查, 并按严重度排序(严重在前)。"""
    r = call_tool("drug_interaction_check", {
        "drugs": ["阿替普酶", "阿司匹林", "氯吡格雷", "奥美拉唑", "辛伐他汀", "克拉霉素"],
    })
    result = r["result"]
    assert result["interaction_count"] >= 3
    severities = [i["severity"] for i in result["interactions"]]
    assert severities == sorted(severities, key={"严重": 0, "中度": 1, "轻度": 2}.get)


def test_ddi_unknown_drug_not_crash():
    r = call_tool("drug_interaction_check", {"drugs": ["阿司匹林", "不明药物X"]})
    result = r["result"]
    assert "不明药物X" in result["unknown_drugs"]
    assert r["ok"] is True


def test_ddi_validation_min_two():
    r = call_tool("drug_interaction_check", {"drugs": ["阿司匹林"]})
    assert r["ok"] is False  # min_length=2 校验失败


# ── ICD-10 编码 ──

def test_icd10_matches_stroke():
    r = call_tool("icd10_coding", {"diagnosis": "急性缺血性脑卒中, 左侧大脑中动脉闭塞"})
    assert r["ok"] is True
    codes = {c["code"] for c in r["result"]["codes"]}
    assert "I63.9" in codes
    assert "I66.0" in codes  # 大脑中动脉闭塞


def test_icd10_hemorrhage_and_af():
    r = call_tool("icd10_coding", {"diagnosis": "脑出血合并心房颤动, 高血压"})
    codes = {c["code"] for c in r["result"]["codes"]}
    assert "I61.9" in codes
    assert "I48.91" in codes
    assert "I10" in codes


def test_icd10_no_match_returns_empty():
    r = call_tool("icd10_coding", {"diagnosis": "膝关节术后康复"})
    assert r["result"]["matched_count"] == 0
    assert r["result"]["codes"] == []


def test_icd10_dedup_codes():
    """同一编码多次命中只保留一次。"""
    r = call_tool("icd10_coding", {"diagnosis": "脑梗死, 急性脑梗死, 缺血性卒中"})
    codes = [c["code"] for c in r["result"]["codes"]]
    assert codes.count("I63.9") == 1


# ── 注册表集成 ──

def test_new_tools_registered():
    names = {t.name for t in get_all_tools()}
    assert "drug_interaction_check" in names
    assert "icd10_coding" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
