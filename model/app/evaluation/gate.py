"""阶段6 评测闭环门禁。

把 BASELINE-2026-08-15.md 的硬门禁固化为可执行检查, 供 CI 与本地回归使用:

- RAGAS 检索指标硬门禁: Recall@3 / MRR / NDCG@10(检索相关变更不得低于基线)
- RAGAS 软门禁(仅告警): Recall@10 / faithfulness(小样本 LLM 评分噪声大, 不作硬门禁)
- 离线安全/引用规则评测门禁: coverage 与 pass_rate 阈值(由调用方传入)

CI 用法:
    python -m app.evaluation.gate --ragas evaluation/ragas_snapshot.json
    python -m app.evaluation.benchmark --cases ... --predictions ... --output ... \
        --gate --min-coverage 1.0 --min-pass-rate 0.8
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("eval_gate")

# 硬门禁(检索相关变更不得低于; 来源: BASELINE-2026-08-15.md)
RAGAS_HARD_GATES: Dict[str, float] = {
    "recall_at_3": 0.783,
    "mrr": 0.757,
    "ndcg_at_10": 0.763,
}
# 软门禁(仅告警, 不阻塞: faithfulness 为 qwen-plus 评分, 小样本噪声大)
RAGAS_WARN_GATES: Dict[str, float] = {
    "recall_at_10": 0.817,
    "faithfulness": 0.71,
}


@dataclass
class GateResult:
    passed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


def check_ragas_gate(metrics: Dict[str, float]) -> GateResult:
    """按 BASELINE 硬/软门禁检查 RAGAS 指标, 返回 GateResult。

    指标先四舍五入到 3 位小数再与基线对比(基线文档即 3 位小数展示值)。
    """
    failures: List[str] = []
    warnings: List[str] = []
    for key, threshold in RAGAS_HARD_GATES.items():
        value = _as_float(metrics.get(key))
        if value is None:
            failures.append(f"缺少硬门禁指标: {key}")
        elif round(value, 3) < threshold:
            failures.append(f"{key}={value:.4f} < 基线 {threshold}(降级!)")
    for key, threshold in RAGAS_WARN_GATES.items():
        value = _as_float(metrics.get(key))
        if value is not None and round(value, 3) < threshold:
            warnings.append(f"{key}={value:.4f} < 基线 {threshold}(软门禁, 仅告警)")
    result = GateResult(passed=not failures, failures=failures, warnings=warnings)
    if result.passed:
        logger.info("✅ RAGAS 检索门禁通过")
    else:
        logger.error("❌ RAGAS 检索门禁失败: %s", "; ".join(failures))
    for warning in warnings:
        logger.warning("⚠️ %s", warning)
    return result


def check_offline_gate(
    report: Dict,
    min_coverage: float,
    min_pass_rate: float,
) -> GateResult:
    """按覆盖率/通过率阈值检查离线规则评测报告。"""
    failures: List[str] = []
    coverage = _as_float(report.get("coverage"))
    pass_rate = _as_float(report.get("pass_rate"))
    if coverage is None or coverage < min_coverage:
        failures.append(f"coverage={coverage if coverage is not None else '缺失'} < {min_coverage}")
    if pass_rate is None or pass_rate < min_pass_rate:
        failures.append(f"pass_rate={pass_rate if pass_rate is not None else '缺失'} < {min_pass_rate}")
    return GateResult(passed=not failures, failures=failures)


def load_metrics(path: Path) -> Dict[str, float]:
    """加载 RAGAS 快照 JSON 中的 metrics。"""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data.get("metrics", data)


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="评测门禁检查(阶段6)")
    parser.add_argument("--ragas", type=Path, help="RAGAS 快照 JSON(检查检索硬门禁)")
    args = parser.parse_args()

    if args.ragas is None:
        parser.error("缺少 --ragas 参数")

    result = check_ragas_gate(load_metrics(args.ragas))
    if not result.passed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
