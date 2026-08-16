"""阶段6 评测闭环门禁测试(纯逻辑, 无需真实 API)。

运行: pytest tests/test_evaluation_gate.py -v
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from app.evaluation.gate import (
    RAGAS_HARD_GATES, RAGAS_WARN_GATES,
    check_ragas_gate, check_offline_gate, load_metrics,
)

_EVAL_DIR = Path(__file__).resolve().parent.parent / "evaluation"


def test_baseline_snapshot_passes_hard_gates():
    """冻结的基线快照必须通过硬门禁(自洽性: 基线不低于基线)。"""
    result = check_ragas_gate(load_metrics(_EVAL_DIR / "ragas_snapshot.json"))
    assert result.passed
    assert result.failures == []


def test_degraded_retrieval_fails_hard_gate():
    metrics = {"recall_at_3": 0.60, "mrr": 0.50, "ndcg_at_10": 0.40}
    result = check_ragas_gate(metrics)
    assert not result.passed
    assert len(result.failures) == 3
    assert any("recall_at_3" in failure for failure in result.failures)


def test_missing_metric_fails_hard_gate():
    result = check_ragas_gate({"recall_at_3": 0.9})
    assert not result.passed
    assert any("mrr" in failure for failure in result.failures)


def test_faithfulness_only_warns():
    """faithfulness 是软门禁: 低于基线只告警不阻塞。"""
    result = check_ragas_gate({
        "recall_at_3": 0.8, "mrr": 0.76, "ndcg_at_10": 0.77,
        "recall_at_10": 0.82, "faithfulness": 0.5,
    })
    assert result.passed
    assert any("faithfulness" in warning for warning in result.warnings)


def test_offline_gate_thresholds():
    ok = {"coverage": 1.0, "pass_rate": 0.9}
    assert check_offline_gate(ok, min_coverage=1.0, min_pass_rate=0.8).passed
    bad = {"coverage": 0.5, "pass_rate": 0.6}
    result = check_offline_gate(bad, min_coverage=1.0, min_pass_rate=0.8)
    assert not result.passed
    assert len(result.failures) == 2


def test_frozen_offline_predictions_all_pass():
    """冻结的离线安全/引用规则预测必须全部通过(回归金丝雀)。"""
    from app.evaluation.benchmark import load_jsonl, load_predictions, run_benchmark
    report = run_benchmark(
        load_jsonl(_EVAL_DIR / "offline_cases.jsonl"),
        load_predictions(_EVAL_DIR / "offline_predictions.jsonl"),
    )
    assert report["coverage"] == 1.0
    assert report["pass_rate"] == 1.0


def test_hard_gate_thresholds_match_baseline_doc():
    """硬门禁阈值与 BASELINE-2026-08-15.md 一致。"""
    assert RAGAS_HARD_GATES == {"recall_at_3": 0.783, "mrr": 0.757, "ndcg_at_10": 0.763}
    assert RAGAS_WARN_GATES["recall_at_10"] == 0.817
    assert RAGAS_WARN_GATES["faithfulness"] == 0.71


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
