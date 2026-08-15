"""脑卒中附加评估工具集:ASPECTS 评分、CHA2DS2-VASc、HAS-BLED、
洼田饮水试验、rt-PA 后 24h 监测清单、压疮/DVT 预防清单、出血转化风险分层。

全部为纯规则函数(无外部 IO),输出均为辅助建议,不替代临床判断。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools.adapters import adapt_model_func


# ============ 1. ASPECTS 评分 ============
_ASPECTS_REGIONS = {
    "M1": "前岛叶皮层", "M2": "岛叶外侧皮层", "M3": "后岛叶皮层",
    "M4": "M1 区", "M5": "M2 区", "M6": "M3 区",
    "insula": "岛叶", "lentiform": "豆状核", "caudate": "尾状核", "internal_capsule": "内囊后肢",
}


class ASPECTSInput(BaseModel):
    affected_regions: List[str] = Field(
        default_factory=list,
        description="CT 上出现低密度/肿胀的 ASPECTS 分区列表(可用: M1,M2,M3,M4,M5,M6,insula,lentiform,caudate,internal_capsule)",
    )
    side: str = Field(default="", description="受累半球(左/右),仅用于记录")


def _aspects_score(inputs: ASPECTSInput) -> Dict:
    valid = set(_ASPECTS_REGIONS)
    affected = [r for r in inputs.affected_regions if r in valid]
    unknown = [r for r in inputs.affected_regions if r not in valid]
    score = 10 - len(affected)
    if score <= 7:
        level = "大面积梗死高风险(ASPECTS≤7): 血管内治疗获益可能有限,需结合灌注影像综合评估"
    elif score <= 9:
        level = "中等: 存在早期缺血改变,建议进一步 CT 灌注/CTA 评估"
    else:
        level = "基本正常或轻微改变"
    return {
        "aspects_score": score,
        "affected_regions": [f"{r}({_ASPECTS_REGIONS[r]})" for r in affected],
        "unknown_regions": unknown,
        "interpretation": level,
        "note": "ASPECTS 需由影像科医师/卒中医师基于标准层面读片;本工具仅做计数辅助。",
    }


# ============ 2. CHA2DS2-VASc 评分 ============
class Cha2ds2Input(BaseModel):
    age: int = Field(description="年龄(岁)")
    sex: str = Field(default="男", description="性别(男/女)")
    congestive_heart_failure: bool = Field(default=False, description="充血性心力衰竭/LVEF≤40%")
    hypertension: bool = Field(default=False, description="高血压病史")
    diabetes: bool = Field(default=False, description="糖尿病病史")
    prior_stroke_tia: bool = Field(default=False, description="既往卒中/TIA/体循环栓塞史")
    vascular_disease: bool = Field(default=False, description="血管疾病(心梗/外周动脉病/主动脉斑块)")


def _cha2ds2_vasc(inputs: Cha2ds2Input) -> Dict:
    score = 0
    items = []
    if inputs.congestive_heart_failure:
        score += 1; items.append("充血性心力衰竭(+1)")
    if inputs.hypertension:
        score += 1; items.append("高血压(+1)")
    if inputs.age >= 75:
        score += 2; items.append("年龄≥75岁(+2)")
    elif 65 <= inputs.age < 75:
        score += 1; items.append("年龄65-74岁(+1)")
    if inputs.diabetes:
        score += 1; items.append("糖尿病(+1)")
    if inputs.prior_stroke_tia:
        score += 2; items.append("既往卒中/TIA(+2)")
    if inputs.vascular_disease:
        score += 1; items.append("血管疾病(+1)")
    if inputs.sex == "女":
        score += 1; items.append("女性(+1)")

    if inputs.sex == "女":
        annual_risk = {0: 0.2, 1: 0.6, 2: 2.0, 3: 3.7, 4: 4.9, 5: 6.9, 6: 7.6, 7: 8.2, 8: 8.4, 9: 9.7}.get(score, ">10")
        advice = "女性低危=0分,中危=1分,高危≥2分"
    else:
        annual_risk = {0: 0.2, 1: 0.6, 2: 2.2, 3: 3.2, 4: 4.8, 5: 7.2, 6: 9.7, 7: 11.2, 8: 10.8}.get(score, ">10")
        advice = "男性低危=0分,中危=1分,高危≥2分"

    risk_level = "低危" if score == 0 else ("中危" if score == 1 else "高危")
    suggestion = {
        "低危": "可暂不抗凝,定期随访",
        "中危": "综合出血风险考虑口服抗凝",
        "高危": "推荐口服抗凝(优先 NOAC),除非存在明确禁忌",
    }[risk_level]
    return {
        "cha2ds2_vasc_score": score,
        "items": items,
        "annual_stroke_risk_percent": annual_risk,
        "risk_level": risk_level,
        "suggestion": suggestion,
        "note": f"{advice}; 出血风险需同时用 HAS-BLED 评估。",
    }


# ============ 3. HAS-BLED 评分 ============
class HasBledInput(BaseModel):
    hypertension: bool = Field(default=False, description="未控制高血压(SBP>160mmHg)")
    abnormal_renal: bool = Field(default=False, description="肾功能异常(透析/移植/Cr>200μmol/L)")
    abnormal_liver: bool = Field(default=False, description="肝功能异常(肝硬化/胆红素>2倍+转氨酶>3倍)")
    prior_stroke: bool = Field(default=False, description="卒中史")
    bleeding_history: bool = Field(default=False, description="大出血史或出血倾向")
    labile_inr: bool = Field(default=False, description="INR 不稳定/治疗窗内时间<60%")
    elderly: bool = Field(default=False, description="年龄>65岁")
    antiplatelet_nsaid: bool = Field(default=False, description="联用抗血小板药或 NSAID")
    alcohol: bool = Field(default=False, description="酗酒(≥8 单位/周)")


def _has_bled(inputs: HasBledInput) -> Dict:
    score = 0
    items = []
    for flag, name, weight in (
        (inputs.hypertension, "高血压(+1)", 1),
        (inputs.abnormal_renal, "肾功能异常(+1)", 1),
        (inputs.abnormal_liver, "肝功能异常(+1)", 1),
        (inputs.prior_stroke, "卒中史(+1)", 1),
        (inputs.bleeding_history, "出血史(+1)", 1),
        (inputs.labile_inr, "INR 不稳定(+1)", 1),
        (inputs.elderly, "年龄>65(+1)", 1),
        (inputs.antiplatelet_nsaid, "抗血小板/NSAID(+1)", 1),
        (inputs.alcohol, "酗酒(+1)", 1),
    ):
        if flag:
            score += weight
            items.append(name)
    risk_level = "低危" if score <= 1 else ("中危" if score == 2 else "高危")
    suggestion = {
        "低危": "可常规抗凝,定期监测",
        "中危": "抗凝获益通常大于风险,加强随访与出血监测",
        "高危": "抗凝前需多学科评估,优先处理可逆因素(血压/INR/联用药物/酒精)",
    }[risk_level]
    return {
        "has_bled_score": score,
        "items": items,
        "risk_level": risk_level,
        "suggestion": suggestion,
        "note": "HAS-BLED≥3 提示高出血风险,但非抗凝禁忌,需综合获益风险个体化决策。",
    }


# ============ 4. 洼田饮水试验(吞咽筛查) ============
class SwallowInput(BaseModel):
    result: str = Field(
        description="洼田饮水试验结果: 1级(一次咽下无呛咳)/2级(分2次以上咽下无呛咳)/3级(一次咽下有呛咳)/4级(分2次以上咽下有呛咳)/5级(频繁呛咳不能咽下)或描述文本"
    )
    conscious: bool = Field(default=True, description="患者是否清醒可配合")


def _swallow_screen(inputs: SwallowInput) -> Dict:
    text = inputs.result.strip()
    level = None
    for i, kw in enumerate(["5级", "4级", "3级", "2级", "1级"], start=5):
        if kw in text:
            level = i
            break
    if level is None and "呛" in text:
        level = 3
    if level is None:
        level = 2

    labels = {
        1: "1级: 一次咽下,无呛咳",
        2: "2级: 分两次以上咽下,无呛咳",
        3: "3级: 一次咽下,有呛咳",
        4: "4级: 分两次以上咽下,有呛咳",
        5: "5级: 频繁呛咳,不能全部咽下",
    }
    if level >= 3:
        suggestion = "吞咽功能异常: 立即禁食禁水,留置胃管鼻饲,请康复科/言语治疗师评估,警惕误吸性肺炎"
        risk = "高"
    elif level == 2:
        suggestion = "可疑异常: 建议稠厚流质,床旁监护下进食,必要时行吞咽造影(VFSS)"
        risk = "中"
    else:
        suggestion = "基本正常: 常规饮食,继续观察"
        risk = "低"
    if not inputs.conscious:
        suggestion = "意识障碍者禁止经口进食,直接鼻饲并评估气道保护" + suggestion
        risk = "高"
    return {
        "level": labels[level],
        "aspiration_risk": risk,
        "suggestion": suggestion,
        "note": "洼田饮水试验为床旁初筛,阴性不能完全排除隐性误吸。",
    }


# ============ 5. rt-PA 溶栓后 24h 监测清单 ============
class RtpaMonitorInput(BaseModel):
    weight_kg: float = Field(description="体重(kg)")


def _rtpa_monitoring(inputs: RtpaMonitorInput) -> Dict:
    return {
        "checklist": [
            "血压监测: 溶栓开始后 q15min×2h → q30min×6h → q1h×16h(共24h);目标 <180/105 mmHg",
            "神经功能评估: 每次血压测量同时行 NIHSS 或简化神经查体",
            "血糖监测: 第 1h 内及之后 q4h,目标 3.9-10.0 mmol/L",
            "24h 内禁止: 抗血小板/抗凝药、留置尿管(除必要)、中心静脉穿刺(除必要)、鼻胃管",
            "出血征象观察: 头痛、呕吐、意识恶化、血压骤升、穿刺部位渗血 → 立即停药+急诊 CT",
            "sICH 应急预案: 若 NIHSS 增加≥4 或意识恶化,立即停溶栓、查血常规/凝血、备冷沉淀/血小板、急诊头颅 CT",
            "24h 复查头颅 CT 排除出血转化后,方可启动抗栓治疗",
        ],
        "bolus_dose_mg": round(0.09 * inputs.weight_kg, 1),
        "infusion_dose_mg": round(0.81 * inputs.weight_kg, 1),
        "note": "剂量仅供核对(总 0.9mg/kg,上限 90mg);以 rtpa_dose_calc 工具结果为准。",
    }


# ============ 6. 压疮/深静脉血栓预防清单 ============
class CareBundleInput(BaseModel):
    mobility: str = Field(default="卧床", description="活动能力(卧床/部分活动/可下床)")
    hemiplegia: bool = Field(default=False, description="是否有偏瘫")


def _care_bundle(inputs: CareBundleInput) -> Dict:
    dvt = []
    pressure = []
    if inputs.hemiplegia or inputs.mobility == "卧床":
        dvt.append("间歇充气加压装置(IPC)或梯度压力袜,除非存在禁忌")
        dvt.append("每日评估下肢肿胀/皮温,必要时超声筛查 DVT")
        dvt.append("无抗凝禁忌者按指南启动预防剂量抗凝(如依诺肝素 40mg qd),需个体化评估")
        pressure.append("每 2 小时翻身一次,使用气垫床/减压垫")
        pressure.append("骶尾部、足跟、肩胛骨等骨隆突处每日皮肤检查")
        pressure.append("保持皮肤清洁干燥,营养支持(蛋白/热量评估)")
    else:
        dvt.append("鼓励早期活动,充足水分摄入")
        pressure.append("常规皮肤观察,活动能力良好者风险较低")
    return {
        "dvt_prevention": dvt,
        "pressure_ulcer_prevention": pressure,
        "note": "清单为通用护理建议,具体以护理评估与医嘱为准。",
    }


# ============ 7. 出血转化风险分层 ============
class HtRiskInput(BaseModel):
    nihss_score: int = Field(description="NIHSS 总分")
    blood_glucose_mmol_l: float = Field(default=6.0, description="血糖 mmol/L")
    large_infarct: bool = Field(default=False, description="是否大面积梗死(如>1/3 MCA 供血区或 ASPECTS≤7)")
    atrial_fibrillation: bool = Field(default=False, description="房颤")
    received_thrombolysis: bool = Field(default=False, description="是否接受静脉溶栓")
    anticoagulant_use: bool = Field(default=False, description="是否使用抗凝药")


def _ht_risk(inputs: HtRiskInput) -> Dict:
    score = 0
    factors = []
    if inputs.nihss_score >= 15:
        score += 2; factors.append("NIHSS≥15(+2)")
    elif inputs.nihss_score >= 8:
        score += 1; factors.append("NIHSS 8-14(+1)")
    if inputs.blood_glucose_mmol_l >= 10:
        score += 2; factors.append(f"血糖 {inputs.blood_glucose_mmol_l}≥10mmol/L(+2)")
    elif inputs.blood_glucose_mmol_l >= 7.8:
        score += 1; factors.append("血糖 7.8-9.9mmol/L(+1)")
    if inputs.large_infarct:
        score += 3; factors.append("大面积梗死(+3)")
    if inputs.atrial_fibrillation:
        score += 1; factors.append("房颤(+1)")
    if inputs.received_thrombolysis:
        score += 2; factors.append("静脉溶栓(+2)")
    if inputs.anticoagulant_use:
        score += 2; factors.append("抗凝药使用(+2)")

    if score >= 6:
        level, plan = "高危", "24h 内密切监测神经功能(建议 q1-2h),溶栓后 24h 复查 CT;谨慎启动抗栓"
    elif score >= 3:
        level, plan = "中危", "加强神经功能监测,控制血糖与血压,溶栓后按指南复查 CT"
    else:
        level, plan = "低危", "常规监测,动态观察"
    return {
        "risk_score": score,
        "risk_level": level,
        "factors": factors or ["无明显高危因素"],
        "plan": plan,
        "note": "分层为规则辅助,不能替代影像随访与临床判断;溶栓后出现神经恶化须立即急诊 CT 排除 sICH。",
    }


# ============ 8. 出院随访计划生成 ============
class FollowupInput(BaseModel):
    subtype: str = Field(
        default="large_artery",
        description="TOAST 病因分型(large_artery/cardioembolic/small_vessel/other/undetermined)"
    )
    received_thrombolysis: bool = Field(default=False, description="是否接受静脉溶栓/取栓")
    anticoagulation_needed: bool = Field(default=False, description="是否需要长期抗凝(如心源性栓塞)")
    hypertension: bool = Field(default=True, description="高血压")
    diabetes: bool = Field(default=False, description="糖尿病")


def _followup_plan(inputs: FollowupInput) -> Dict:
    plans = []
    for node, months in (("3个月", 3), ("6个月", 6), ("12个月", 12)):
        items = [
            f"神经功能评估(NIHSS/mRS)、血压与血糖控制评估",
            f"用药依从性与不良反应核查(抗血小板{'/抗凝' if inputs.anticoagulation_needed else ''}、他汀)",
        ]
        if months >= 6:
            items.append("颈动脉超声/CTA 复查(评估血管再狭窄或斑块进展)")
        if months >= 12:
            items.append("年度综合评估: 心脏超声/Holter(如病因未明)、认知与抑郁筛查")
        plans.append({"node": node, "items": items})
    return {
        "followup_nodes": plans,
        "daily_management": [
            "血压: 家庭自测, 目标 <140/90 mmHg(合并糖尿病/肾病 <130/80)",
            "血糖: 每 3 个月查 HbA1c, 目标 <7%",
            "血脂: 他汀长期维持, LDL-C <1.8 mmol/L(高危)",
            "生活方式: 戒烟限酒、限盐(<5g/d)、每周≥150 分钟中等强度运动、体重管理",
            "康复: 吞咽/言语/肢体功能康复训练按需持续",
        ],
        "warning_signs": [
            "突发口角歪斜、肢体无力、言语不清 → 立即急诊(FAST)",
            "黑便/牙龈出血/皮肤瘀斑(抗栓治疗期) → 就医评估",
            "房颤患者出现心悸加重 → 复查心电图/Holter",
        ],
        "note": "随访计划为通用模板,需结合患者个体情况与出院医嘱个体化调整。",
    }


followup_plan_tool = StructuredTool.from_function(
    name="followup_plan",
    description="卒中出院随访计划生成(3/6/12个月随访节点、日常管理、预警信号)。",
    args_schema=FollowupInput,
    func=adapt_model_func(FollowupInput, _followup_plan),
)


# ============ 工具注册 ============
aspects_score_tool = StructuredTool.from_function(
    name="aspects_score",
    description="ASPECTS 早期缺血评分: 输入 CT 受累分区,输出 10 分制评分与大面积梗死风险分层。",
    args_schema=ASPECTSInput,
    func=adapt_model_func(ASPECTSInput, _aspects_score),
)
cha2ds2_vasc_tool = StructuredTool.from_function(
    name="cha2ds2_vasc_score",
    description="房颤卒中风险 CHA2DS2-VASc 评分: 输出评分、年卒中风险与抗凝建议。",
    args_schema=Cha2ds2Input,
    func=adapt_model_func(Cha2ds2Input, _cha2ds2_vasc),
)
has_bled_tool = StructuredTool.from_function(
    name="has_bled_score",
    description="抗凝出血风险 HAS-BLED 评分: 输出评分、风险分层与出血防控建议。",
    args_schema=HasBledInput,
    func=adapt_model_func(HasBledInput, _has_bled),
)
swallow_screen_tool = StructuredTool.from_function(
    name="swallow_screen",
    description="洼田饮水试验吞咽功能筛查: 输出分级、误吸风险与进食建议。",
    args_schema=SwallowInput,
    func=adapt_model_func(SwallowInput, _swallow_screen),
)
rtpa_monitor_tool = StructuredTool.from_function(
    name="rtpa_monitoring_checklist",
    description="rt-PA 静脉溶栓后 24 小时监测清单(血压/神经功能/血糖/禁忌操作/出血应急预案)。",
    args_schema=RtpaMonitorInput,
    func=adapt_model_func(RtpaMonitorInput, _rtpa_monitoring),
)
care_bundle_tool = StructuredTool.from_function(
    name="vte_pressure_ulcer_prevention",
    description="卒中卧床患者深静脉血栓(DVT)与压疮预防护理清单。",
    args_schema=CareBundleInput,
    func=adapt_model_func(CareBundleInput, _care_bundle),
)
ht_risk_tool = StructuredTool.from_function(
    name="hemorrhage_transformation_risk",
    description="急性缺血性卒中出血转化风险分层(NIHSS/血糖/梗死面积/房颤/溶栓/抗凝加权)。",
    args_schema=HtRiskInput,
    func=adapt_model_func(HtRiskInput, _ht_risk),
)

EXTRA_TOOLS = [
    aspects_score_tool,
    cha2ds2_vasc_tool,
    has_bled_tool,
    swallow_screen_tool,
    rtpa_monitor_tool,
    care_bundle_tool,
    ht_risk_tool,
    followup_plan_tool,
]

__all__ = ["EXTRA_TOOLS"]
