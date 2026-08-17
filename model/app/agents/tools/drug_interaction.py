"""药物-药物相互作用(DDI)检查工具。

内置脑卒中人群常用药物的 DDI 知识库(通用名 + 别名), 对给定药物列表做两两交互检查,
返回严重度/机制/处置建议。

医疗安全提示: 本工具基于静态知识库, 不能替代药理学审核与临床药师判断。
"""

from __future__ import annotations

from typing import Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools.adapters import adapt_model_func

# 别名 → 规范名(检查/展示用规范名)
ALIASES: Dict[str, str] = {
    # 溶栓
    "阿替普酶": "阿替普酶", "alteplase": "阿替普酶", "爱通立": "阿替普酶",
    "rt-pa": "阿替普酶", "rtpa": "阿替普酶",
    # 抗凝
    "华法林": "华法林", "warfarin": "华法林",
    "肝素": "肝素", "普通肝素": "肝素", "heparin": "肝素", "肝素钠": "肝素",
    "低分子肝素": "低分子肝素", "依诺肝素": "低分子肝素", "enoxaparin": "低分子肝素",
    "那屈肝素": "低分子肝素", "达肝素": "低分子肝素",
    "达比加群": "达比加群", "达比加群酯": "达比加群", "dabigatran": "达比加群",
    "利伐沙班": "利伐沙班", "rivaroxaban": "利伐沙班",
    "阿哌沙班": "阿哌沙班", "apixaban": "阿哌沙班",
    # 抗血小板
    "阿司匹林": "阿司匹林", "aspirin": "阿司匹林", "拜阿司匹林": "阿司匹林", "乙酰水杨酸": "阿司匹林",
    "氯吡格雷": "氯吡格雷", "clopidogrel": "氯吡格雷",
    "替格瑞洛": "替格瑞洛", "ticagrelor": "替格瑞洛",
    # NSAIDs
    "布洛芬": "布洛芬", "ibuprofen": "布洛芬", "芬必得": "布洛芬",
    "双氯芬酸": "双氯芬酸", "diclofenac": "双氯芬酸",
    "萘普生": "萘普生", "naproxen": "萘普生",
    # PPI
    "奥美拉唑": "奥美拉唑", "omeprazole": "奥美拉唑",
    "埃索美拉唑": "埃索美拉唑", "艾司奥美拉唑": "埃索美拉唑", "esomeprazole": "埃索美拉唑",
    # 他汀
    "阿托伐他汀": "阿托伐他汀", "atorvastatin": "阿托伐他汀", "立普妥": "阿托伐他汀",
    "辛伐他汀": "辛伐他汀", "simvastatin": "辛伐他汀",
    "瑞舒伐他汀": "瑞舒伐他汀", "rosuvastatin": "瑞舒伐他汀",
    # CYP 抑制剂/诱导剂
    "克拉霉素": "克拉霉素", "clarithromycin": "克拉霉素",
    "伊曲康唑": "伊曲康唑", "itraconazole": "伊曲康唑",
    "酮康唑": "酮康唑", "ketoconazole": "酮康唑",
    "红霉素": "红霉素", "erythromycin": "红霉素",
    "吉非罗齐": "吉非罗齐", "gemfibrozil": "吉非罗齐",
    "胺碘酮": "胺碘酮", "amiodarone": "胺碘酮",
    "环丙沙星": "环丙沙星", "ciprofloxacin": "环丙沙星",
    "左氧氟沙星": "左氧氟沙星", "levofloxacin": "左氧氟沙星",
    "利福平": "利福平", "rifampicin": "利福平", "利福霉素": "利福平",
    # 抗抑郁(SSRI)
    "氟西汀": "氟西汀", "fluoxetine": "氟西汀",
    "舍曲林": "舍曲林", "sertraline": "舍曲林",
    "帕罗西汀": "帕罗西汀", "paroxetine": "帕罗西汀",
    # CCB
    "硝苯地平": "硝苯地平", "nifedipine": "硝苯地平",
}

