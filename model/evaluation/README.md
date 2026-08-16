# 评测闭环(阶段6)

## 文件说明

| 文件 | 用途 |
|---|---|
| `BASELINE-2026-08-15.md` | 升级基线快照: 版本/RAGAS 指标/测试门禁/成本基线 |
| `ragas_snapshot.json` | 30 题 RAGAS 检索指标快照(机器可读, 与 regression_report.md 同源) |
| `regression_report.md` | 2026-08-08 的 30 题逐题检索回归报告 |
| `stroke_ragas.json` | 30 题 RAGAS 用例集(question/evidence_type/expected_source/ground_truth) |
| `offline_cases.jsonl` | 离线安全/引用规则用例(6 题: 禁止剂量/禁止确诊语气/引用白名单) |
| `offline_predictions.jsonl` | 上述用例的冻结真实模型输出(回归金丝雀, 升级后需重跑刷新) |

## 两级门禁

### 1. RAGAS 检索硬门禁(检索变更必查)

```bash
# 本地全量重跑(需 DASHSCOPE 密钥 + 向量库 + ragas):
python -m scripts.eval_ragas --max-cases 30 --top-k 20
# 快照门禁(CI 每次执行):
python -m app.evaluation.gate --ragas evaluation/ragas_snapshot.json
```

硬门禁: Recall@3 ≥ 0.783 / MRR ≥ 0.757 / NDCG@10 ≥ 0.763(不达标 exit 1)。
软门禁(仅告警): Recall@10 ≥ 0.817 / faithfulness ≥ 0.71。

**任何检索相关变更后**: 必须在本地重跑 `eval_ragas` 生成新回归报告,
对比基线不降级后, 更新 `ragas_snapshot.json` 与 `regression_report.md` 再合入。

### 2. 离线安全/引用规则门禁(CI 每次执行)

```bash
python -m app.evaluation.benchmark \
  --cases evaluation/offline_cases.jsonl \
  --predictions evaluation/offline_predictions.jsonl \
  --output /tmp/offline_report.json \
  --gate --min-coverage 1.0 --min-pass-rate 0.8
```

检查: 必需术语出现、禁止内容(具体剂量/确诊语气)不出现、引用限定白名单。

**模型层升级后**: 用新版本重新生成各用例的真实输出并替换 `offline_predictions.jsonl`
(逐条人工确认符合安全规则), 再提交。

## CI 集成

`.github/workflows/ci.yml` 的 model job:
1. 离线测试全集(含 test_evaluation_gate.py 的自洽性检查)
2. RAGAS 快照门禁(`--ragas`)
3. 离线规则评测门禁(`--gate`)
