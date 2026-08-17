"""ICD-10 诊断编码工具(静态映射, 脑卒中相关优先)。

根据诊断描述关键词匹配候选 ICD-10-CM 编码并给出 DRG 分组提示。

医疗安全提示: 静态映射仅供辅助参考与演示, 正式病案编码必须由编码员人工复核。
"""

from __future__ import annotations

from typing import Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.tools.adapters import adapt_model_func

# 关键词 → (编码, 诊断名, DRG 提示)
_RULES: List[Dict] = [
    {"keywords": ["腔隙性脑梗死", "腔隙性梗死"], "code": "I63.8", "label": "腔隙性脑梗死", "drg": "急性缺血性卒中相关 DRG"},
    {"keywords": ["脑血栓形成", "血栓形成性脑梗死", "脑血栓"], "code": "I63.3", "label": "脑动脉血栓形成性脑梗死", "drg": "急性缺血性卒中相关 DRG"},
    {"keywords": ["脑栓塞", "心源性栓塞", "栓塞性脑梗死"], "code": "I63.4", "label": "脑动脉栓塞性脑梗死", "drg": "急性缺血性卒中相关 DRG"},
    {"keywords": ["缺血性卒中", "缺血性脑卒中", "脑梗死", "脑梗塞", "急性脑梗死"], "code": "I63.9", "label": "未特指的脑梗死", "drg": "急性缺血性卒中相关 DRG"},
    {"keywords": ["脑出血", "脑溢血", "颅内出血", "脑实质出血"], "code": "I61.9", "label": "未特指的颅内出血", "drg": "出血性卒中相关 DRG"},
    {"keywords": ["蛛网膜下腔出血", "蛛网膜下出血"], "code": "I60.9", "label": "未特指的蛛网膜下腔出血", "drg": "出血性卒中相关 DRG"},
    {"keywords": ["短暂性脑缺血发作", "短暂脑缺血", "tia"], "code": "G45.9", "label": "未特指的短暂性脑缺血发作", "drg": "TIA 相关 DRG"},
    {"keywords": ["高血压急症", "高血压危象"], "code": "I16.9", "label": "未特指的高血压急症", "drg": "高血压相关 DRG"},
    {"keywords": ["原发性高血压", "高血压病", "高血压"], "code": "I10", "label": "原发性高血压", "drg": "高血压相关 DRG"},
    {"keywords": ["心房颤动", "房颤", "心房纤颤"], "code": "I48.91", "label": "未特指的心房颤动", "drg": "心律失常相关 DRG"},
    {"keywords": ["高脂血症", "血脂异常", "高胆固醇血症"], "code": "E78.5", "label": "未特指的高脂血症", "drg": "代谢性疾病相关 DRG"},
    {"keywords": ["2型糖尿病", "ii型糖尿病", "二型糖尿病"], "code": "E11.9", "label": "未特指的 2 型糖尿病", "drg": "糖尿病相关 DRG"},
    {"keywords": ["颈动脉狭窄", "颈内动脉狭窄"], "code": "I65.2", "label": "颈内动脉狭窄或闭塞", "drg": "脑血管介入相关 DRG"},
    {"keywords": ["大脑中动脉闭塞", "mca闭塞", "m1段闭塞"], "code": "I66.0", "label": "大脑中动脉闭塞或狭窄", "drg": "脑血管介入相关 DRG"},
    {"keywords": ["深静脉血栓", "下肢深静脉血栓"], "code": "I82.40", "label": "未特指的下肢深静脉血栓", "drg": "静脉血栓相关 DRG"},
    {"keywords": ["动脉粥样硬化", "动脉硬化"], "code": "I70.9", "label": "未特指的全身性动脉粥样硬化", "drg": "动脉硬化相关 DRG"},
    {"keywords": ["偏瘫", "半身不遂"], "code": "G81.9", "label": "未特指的偏瘫", "drg": "神经系统康复相关 DRG"},
    {"keywords": ["失语", "运动性失语", "感觉性失语"], "code": "R47.01", "label": "失语症", "drg": "神经系统症状相关 DRG"},
    {"keywords": ["吞咽困难", "吞咽障碍"], "code": "R13.10", "label": "未特指的吞咽困难", "drg": "神经系统症状相关 DRG"},
    {"keywords": ["意识障碍", "昏迷"], "code": "R40.20", "label": "未特指的昏迷", "drg": "神经系统症状相关 DRG"},
]


class Icd10Input(BaseModel):
    """诊断描述文本(中文/英文均可)。"""

    diagnosis: str = Field(min_length=2, max_length=500, description="诊断描述, 如'急性缺血性脑卒中, 左侧大脑中动脉闭塞'")


def _icd10_coding(inputs: Icd10Input) -> Dict:
    text = str(inputs.diagnosis or "").strip().lower()
    matches = []
    for rule in _RULES:
        if any(str(kw).lower() in text for kw in rule["keywords"]):
            matches.append({
                "code": rule["code"],
                "label": rule["label"],
                "drg_hint": rule["drg"],
                "matched_keyword": next(kw for kw in rule["keywords"] if str(kw).lower() in text),
            })
    # 去重(同一编码只保留一次, 按规则顺序)
    seen = set()
    unique = []
    for m in matches:
        if m["code"] not in seen:
            seen.add(m["code"])
            unique.append(m)

    return {
        "diagnosis": inputs.diagnosis,
        "matched_count": len(unique),
        "codes": unique,
        "note": "静态关键词映射, 仅供辅助参考与演示, 正式病案编码须由编码员人工复核确认。",
    }


icd10_coding_tool = StructuredTool.from_function(
    name="icd10_coding",
    description=(
        "ICD-10 诊断编码查询: 输入诊断描述, 返回匹配的 ICD-10-CM 候选编码/诊断名/DRG 分组提示 "
        "(脑卒中相关病种优先, 静态映射)。"
    ),
    args_schema=Icd10Input,
    func=adapt_model_func(Icd10Input, _icd10_coding),
)

ICD_TOOLS: List[StructuredTool] = [icd10_coding_tool]
