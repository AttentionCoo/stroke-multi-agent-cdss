# 评测闭环(阶段6)

## 文件说明

| 文件 | 用途 |
|---|---|
| `BASELINE-2026-08-15.md` | 升级基线快照: 版本/RAGAS 指标/测试门禁/成本基线 |
| `ragas_snapshot.json` | 30 题 RAGAS 检索指标快照(机器可读, 与 regression_report.md 同源) |
| `regression_report.md` | 2026-08-08 的 30 题逐题检索回归报告 |
| `stroke_ragas.json` | 30 题 RAGAS 用例集(question/evidence_type/expected_source/ground_truth) |
| `bm25_tokenizer_ab_20261014.{json,md}` | 13份 PDF 整页的纯 BM25 分词对照，零 API 调用 |
| `retrieval_final_{whitespace,jieba}_20261014.{json,md}` | 同语料、同预算的30题最终真实混合检索分词对照 |
| `jieba_optimization_20261014.{json,md}` | 30题和69个额外去重问题的配置对照、分词对照及限制 |
| `retrieval_current_validation_20261014.{json,md}` | 当前主引擎99题复验：缓存embedding、真实Chroma查询、强制规则回退，无新增API调用 |
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

**任何检索相关变更后**: 必须在本地重跑 `eval_ragas` 生成新回归报告并检查门禁。
完整 RAGAS 评分完成后，再更新 `ragas_snapshot.json` 与 `regression_report.md`；仅检索实验单独保存，避免把旧答案评分当成新结果。

### jieba 检索对照

应用默认使用 `BM25_TOKENIZER=jieba`，重启模型服务或调用知识库热更新后，五个主题 collection 共用新分词器。索引和查询都使用相同的医学词典及搜索模式，Chroma embedding 无需重建。`whitespace` 用于分词对照，仍保留新检索器的无匹配过滤等公共逻辑，不等同于完整旧版代码。

默认每路召回 `RAG_RETRIEVAL_CANDIDATES=80` 个候选，跨桶融合后只重排 `RAG_RERANK_CANDIDATES=12` 个，返回上限受重排预算限制。请求 top3/top20 均以固定 top_n=12 重排后截取，前缀一致；如需返回超过12条，应统一增加重排预算再复测。评测可用 `--candidate-k` / `--rerank-k` 显式指定预算，须满足 `10 <= rerank-k <= candidate-k` 才能计算完整 Recall@10。

不需要密钥的整页 BM25 实验：

```bash
python -m scripts.eval_bm25 --output evaluation/bm25_tokenizer_ab_20261014.json
```

同一持久库的混合检索实验（需要 embedding 密钥，评测不会自动构库或生成 QA）：

```bash
python -m scripts.eval_ragas --retrieval-only --top-k 20 \
  --persist-dir /path/to/copied/chroma_db_unified --bm25-tokenizer whitespace \
  --report-path evaluation/retrieval_final_whitespace_20261014.md
python -m scripts.eval_ragas --retrieval-only --top-k 20 \
  --persist-dir /path/to/copied/chroma_db_unified --bm25-tokenizer jieba \
  --report-path evaluation/retrieval_final_jieba_20261014.md
python -m app.evaluation.gate --ragas evaluation/retrieval_final_jieba_20261014.json
```

每次生成同名 JSON 和 Markdown，保存来源排名、语料/题集指纹和实际 `rerank_layer`。Chroma 客户端可能升级数据库内部格式，跨版本实验应先复制持久库。题集缺失、向量库为空或 BM25 索引全空时失败，防止无效评测被当作成功。

来源匹配统一处理路径、全角字符、空白、QA 多来源以及教材历史短名；两种分词器使用同一口径。指标验证文献覆盖，不证明页面相关性或临床正确性；不能把新口径结果直接归因于相对旧快照的改进。混合评测只运行查询第一变体，不包含服务层多变体聚合和不匹配过滤。在线重排不可用时会记录 `rule_fallback`，此时结果仅代表规则回退路径。答案忠实度、正确性仍须完整 RAGAS 评分。

实际运行报告的实现指纹保留运行时版本。后续生产路由与并发隔离修复后的当前版本，另用缓存 query embedding 及真实 Chroma 查询完成99题、两种分词的复验，指标与综合报告一致；见 `retrieval_current_validation_20261014.md`。该复验强制规则回退，不测在线 embedding/gte-rerank 可用性。生产多变体和 Router 原始意图传递由端到端离线测试覆盖。

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
2. 历史 RAGAS 和新检索实验快照门禁(`--ragas`，分别保存答案评分与仅检索指标)
3. 离线规则评测门禁(`--gate`)
