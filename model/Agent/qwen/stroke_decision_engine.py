# StrokeDecisionEngine.py — 已降级，不再被主流程调用
# 保留作为可选的结构化特征提取器 / 实验对照组

import json
import logging
from typing import Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StrokeResult:
    most_likely: str = ""
    mechanism: str = ""
    time_window: str = ""
    probabilities: Dict[str, float] = field(default_factory=dict)
    extracted_features: List[str] = field(default_factory=list)
    recommendation: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


_TYPE_CN_MAP = {
    "Ischemic": "缺血性卒中",
    "Hemorrhage": "出血性卒中",
    "SAH": "蛛网膜下腔出血",
    "TIA": "短暂性脑缺血发作",
}

_MECHANISM_CN_MAP = {
    "LargeArtery": "大动脉粥样硬化型",
    "Cardioembolic": "心源性栓塞型",
    "