# 交互条目: frozenset({规范A, 规范B}) → 严重度/机制/建议
_INTERACTIONS = {
    frozenset({"阿替普酶", "华法林"}): {
        "severity": "严重", "mechanism": "溶栓联合抗凝显著增加颅内及其他大出血风险",
        "advice": "溶栓前评估凝血功能与出血史; 溶栓 24h 内避免启用抗凝",
    },
    frozenset({"阿替普酶", "肝素"}): {
        "severity": "严重", "mechanism": "溶栓联合肝素增加出血风险",
        "advice": "溶栓开始后至少 24h 内避免抗凝(个体化权衡)",
    },
    frozenset({"阿替普酶", "低分子肝素"}): {
        "severity": "严重", "mechanism": "溶栓联合 LMWH 增加出血风险",
        "advice": "参照指南: 溶栓 24h 内不常规联合抗凝",
    },
    frozenset({"阿司匹林", "氯吡格雷"}): {
        "severity": "中度", "mechanism": "双联抗血小板增加出血风险",
        "advice": "仅短期双抗(如支架术后)并按出血风险个体化; 长期联用需评估",
    },
    frozenset({"阿司匹林", "华法林"}): {
        "severity": "严重", "mechanism": "抗血小板+抗凝显著增加出血风险",
        "advice": "仅在房颤+缺血事件等明确指征下联用, 密切监测出血",
    },
    frozenset({"阿司匹林", "布洛芬"}): {
        "severity": "中度", "mechanism": "布洛芬竞争 COX-1 位点, 削弱阿司匹林抗血小板作用并叠加胃肠出血",
        "advice": "避免联用; 必须止痛时优先对乙酰氨基酚等",
    },
    frozenset({"氯吡格雷", "奥美拉唑"}): {
        "severity": "中度", "mechanism": "奥美拉唑强抑制 CYP2C19, 降低氯吡格雷活性代谢物浓度",
        "advice": "换用泮托拉唑/雷贝拉唑等影响较小的 PPI, 或评估替格瑞洛",
    },
    frozenset({"氯吡格雷", "埃索美拉唑"}): {
        "severity": "中度", "mechanism": "埃索美拉唑抑制 CYP2C19, 降低氯吡格雷疗效",
        "advice": "优先泮托拉唑/雷贝拉唑, 或换抗血小板方案",
    },
    frozenset({"氯吡格雷", "利福平"}): {
        "severity": "中度", "mechanism": "利福平诱导 CYP 代谢, 降低氯吡格雷活性浓度",
        "advice": "评估抗血小板疗效或更换方案",
    },
    frozenset({"阿托伐他汀", "克拉霉素"}): {
        "severity": "中度", "mechanism": "克拉霉素抑制 CYP3A4, 升高他汀暴露, 增加肌病风险",
        "advice": "联用时降低他汀剂量或暂停, 监测肌痛/肌酶",
    },
    frozenset({"辛伐他汀", "克拉霉素"}): {
        "severity": "中度", "mechanism": "克拉霉素抑制 CYP3A4, 显著升高辛伐他汀暴露",
        "advice": "联用期间停用辛伐他汀或换非 CYP3A4 代谢他汀",
    },
    frozenset({"瑞舒伐他汀", "克拉霉素"}): {
        "severity": "轻度", "mechanism": "克拉霉素轻度升高瑞舒伐他汀暴露",
        "advice": "常规剂量安全, 监测肌痛/肌酶",
    },
    frozenset({"辛伐他汀", "吉非罗齐"}): {
        "severity": "严重", "mechanism": "吉非罗齐显著升高辛伐他汀浓度, 横纹肌溶解风险高",
        "advice": "禁止联用; 换非诺贝特并监测肌酶",
    },
    frozenset({"华法林", "胺碘酮"}): {
        "severity": "严重", "mechanism": "胺碘酮抑制华法林代谢, INR 显著升高",
        "advice": "联用时华法林剂量减 1/3~1/2, 加密 INR 监测",
    },
    frozenset({"华法林", "环丙沙星"}): {
        "severity": "中度", "mechanism": "氟喹诺酮类增强华法林抗凝作用, INR 升高",
        "advice": "联用期间加密 INR 监测并适当减量",
    },
    frozenset({"华法林", "左氧氟沙星"}): {
        "severity": "中度", "mechanism": "氟喹诺酮类增强华法林抗凝作用, INR 升高",
        "advice": "联用期间加密 INR 监测并适当减量",
    },
    frozenset({"华法林", "布洛芬"}): {
        "severity": "严重", "mechanism": "NSAIDs 增加华法林出血风险(血小板+黏膜)",
        "advice": "避免联用; 必须使用优先短疗程 COX-2 选择性药物并监测出血",
    },
    frozenset({"替格瑞洛", "酮康唑"}): {
        "severity": "严重", "mechanism": "强 CYP3A4 抑制剂显著升高替格瑞洛暴露",
        "advice": "避免联用强 CYP3A4 抑制剂",
    },
    frozenset({"替格瑞洛", "辛伐他汀"}): {
        "severity": "中度", "mechanism": "替格瑞洛升高辛伐他汀暴露",
        "advice": "辛伐他汀剂量不超过 40mg/日",
    },
    frozenset({"氟西汀", "华法林"}): {
        "severity": "中度", "mechanism": "SSRI 抑制血小板功能并影响华法林代谢, 出血风险升高",
        "advice": "联用期间监测出血体征与 INR",
    },
    frozenset({"舍曲林", "华法林"}): {
        "severity": "中度", "mechanism": "SSRI 增加抗凝出血风险",
        "advice": "联用期间监测出血体征与 INR",
    },
    frozenset({"硝苯地平", "克拉霉素"}): {
        "severity": "中度", "mechanism": "克拉霉素抑制 CYP3A4, 升高硝苯地平暴露致低血压",
        "advice": "联用期间监测血压, 必要时减量",
    },
    frozenset({"低分子肝素", "阿司匹林"}): {
        "severity": "中度", "mechanism": "LMWH 联合抗血小板增加出血风险",
        "advice": "按指征短期联用(如急性期), 监测出血",
    },
}


