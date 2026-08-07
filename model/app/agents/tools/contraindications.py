"""禁忌症检查工具

复用 rules_config.yaml 中的禁忌症规则,对患者信息做关键词匹配检查。
支持的治疗方式:溶栓 / 抗凝 / 双抗(与配置一致)。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools._compat import model_func
from app.config.config_loader import get_validation_manager

# 患者信息中常见同义表述 → 规则关键词(提高命中率)
_SYNONYMS = {
    "血小板<100": ["血小板<100", "血小板低于100", "血小板减少", "plt<100", "血小板 100"],
    "血小板低": ["血小板<100", "血小板低于100", "血小板减少", "plt<100"],
    "血压超180/110": ["180/110", "血压180", "收缩压180", "高压180", "血压超180"],
    "活动性出血": ["活动性出血", "活动出血", "消化道出血", "脑出血", "颅内出血", "鼻出血", "牙龈出血", "血尿", "黑便", "呕血"],
    "近期大手术": ["近期手术", "大手术", "外科手术", "术后", "手术史"],
    "头颅CT高密度": ["ct高密度", "ct示高密度", "高密度影", "ct见高密度"],
    "出血倾向": ["出血倾向", "凝血异常", "凝血功能异常", "血小板低", "血小板减少", "易出血"],
    "活动性溃疡": ["活动性溃疡", "胃溃疡", "十二指肠溃疡", "消化性溃疡"],
    "既往脑出血史": ["既往脑出血", "脑出血史", "曾有脑出血", "出血性卒中史", "脑溢血"],
}

# 否定表述:命中这些短语时,即使出现规则关键词也不判为阳性(排除误杀)
_NEGATION_PATTERNS = [
    "未见出血", "无出血", "未见高密度", "无高密度", "未见明显出血", "排除出血",
    "未见脑出血", "无脑出血", "无颅内出血", "未见颅内出血", "ct未见出血",
    "未提示出血", "没有出血", "未见活动性出血", "无活动性出血",
    "出血已止", "无出血倾向", "未见异常", "正常",
]

# 语境敏感的规则:只有"阳性语境"才命中(避免"CT平扫"误判为"CT高密度")
_CONTEXT_SENSITIVE_RULES = {
    "头颅CT高密度": [
        # 阳性语境:明确描述高密度/出血
        ("阳性", ["高密度", "高密度影", "ct示高密度", "ct见高密度", "出血灶", "出血表现"]),
        # 阴性语境:描述平扫/未见异常等,不命中
        ("阴性", ["平扫", "未见异常", "未见出血", "排除出血"]),
    ],
    "活动性出血": [
        ("阳性", ["活动性出血", "活动出血", "消化道出血", "脑出血", "颅内出血", "鼻出血", "牙龈出血", "血尿", "黑便", "呕血"]),
        ("阴性", ["未见活动性出血", "无活动性出血", "出血已止", "无出血", "排除出血"]),
    ],
}

_RULE_ALIASES = {
    "溶栓": ["溶栓", "静脉溶栓", "阿替普酶", "rt-pa", "rtpa", "rt pa", "尿激酶"],
    "抗凝": ["抗凝", "华法林", "低分子肝素", "肝素", "利伐沙班", "达比加群", "阿哌沙班"],
    "双抗": ["双抗", "阿司匹林", "氯吡格雷", "替格瑞洛", "双联抗血小板"],
}


def _has_negation(text: str, window: int = 40) -> bool:
    """判断文本中是否出现否定/排除表述(命中则不应判为阳性)。"""
    lower_text = text.lower()
    for neg in _NEGATION_PATTERNS:
        idx = lower_text.find(neg.lower())
        if idx != -1:
            return True
    return False


def _matches(text: str, rule: str) -> bool:
    """判断患者信息文本是否命中某条规则(支持同义词表、数值匹配与否定语义识别)。"""
    lower_text = text.lower()

    # 否定表述优先:明确"未见出血/排除出血"等,不再命中出血类规则
    if rule in ("头颅CT高密度", "活动性出血", "出血倾向", "既往脑出血史") and _has_negation(lower_text):
        return False

    # 语境敏感规则:CT 平扫/未见异常 ≠ CT 高密度(出血)
    if rule in _CONTEXT_SENSITIVE_RULES:
        groups = _CONTEXT_SENSITIVE_RULES[rule]
        # 先查阳性语境
        for label, keywords in groups:
            if label == "阳性":
                if any(k.lower() in lower_text for k in keywords):
                    return True
            else:
                # 阴性语境命中 → 直接不判阳性
                if any(k.lower() in lower_text for k in keywords):
                    return False
        return False  # 只有阳性语境才命中,其余一律不判

    rule_lower = rule.lower()
    if rule_lower in lower_text:
        return True
    # 同义表述
    candidates = _SYNONYMS.get(rule, [])
    for cand in candidates:
        if cand.lower() in lower_text:
            return True
    # 数值规则:血小板<100 → 匹配 "血小板 XX" 且数值 < 100
    m = re.search(r"血小板\s*[<＜]?\s*(\d+)", lower_text)
    if m and ("血小板" in rule_lower or "plt" in rule_lower):
        try:
            if int(m.group(1)) < 100:
                return True
        except ValueError:
            pass
    # 数值规则:血压超180/110 → 匹配 "血压 xxx/yyy" 且 收缩压>180 或 舒张压>110
    if "180" in rule_lower or "110" in rule_lower:
        bp = re.search(r"血压\s*[=:]?\s*(\d{2,3})\s*[/／]\s*(\d{2,3})", lower_text)
        if bp:
            try:
                systolic, diastolic = int(bp.group(1)), int(bp.group(2))
                if systolic > 180 or diastolic > 110:
                    return True
            except ValueError:
                pass
        # 单值形式:收缩压185 / 高压185 / 血压185
        single = re.search(r"(?:收缩压|高压|血压)\s*[=:]?\s*(1[89]\d|2\d\d)", lower_text)
        if single:
            try:
                if int(single.group(1)) > 180:
                    return True
            except ValueError:
                pass
    return False


class ContraindicationInput(BaseModel):
    """禁忌症检查输入。"""

    treatment: str = Field(
        description="治疗方式,可选值:溶栓 / 抗凝 / 双抗"
    )
    patient_info: str = Field(
        description="患者信息文本(主诉、病史、检查结果等),用于匹配禁忌症规则"
    )


def _check_contraindication(inputs: ContraindicationInput) -> Dict:
    treatment = inputs.treatment.strip()
    patient_text = inputs.patient_info or ""
    try:
        rules_map = get_validation_manager().get_contraindication_rules()
    except Exception:
        # 配置加载失败时使用内置默认规则(与 rules_config.yaml 一致)
        rules_map = {
            "溶栓": ["近期大手术", "活动性出血", "血小板<100", "血压超180/110", "头颅CT高密度"],
            "抗凝": ["出血倾向", "活动性溃疡"],
            "双抗": ["既往脑出血史"],
        }

    # 找到匹配的治疗方式键(支持别名,如 "rt-pa"/"阿替普酶" → 溶栓)
    matched_key = None
    for key in rules_map:
        if treatment == key or treatment in key or key in treatment:
            matched_key = key
            break
    if matched_key is None:
        for key, aliases in _RULE_ALIASES.items():
            if any(alias in treatment.lower() for alias in aliases):
                matched_key = key
                break
    if matched_key is None:
        return {
            "valid": False,
            "supported_treatments": list(rules_map.keys()),
            "error": f"不支持的治疗方式: {treatment}",
        }

    rules = rules_map[matched_key]
    hits = [rule for rule in rules if _matches(patient_text, rule)]

    return {
        "valid": True,
        "treatment": matched_key,
        "checked_rules": rules,
        "hits": hits,
        "passed": len(hits) == 0,
        "conclusion": (
            "未检出禁忌症,但需结合完整病史、影像与实验室检查综合判断。"
            if not hits
            else f"检出 {len(hits)} 项潜在禁忌症,需进一步确认并评估风险收益比。"
        ),
        "note": "规则引擎为关键词匹配,仅供快速筛查;阴性结果不能排除禁忌症。",
    }


contraindication_check_tool = StructuredTool.from_function(
    name="contraindication_check",
    description=(
        "对指定治疗方式(溶栓/抗凝/双抗)检查患者信息中的禁忌症:"
        "输入治疗方式与患者病史文本,返回命中的禁忌症规则及结论。"
    ),
    args_schema=ContraindicationInput,
    func=model_func(ContraindicationInput, _check_contraindication),
)

CONTRAINDICATION_TOOLS = [contraindication_check_tool]

__all__ = ["CONTRAINDICATION_TOOLS", "contraindication_check_tool"]
