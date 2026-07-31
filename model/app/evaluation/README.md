# 离线评测

本目录提供可复现的安全与引用规则评测，不调用或修改现有大模型推理流程。

## 数据格式

- `benchmark_cases.jsonl`：脱敏合成病例与预期规则，目前均标记为 `synthetic_unreviewed`。
- 预测文件：每行包含 `id` 与模型原始 `output`。
- 输出：JSON 机器报告与同名 Markdown 摘要，并记录病例集和预测文件 SHA-256。

## 运行

```bash
python -m app.evaluation.benchmark \
  --cases app/evaluation/benchmark_cases.jsonl \
  --predictions app/evaluation/predictions.example.jsonl \
  --output app/evaluation/results/smoke-report.json
```

示例预测只用于验证评测管线，不能作为模型准确率、临床有效性或专家盲评结果。
正式评测前应由神经内科专家审阅病例与预期规则，并保存模型版本、知识库版本和完整预测文件。