class DrugInteractionInput(BaseModel):
    """待检查的药物列表(通用名/商品名/英文名均可)。"""

    drugs: List[str] = Field(
        min_length=2, max_length=8,
        description="待检查的药物列表, 至少 2 种, 最多 8 种",
    )


def _normalize(drug: str) -> str | None:
    """别名 → 规范名(大小写不敏感, 去空白); 未收录返回 None。"""
    key = str(drug or "").strip().lower()
    return ALIASES.get(key) or ALIASES.get(str(drug or "").strip())


def _drug_interaction_check(inputs: DrugInteractionInput) -> Dict:
    canonical: List[str] = []
    unknown: List[str] = []
    for raw in inputs.drugs:
        name = _normalize(raw)
        if name is None:
            unknown.append(str(raw).strip())
        elif name not in canonical:
            canonical.append(name)

    interactions = []
    for i in range(len(canonical)):
        for j in range(i + 1, len(canonical)):
            pair = frozenset({canonical[i], canonical[j]})
            entry = _INTERACTIONS.get(pair)
            if entry:
                interactions.append({
                    "drug_a": canonical[i],
                    "drug_b": canonical[j],
                    "severity": entry["severity"],
                    "mechanism": entry["mechanism"],
                    "advice": entry["advice"],
                })

    interactions.sort(key=lambda x: {"严重": 0, "中度": 1, "轻度": 2}.get(x["severity"], 3))

    return {
        "checked_drugs": canonical,
        "unknown_drugs": unknown,
        "interaction_count": len(interactions),
        "interactions": interactions,
        "note": "基于静态 DDI 知识库, 仅供辅助参考, 请由药师/医生结合临床审核。",
    }


drug_interaction_check_tool = StructuredTool.from_function(
    name="drug_interaction_check",
    description=(
        "检查药物-药物相互作用(DDI): 输入患者正在使用/拟使用的药物列表(通用名或商品名), "
        "返回两两交互的严重度/机制/处置建议(严重/中度/轻度)。"
    ),
    args_schema=DrugInteractionInput,
    func=adapt_model_func(DrugInteractionInput, _drug_interaction_check),
)

DDI_TOOLS: List[StructuredTool] = [drug_interaction_check_tool]
