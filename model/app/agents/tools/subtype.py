"""诊断分型工具:TOAST 缺血性卒中病因分型辅助

依据 TOAST 标准(1993, Adams et al.)提供分型决策辅助。
输入患者的关键线索(大血管狭窄、心源性栓塞风险、腔隙综合征等),
输出建议分型与理由。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools._compat import model_func


class TOASTInput(BaseModel):
    """TOAST 分型判断输入。"""

    large_artery_evidence: bool = Field(
        default=False, description="是否存在大动脉粥样硬化证据(如颈内动脉/大脑中动脉狭窄≥50%、斑块、闭塞)"
    )
    cardioembolic_evidence: bool = Field(
        default=False, description="是否存在心源性栓塞证据(房颤、心内血栓、瓣膜病变、近期心梗等)"
    )
    small_vessel_evidence: bool = Field(
        default=False, description="是否存在小动脉闭塞(腔隙)证据:典型腔隙综合征+影像示 <1.5cm 深部梗死"
    )
    other_cause_evidence: bool = Field(
        default=False, description="是否存在其他明确病因(血管炎、动脉夹层、血液病、抗磷脂综合征等)"
    )
    large_vessel_lesion_gt_1_5cm: bool = Field(
        default=False, description="影像学梗死灶是否 >1.5cm(用于区分大动脉与小动脉闭塞)"
    )
    cortical_infarct: bool = Field(
        default=False, description="是否存在皮层梗死(提示栓塞而非小动脉闭塞)"
    )
    multiple_vascular_territory: bool = Field(
        default=False, description="是否存在多血管区梗死(心源性栓塞的强提示)"
    )
    no_large_artery_disease: bool = Field(
        default=False, description="是否排除大动脉粥样硬化疾病(无≥50%狭窄/闭塞)"
    )
    additional_info: str = Field(
        default="", description="其他补充信息(如血管超声、DSA、超声心动结果),可帮助分型判断"
    )


_TOAST_LABELS = {
    "large_artery": "大动脉粥样硬化型(LAA)",
    "cardioembolic": "心源性栓塞型(CE)",
    "small_vessel": "小动脉闭塞型(SVO)",
    "other": "其他明确病因型(SOE)",
    "undetermined": "不明原因型(SUE)",
}

_DESCRIPTIONS = {
    "large_artery": "皮层或小脑损害、或脑干梗死;影像示梗死灶 >1.5cm,伴大动脉狭窄/闭塞证据。",
    "cardioembolic": "皮层或小脑损害、或脑干梗死;影像示梗死灶 >1.5cm,伴明确心源性栓塞来源。",
    "small_vessel": "典型腔隙综合征,影像示深部或脑干梗死灶 <1.5cm,无皮层损害。",
    "other": "存在血管炎、夹层、血液病等明确其他病因。",
    "undetermined": "检查未发现明确病因,或存在两个及以上可能病因。",
}


def _toast_classify(inputs: TOASTInput) -> Dict:
    score = {
        "large_artery": 0,
        "cardioembolic": 0,
        "small_vessel": 0,
        "other": 0,
    }
    reasons: List[str] = []

    # 大动脉粥样硬化
    if inputs.large_artery_evidence:
        score["large_artery"] += 2
        reasons.append("检出大动脉狭窄/斑块/闭塞证据")

    # 心源性栓塞:按证据强度分层(避免"有房颤=心源性"的过强规则)
    if inputs.cardioembolic_evidence:
        score["cardioembolic"] += 1
        reasons.append("存在心源性栓子来源(房颤等),基础证据")
    if inputs.cardioembolic_evidence and inputs.cortical_infarct:
        score["cardioembolic"] += 1
        reasons.append("皮层梗死提示栓塞性而非小动脉闭塞")
    if inputs.cardioembolic_evidence and inputs.multiple_vascular_territory:
        score["cardioembolic"] += 2
        reasons.append("多血管区梗死是心源性栓塞的强提示")
    if inputs.cardioembolic_evidence and inputs.no_large_artery_disease:
        score["cardioembolic"] += 1
        reasons.append("已排除大动脉粥样硬化,支持心源性病因")

    if inputs.small_vessel_evidence:
        score["small_vessel"] += 2
        reasons.append("符合典型腔隙综合征且深部梗死灶<1.5cm")
    if inputs.other_cause_evidence:
        score["other"] += 2
        reasons.append("检出其他明确病因")

    # 梗死灶大小与大动脉/心源/小血管判断的相互作用
    if inputs.large_vessel_lesion_gt_1_5cm:
        if inputs.small_vessel_evidence:
            score["small_vessel"] -= 1
            reasons.append("梗死灶>1.5cm 不支持小动脉闭塞诊断")
        if not (inputs.large_artery_evidence or inputs.cardioembolic_evidence):
            reasons.append("梗死灶>1.5cm 提示可能为大动脉或心源性病因")

    if inputs.additional_info.strip():
        reasons.append(f"补充信息: {inputs.additional_info.strip()}")

    # 决策
    if score["other"] > 0 and max(score.values()) == score["other"]:
        subtype = "other"
    elif score["small_vessel"] >= 2 and max(score.values()) == score["small_vessel"]:
        subtype = "small_vessel"
    elif score["cardioembolic"] >= score["large_artery"] and score["cardioembolic"] > 0:
        subtype = "cardioembolic"
    elif score["large_artery"] > 0:
        subtype = "large_artery"
    else:
        subtype = "undetermined"

    return {
        "suggested_subtype": _TOAST_LABELS[subtype],
        "subtype_key": subtype,
        "score": score,
        "reasons": reasons,
        "description": _DESCRIPTIONS[subtype],
        "note": "本工具为分型决策辅助,最终分型需结合完整影像、血管与心脏评估。",
    }


toast_classify_tool = StructuredTool.from_function(
    name="toast_classify",
    description=(
        "缺血性卒中 TOAST 病因分型辅助:输入大动脉/心源性/小血管/其他病因证据线索,"
        "输出建议分型(大动脉粥样硬化型/心源性栓塞型/小动脉闭塞型/其他明确病因型/不明原因型)。"
    ),
    args_schema=TOASTInput,
    func=model_func(TOASTInput, _toast_classify),
)

SUBTYPE_TOOLS = [toast_classify_tool]

__all__ = ["SUBTYPE_TOOLS", "toast_classify_tool"]
