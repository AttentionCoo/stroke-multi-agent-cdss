"""脑卒中量表评估工具集

提供 NIHSS / mRS / GCS 结构化评估与评分计算。
所有工具均为纯函数式、可独立调用,并可作为 LangChain tool 供 LLM 调用。

医疗安全提示:本工具仅做结构化评分计算辅助,不能替代临床医生判断。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools._compat import model_func

# ---------------------------------------------------------------------------
# NIHSS(美国国立卫生研究院卒中量表)
# ---------------------------------------------------------------------------


class NIHSSInput(BaseModel):
    """NIHSS 各分项得分(0-42 分)。未提供的分项按 0 分计。"""

    level_of_consciousness: int = Field(
        default=0, ge=0, le=3, description="1a 意识水平(0=清醒,1=嗜睡,2=昏睡,3=昏迷)"
    )
    loc_questions: int = Field(
        default=0, ge=0, le=2, description="1b 意识水平提问(0=两项均正确,1=一项正确,2=两项均错误)"
    )
    loc_commands: int = Field(
        default=0, ge=0, le=2, description="1c 意识水平指令(0=两项均正确,1=一项正确,2=两项均错误)"
    )
    gaze: int = Field(default=0, ge=0, le=2, description="2 凝视(0=正常,1=部分凝视麻痹,2=完全凝视麻痹)")
    visual: int = Field(default=0, ge=0, le=3, description="3 视野(0=无缺损,1=部分偏盲,2=完全偏盲,3=双侧偏盲)")
    facial: int = Field(default=0, ge=0, le=3, description="4 面瘫(0=正常,1=轻微,2=部分,3=完全)")
    motor_arm: int = Field(
        default=0, ge=0, le=4, description="5 左上肢/右上肢运动(0=无坠落,1=坠落,2=抗重力,3=不能抗重力,4=无运动)"
    )
    motor_leg: int = Field(
        default=0, ge=0, le=4, description="6 左下肢/右下肢运动(0=无坠落,1=坠落,2=抗重力,3=不能抗重力,4=无运动)"
    )
    ataxia: int = Field(default=0, ge=0, le=2, description="7 肢体共济失调(0=无,1=一个肢体,2=两个肢体)")
    sensory: int = Field(default=0, ge=0, le=2, description="8 感觉(0=正常,1=轻中度,2=严重或完全丧失)")
    language: int = Field(default=0, ge=0, le=3, description="9 语言(0=正常,1=轻中度失语,2=严重失语,3=缄默或完全失语)")
    dysarthria: int = Field(default=0, ge=0, le=2, description="10 构音障碍(0=正常,1=轻中度,2=严重或无法评估)")
    extinction: int = Field(default=0, ge=0, le=2, description="11 忽视(0=无,1=一种感觉通道,2=两种及以上感觉通道)")


def _nihss_score(inputs: NIHSSInput) -> Dict:
    items = {
        "1a_意识水平": inputs.level_of_consciousness,
        "1b_意识提问": inputs.loc_questions,
        "1c_意识指令": inputs.loc_commands,
        "2_凝视": inputs.gaze,
        "3_视野": inputs.visual,
        "4_面瘫": inputs.facial,
        "5_上肢运动": inputs.motor_arm,
        "6_下肢运动": inputs.motor_leg,
        "7_共济失调": inputs.ataxia,
        "8_感觉": inputs.sensory,
        "9_语言": inputs.language,
        "10_构音障碍": inputs.dysarthria,
        "11_忽视": inputs.extinction,
    }
    total = sum(items.values())

    if total <= 4:
        severity = "轻度(0-4)"
    elif total <= 15:
        severity = "中度(5-15)"
    elif total <= 20:
        severity = "中重度(16-20)"
    else:
        severity = "重度(21-42)"

    # 关键警示:意识或语言/视野受累提示大面积或后循环卒中可能
    warnings: List[str] = []
    if inputs.level_of_consciousness >= 2:
        warnings.append("意识障碍明显(1a≥2),警惕大面积半球或脑干卒中")
    if inputs.language >= 2:
        warnings.append("严重失语(9≥2),提示优势半球受累")
    if inputs.visual >= 3:
        warnings.append("双侧视野缺损(3=3),提示后循环受累可能")
    if inputs.motor_arm >= 3 or inputs.motor_leg >= 3:
        warnings.append("肢体完全瘫痪(5/6≥3),提示皮质脊髓束严重受损")

    return {
        "total_score": total,
        "severity": severity,
        "items": items,
        "warnings": warnings,
        "note": "NIHSS 总分 0-42,评分越高神经功能缺损越重;用于基线评估与动态对比。",
    }


nihss_score_tool = StructuredTool.from_function(
    name="nihss_score",
    description=(
        "计算 NIHSS(美国国立卫生研究院卒中量表)总分与严重程度分级。"
        "输入各分项得分(0-42 分制),返回总分、分级与关键警示。"
        "适用于急性缺血性卒中神经功能缺损评估。"
    ),
    args_schema=NIHSSInput,
    func=model_func(NIHSSInput, _nihss_score),
)

# ---------------------------------------------------------------------------
# mRS(改良 Rankin 量表)
# ---------------------------------------------------------------------------


class MRSInput(BaseModel):
    """mRS 分级(0-6)。"""

    score: int = Field(ge=0, le=6, description="mRS 分级(0=完全无症状,6=死亡)")


def _mrs_score(inputs: MRSInput) -> Dict:
    descriptions = {
        0: "完全无症状",
        1: "尽管有症状,但无明显功能障碍;能完成所有日常职责和活动",
        2: "轻度残疾;不能完成病前所有活动,但不需帮助能照料自己的事务",
        3: "中度残疾;需要一些帮助,但行走不需协助",
        4: "中重度残疾;不能独立行走,日常生活需他人帮助",
        5: "重度残疾;卧床、二便失禁,需持续护理",
        6: "死亡",
    }
    s = inputs.score
    if s <= 1:
        prognosis = "预后良好(独立生活能力保留)"
    elif s == 2:
        prognosis = "轻度依赖"
    elif s <= 4:
        prognosis = "中度依赖,需康复治疗"
    else:
        prognosis = "重度依赖或死亡,需长期照护"
    return {
        "score": s,
        "description": descriptions[s],
        "prognosis": prognosis,
        "note": "mRS 是卒中功能结局评价的常用量表,常用于 90 天功能预后评估。",
    }


mrs_score_tool = StructuredTool.from_function(
    name="mrs_score",
    description="计算 mRS(改良 Rankin 量表)功能结局分级(0-6),返回分级描述与预后提示。",
    args_schema=MRSInput,
    func=model_func(MRSInput, _mrs_score),
)

# ---------------------------------------------------------------------------
# GCS(格拉斯哥昏迷量表)
# ---------------------------------------------------------------------------


class GCSInput(BaseModel):
    """GCS 三部分得分。"""

    eye: int = Field(ge=1, le=4, description="睁眼反应 E(1=不睁眼,2=疼痛刺激睁眼,3=呼唤睁眼,4=自发睁眼)")
    verbal: int = Field(
        ge=1, le=5, description="语言反应 V(1=无语言,2=不可理解发声,3=言语不当,4=言语混乱,5=对答正确)"
    )
    motor: int = Field(
        ge=1, le=6, description="运动反应 M(1=无反应,2=过伸,3=屈曲,4=回缩,5=定位,6=遵嘱运动)"
    )


def _gcs_score(inputs: GCSInput) -> Dict:
    total = inputs.eye + inputs.verbal + inputs.motor
    if total >= 13:
        severity = "轻度意识障碍(13-15)"
    elif total >= 9:
        severity = "中度意识障碍(9-12)"
    else:
        severity = "重度意识障碍(3-8,昏迷)"
    return {
        "eye": inputs.eye,
        "verbal": inputs.verbal,
        "motor": inputs.motor,
        "total_score": total,
        "severity": severity,
        "note": "GCS 总分 3-15,评分越低意识障碍越重;≤8 分通常提示需要气道保护。",
    }


gcs_score_tool = StructuredTool.from_function(
    name="gcs_score",
    description="计算 GCS(格拉斯哥昏迷量表)总分(3-15)与意识障碍分级。输入 E/V/M 三部分得分。",
    args_schema=GCSInput,
    func=model_func(GCSInput, _gcs_score),
)

SCALE_TOOLS: List[StructuredTool] = [
    nihss_score_tool,
    mrs_score_tool,
    gcs_score_tool,
]

__all__ = ["SCALE_TOOLS", "nihss_score_tool", "mrs_score_tool", "gcs_score_tool"]
