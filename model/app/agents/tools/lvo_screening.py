"""LVO(大血管闭塞)筛查工具

基于卒中文献中 LVO 预测因素(NIHSS 分项、失语、偏瘫、皮层体征等),
输出 LVO 可能性分层与 CTA 检查建议。

医疗安全提示:本工具为筛查辅助,不能替代急诊 CTA 与临床综合判断。
"""
from __future__ import annotations

from typing import Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools._compat import model_func


class LVOScreeningInput(BaseModel):
    """LVO 筛查输入。"""

    nihss_score: int = Field(ge=0, le=42, description="NIHSS 总分")
    aphasia: bool = Field(default=False, description="是否存在失语/言语障碍")
    hemiplegia: bool = Field(default=False, description="是否存在偏瘫/肢体完全无力")
    cortical_signs: bool = Field(
        default=False, description="是否存在皮层体征(忽视/凝视/视野缺损/意识下降)"
    )
    gaze_deviation: bool = Field(default=False, description="是否存在凝视偏移")
    neglect: bool = Field(default=False, description="是否存在忽视/单侧忽略")


def _lvo_screening(inputs: LVOScreeningInput) -> Dict:
    score = 0
    reasons = []

    # NIHSS ≥ 10 提示 LVO 可能
    if inputs.nihss_score >= 10:
        score += 2
        reasons.append(f"NIHSS {inputs.nihss_score} ≥ 10,提示大血管闭塞可能")
    elif inputs.nihss_score >= 6:
        score += 1
        reasons.append(f"NIHSS {inputs.nihss_score} ≥ 6,需考虑大血管闭塞")

    if inputs.aphasia:
        score += 1
        reasons.append("失语提示优势半球(左侧 MCA 区)受累")
    if inputs.hemiplegia:
        score += 1
        reasons.append("偏瘫提示皮质脊髓束/运动区受累")
    if inputs.cortical_signs:
        score += 1
        reasons.append("皮层体征提示皮质受累")
    if inputs.gaze_deviation:
        score += 2
        reasons.append("凝视偏移是 MCA M1 段闭塞的强预测因素")
    if inputs.neglect:
        score += 1
        reasons.append("忽视提示非优势半球(右侧 MCA 区)受累")

    if score >= 4:
        probability = "高"
        cta = "强烈建议急诊 CTA 筛查大血管闭塞,评估机械取栓适应证"
    elif score >= 2:
        probability = "中"
        cta = "建议急诊 CTA 评估大血管闭塞可能"
    else:
        probability = "低"
        cta = "大血管闭塞可能性低,可结合临床与影像决定是否 CTA"

    return {
        "lvo_score": score,
        "lvo_probability": probability,
        "cta_recommended": score >= 2,
        "cta_advice": cta,
        "reasons": reasons,
        "note": "本工具基于 LVO 预测因素(如 NIHSS、凝视偏移、失语、忽视)的筛查辅助,"
        "最终血管评估以 CTA/MRA 为准。",
    }


lvo_screening_tool = StructuredTool.from_function(
    name="lvo_screening",
    description=(
        "大血管闭塞(LVO)筛查:输入 NIHSS 总分与神经体征(失语/偏瘫/皮层体征/凝视偏移/忽视),"
        "输出 LVO 可能性分层(高/中/低)与是否推荐急诊 CTA。"
    ),
    args_schema=LVOScreeningInput,
    func=model_func(LVOScreeningInput, _lvo_screening),
)

LVO_TOOLS = [lvo_screening_tool]

__all__ = ["LVO_TOOLS", "lvo_screening_tool"]
