"""溶栓治疗相关工具

提供:
- 溶栓时间窗判断(发病-就诊时间 vs 指南窗口)
- rt-PA(阿替普酶)剂量计算(按体重)

医疗安全提示:本工具仅为计算辅助,最终给药决策必须由临床医生结合
影像与实验室检查结果作出。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools._compat import model_func


class ThrombolysisWindowInput(BaseModel):
    """溶栓时间窗判断输入。提供 发病时间/就诊时间 或直接提供 分钟数。"""

    onset_time: Optional[str] = Field(
        default=None, description="发病时间,ISO 8601 格式,如 2025-05-01T08:30:00"
    )
    arrival_time: Optional[str] = Field(
        default=None, description="就诊时间(到院时间),ISO 8601 格式,如 2025-05-01T11:00:00"
    )
    minutes_from_onset: Optional[float] = Field(
        default=None, ge=0, description="发病至到院分钟数(若未提供具体时间点,可直接给分钟数)"
    )


# 指南时间窗阈值(分钟)
_WINDOW_STANDARD = 270.0       # 4.5h:rt-PA 标准窗口(中国指南)
_WINDOW_STRICT = 180.0         # 3.0h:更严格窗口(早期指南/部分适应症)


def _thrombolysis_window(inputs: ThrombolysisWindowInput) -> Dict:
    if inputs.minutes_from_onset is not None:
        minutes = inputs.minutes_from_onset
    elif inputs.onset_time and inputs.arrival_time:
        try:
            onset = datetime.fromisoformat(inputs.onset_time)
            arrival = datetime.fromisoformat(inputs.arrival_time)
            minutes = (arrival - onset).total_seconds() / 60.0
        except (ValueError, TypeError):
            return {
                "valid": False,
                "error": "时间格式错误,请使用 ISO 8601 格式(如 2025-05-01T08:30:00),且两个时间点的时区格式应一致",
            }
    else:
        return {
            "valid": False,
            "error": "请提供 minutes_from_onset,或同时提供 onset_time 与 arrival_time",
        }

    if minutes < 0:
        return {"valid": False, "error": "发病时间晚于就诊时间,请检查输入"}

    if minutes <= _WINDOW_STRICT:
        verdict = "溶栓窗内(≤3h):符合 rt-PA 静脉溶栓标准时间窗"
        window_status = "within_3h"
    elif minutes <= _WINDOW_STANDARD:
        verdict = "溶栓窗内(3-4.5h):符合 rt-PA 静脉溶栓扩展时间窗,需结合影像与禁忌症综合评估"
        window_status = "within_4_5h"
    else:
        verdict = "超出溶栓时间窗(>4.5h):不建议常规静脉溶栓,评估血管内取栓或个体化方案"
        window_status = "beyond_window"

    return {
        "valid": True,
        "minutes_from_onset": round(minutes, 1),
        "hours_from_onset": round(minutes / 60.0, 2),
        "window_status": window_status,
        "verdict": verdict,
        "note": "时间窗判断仅基于时间因素;是否溶栓还需结合 NIHSS 评分、头颅 CT、禁忌症等综合评估。",
    }


thrombolysis_window_tool = StructuredTool.from_function(
    name="thrombolysis_window_check",
    description=(
        "判断急性缺血性卒中患者的静脉溶栓时间窗:输入发病-到院时间(分钟或时间点),"
        "返回是否在 3h/4.5h 溶栓窗内及处理建议。"
    ),
    args_schema=ThrombolysisWindowInput,
    func=model_func(ThrombolysisWindowInput, _thrombolysis_window),
)


class RtPADoseInput(BaseModel):
    """rt-PA 剂量计算输入。"""

    weight_kg: float = Field(gt=0, le=300, description="患者体重(公斤)")
    max_dose_mg: Optional[float] = Field(
        default=90.0, ge=10, le=200, description="最大剂量上限(默认 90mg,按指南)"
    )
    dose_per_kg: Optional[float] = Field(
        default=0.9, gt=0, le=2.0, description="单位体重剂量(mg/kg,默认 0.9mg/kg,按指南)"
    )


def _rtpa_dose(inputs: RtPADoseInput) -> Dict:
    raw = inputs.weight_kg * inputs.dose_per_kg
    total_dose = min(raw, inputs.max_dose_mg)
    bolus = round(total_dose * 0.10, 2)   # 10% 首剂静推
    infusion = round(total_dose * 0.90, 2)  # 90% 静滴 60 分钟
    return {
        "weight_kg": inputs.weight_kg,
        "dose_per_kg": inputs.dose_per_kg,
        "raw_dose_mg": round(raw, 2),
        "max_dose_mg": inputs.max_dose_mg,
        "total_dose_mg": round(total_dose, 2),
        "bolus_mg": bolus,
        "infusion_mg": infusion,
        "regimen": f"首剂 {bolus}mg 静推(10%),随后 {infusion}mg 静脉滴注 60 分钟(90%)",
        "note": "剂量计算基于指南标准方案(0.9mg/kg,最大 90mg);实际用药前必须复核体重、核对禁忌症并取得知情同意。",
    }


rtpa_dose_tool = StructuredTool.from_function(
    name="rtpa_dose_calc",
    description=(
        "按体重计算 rt-PA(阿替普酶)静脉溶栓剂量:0.9mg/kg,最大 90mg,"
        "返回总剂量、10% 首剂推注量与 90% 静滴量。"
    ),
    args_schema=RtPADoseInput,
    func=model_func(RtPADoseInput, _rtpa_dose),
)

THROMBOLYSIS_TOOLS = [thrombolysis_window_tool, rtpa_dose_tool]

__all__ = ["THROMBOLYSIS_TOOLS", "thrombolysis_window_tool", "rtpa_dose_tool"]
