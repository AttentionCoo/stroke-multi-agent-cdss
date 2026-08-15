"""脑卒中医疗工具单元测试

覆盖:
- 量表评估工具(NIHSS / mRS / GCS)
- 溶栓治疗工具(时间窗 / rt-PA 剂量)
- 禁忌症检查工具
- TOAST 诊断分型工具
- 工具注册表与执行器

运行: pytest tests/test_tools.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.tools.registry import (
    TOOL_GROUPS,
    TOOL_MAP,
    call_tool,
    get_all_tools,
    get_tool_schemas,
)


# ---------------------------------------------------------------------------
# 注册表与执行器
# ---------------------------------------------------------------------------

def test_registry_aggregates_expected_tools():
    names = {t.name for t in get_all_tools()}
    assert {"nihss_score", "mrs_score", "gcs_score"} <= names
    assert {"thrombolysis_window_check", "rtpa_dose_calc"} <= names
    assert "contraindication_check" in names
    assert "toast_classify" in names
    assert "lvo_screening" in names
    # 附加评估工具(ASPECTS/风险评分/护理清单/随访计划)
    assert {"aspects_score", "cha2ds2_vasc_score", "has_bled_score",
            "swallow_screen", "rtpa_monitoring_checklist",
            "vte_pressure_ulcer_prevention", "hemorrhage_transformation_risk",
            "followup_plan"} <= names
    assert len(get_all_tools()) == 16


def test_tool_groups_cover_all_tools():
    grouped = {n for v in TOOL_GROUPS.values() for n in v}
    assert grouped == set(TOOL_MAP.keys())


def test_schemas_are_serializable():
    schemas = get_tool_schemas()
    assert len(schemas) == 16
    for s in schemas:
        assert s["name"] and s["description"]
        assert "properties" in s["parameters"]


def test_call_unknown_tool_returns_error():
    r = call_tool("no_such_tool", {})
    assert r["ok"] is False
    assert "available" in r


# ---------------------------------------------------------------------------
# 量表评估工具
# ---------------------------------------------------------------------------

def test_nihss_total_and_severity():
    r = call_tool("nihss_score", {"level_of_consciousness": 0, "language": 2, "motor_arm": 4})
    assert r["ok"] is True
    result = r["result"]
    assert result["total_score"] == 6
    assert "中度" in result["severity"]


def test_nihss_severe_warning():
    r = call_tool("nihss_score", {"level_of_consciousness": 3, "visual": 3, "motor_leg": 4})
    result = r["result"]
    assert result["total_score"] == 10
    assert any("意识" in w for w in result["warnings"])


def test_mrs_description_and_prognosis():
    r = call_tool("mrs_score", {"score": 3})
    result = r["result"]
    assert result["score"] == 3
    assert "中度" in result["description"]
    assert "依赖" in result["prognosis"]


def test_gcs_total():
    r = call_tool("gcs_score", {"eye": 3, "verbal": 4, "motor": 5})
    result = r["result"]
    assert result["total_score"] == 12
    assert "中度" in result["severity"]


# ---------------------------------------------------------------------------
# 溶栓治疗工具
# ---------------------------------------------------------------------------

def test_window_within_3h():
    r = call_tool("thrombolysis_window_check", {"minutes_from_onset": 150})
    result = r["result"]
    assert result["window_status"] == "within_3h"
    assert "溶栓窗内" in result["verdict"]


def test_window_3h_to_4_5h():
    r = call_tool("thrombolysis_window_check", {"minutes_from_onset": 200})
    assert r["result"]["window_status"] == "within_4_5h"


def test_window_beyond():
    r = call_tool("thrombolysis_window_check", {"minutes_from_onset": 400})
    assert r["result"]["window_status"] == "beyond_window"


def test_window_with_timestamps():
    r = call_tool(
        "thrombolysis_window_check",
        {"onset_time": "2025-05-01T08:00:00", "arrival_time": "2025-05-01T11:30:00"},
    )
    assert r["result"]["minutes_from_onset"] == 210.0


def test_window_mixed_timezone_returns_clear_error():
    """一个带时区一个不带时区 → 返回明确错误而非异常。"""
    r = call_tool(
        "thrombolysis_window_check",
        {"onset_time": "2025-05-01T08:00:00", "arrival_time": "2025-05-01T11:30:00+08:00"},
    )
    assert r["result"]["valid"] is False
    assert "时区" in r["result"]["error"]


def test_rtpa_dose_normal():
    r = call_tool("rtpa_dose_calc", {"weight_kg": 70})
    result = r["result"]
    assert result["total_dose_mg"] == 63.0
    assert result["bolus_mg"] == 6.3
    assert result["infusion_mg"] == 56.7


def test_rtpa_dose_capped_at_90():
    r = call_tool("rtpa_dose_calc", {"weight_kg": 120})
    assert r["result"]["total_dose_mg"] == 90.0


# ---------------------------------------------------------------------------
# 禁忌症检查工具
# ---------------------------------------------------------------------------

def test_contraindication_hits():
    r = call_tool(
        "contraindication_check",
        {
            "treatment": "溶栓",
            "patient_info": "患者3小时前发病,既往有脑出血史,血小板90,血压185/115",
        },
    )
    result = r["result"]
    assert result["passed"] is False
    assert "活动性出血" in result["hits"]
    assert "血小板<100" in result["hits"]
    assert "血压超180/110" in result["hits"]


def test_contraindication_blood_pressure_numeric():
    """收缩压>180 或 舒张压>110 应命中血压禁忌(数值解析)。"""
    r = call_tool(
        "contraindication_check",
        {"treatment": "溶栓", "patient_info": "血压 185/100"},
    )
    assert "血压超180/110" in r["result"]["hits"]
    r2 = call_tool(
        "contraindication_check",
        {"treatment": "溶栓", "patient_info": "血压 150/115"},
    )
    assert "血压超180/110" in r2["result"]["hits"]
    r3 = call_tool(
        "contraindication_check",
        {"treatment": "溶栓", "patient_info": "血压 150/100"},
    )
    assert "血压超180/110" not in r3["result"]["hits"]


def test_contraindication_treatment_alias():
    """治疗别名(rt-pa/阿替普酶→溶栓)应被识别。"""
    r = call_tool(
        "contraindication_check",
        {"treatment": "阿替普酶", "patient_info": "活动性出血"},
    )
    assert r["result"]["valid"] is True
    assert r["result"]["treatment"] == "溶栓"
    assert "活动性出血" in r["result"]["hits"]


def test_contraindication_clean():
    r = call_tool(
        "contraindication_check",
        {"treatment": "抗凝", "patient_info": "健康成年人,无出血史"},
    )
    assert r["result"]["passed"] is True


def test_contraindication_unsupported_treatment():
    r = call_tool("contraindication_check", {"treatment": "放血疗法", "patient_info": "x"})
    assert r["ok"] is True
    assert r["result"]["valid"] is False


# ---------------------------------------------------------------------------
# TOAST 分型工具
# ---------------------------------------------------------------------------

def test_toast_cardioembolic():
    r = call_tool("toast_classify", {"cardioembolic_evidence": True})
    assert r["result"]["subtype_key"] == "cardioembolic"


def test_toast_large_artery():
    r = call_tool("toast_classify", {"large_artery_evidence": True})
    assert r["result"]["subtype_key"] == "large_artery"


def test_toast_small_vessel_excluded_by_large_lesion():
    r = call_tool(
        "toast_classify",
        {"small_vessel_evidence": True, "large_vessel_lesion_gt_1_5cm": True},
    )
    # >1.5cm 病灶应排除小动脉闭塞,无其他证据 → 不明原因
    assert r["result"]["subtype_key"] == "undetermined"


def test_toast_undetermined_when_no_evidence():
    r = call_tool("toast_classify", {})
    assert r["result"]["subtype_key"] == "undetermined"
