# jieba 与项目检索优化实验（2026-10-14）

最终采用向量/BM25等权RRF：每路召回80条，每桶融合保留80条，跨桶融合后只取12条规则重排；排序意图使用原始问题。中文医学词典和jieba仅作用于BM25，向量文本保持原样。

## 对照定义

| 配置 | 检索扩展 | BM25 | 每路召回 | 重排候选 | 排序查询 |
|---|---|---|---:|---:|---|
| 旧配置控制组 | 冻结旧扩展 | whitespace | 80 | 80 | 扩展查询 |
| 最终空白分词对照 | 冻结修复后扩展 | whitespace | 80 | 12 | 原始问题 |
| 最终配置 | 冻结修复后扩展 | jieba | 80 | 12 | 原始问题 |

全部共享持久化4861条语料、text-embedding-v2向量、collection路由、RRF k=60、规则重排和来源计分；请求top20，最终配置最多返回12条。旧控制组也使用修复后的来源身份、计分和BM25零命中过滤，**不是原HEAD严格代码基线**。

## 整套优化效果

| 题集 | 指标 | 旧配置控制组 | 最终配置 | 绝对变化 |
|---|---|---:|---:|---:|
| primary30（30题） | recall_at_3 | 0.8500 | 0.9167 | +0.0667 |
| primary30（30题） | recall_at_5 | 0.8833 | 0.9333 | +0.0500 |
| primary30（30题） | recall_at_10 | 0.9667 | 0.9833 | +0.0167 |
| primary30（30题） | mrr | 0.8468 | 0.8583 | +0.0115 |
| primary30（30题） | ndcg_at_10 | 0.8681 | 0.8814 | +0.0132 |
| secondary69（69题） | recall_at_3 | 0.3768 | 0.5652 | +0.1884 |
| secondary69（69题） | recall_at_5 | 0.4928 | 0.6377 | +0.1449 |
| secondary69（69题） | recall_at_10 | 0.5797 | 0.7826 | +0.2029 |
| secondary69（69题） | mrr | 0.3579 | 0.5371 | +0.1792 |
| secondary69（69题） | ndcg_at_10 | 0.4048 | 0.5893 | +0.1845 |

## 分词独立对照

相同新查询、80/12预算和原始排序意图，只改变BM25分词器：

| 题集 | 指标 | whitespace | jieba | 绝对变化 |
|---|---|---:|---:|---:|
| primary30（30题） | recall_at_3 | 0.8667 | 0.9167 | +0.0500 |
| primary30（30题） | recall_at_5 | 0.8667 | 0.9333 | +0.0667 |
| primary30（30题） | recall_at_10 | 0.9000 | 0.9833 | +0.0833 |
| primary30（30题） | mrr | 0.8056 | 0.8583 | +0.0528 |
| primary30（30题） | ndcg_at_10 | 0.8179 | 0.8814 | +0.0635 |
| secondary69（69题） | recall_at_3 | 0.5797 | 0.5652 | -0.0145 |
| secondary69（69题） | recall_at_5 | 0.6232 | 0.6377 | +0.0145 |
| secondary69（69题） | recall_at_10 | 0.7826 | 0.7826 | +0.0000 |
| secondary69（69题） | mrr | 0.4967 | 0.5371 | +0.0405 |
| secondary69（69题） | ndcg_at_10 | 0.5599 | 0.5893 | +0.0294 |

69题Recall@3净下降1题（-1.45个百分点），不能声称所有题集Recall@3都提高。下降3题、改善2题：

| 用例 | whitespace R@3 | jieba R@3 | 变化 |
|---|---:|---:|---:|
| etio-11 | 0.0000 | 1.0000 | +1.0000 |
| etio-13 | 1.0000 | 0.0000 | -1.0000 |
| tx-24 | 1.0000 | 0.0000 | -1.0000 |
| tx-29 | 0.0000 | 1.0000 | +1.0000 |
| tx-33 | 1.0000 | 0.0000 | -1.0000 |

## 实际运行与重放

30题由本项目 `python -m scripts.eval_ragas --retrieval-only --candidate-k 80 --rerank-k 12 --top-k 20` 分别实际执行jieba/whitespace，再从已有冻结候选按最终主实现顺序重放：两组全部30条查询、全部逐题5项指标及5项汇总结果完全一致。whitespace全部source/page排名一致；jieba的29题完全一致，diag-01前三条一致、第4位后存在页面/来源替换（JSON保留实际与重放两份排名）。差异未改变该题5项指标，但不能称所有页面排名完全一致。

实际运行文件为 `retrieval_final_jieba_20261014.json` / `retrieval_final_whitespace_20261014.json`。全部重排为 `rule_fallback`，没有测量答案生成RAGAS指标。

实际运行后 `eval_ragas.py` 和 `retrievers.py` 的文件指纹已有变化，运行时指纹保持原样。最终当前实现另外完成99题、两种分词的主引擎全链路复验：复用已保存的query embedding，执行实际Chroma检索，显式强制规则回退，无新增API调用；全部逐题指标及source/page排名与综合报告一致。复验保留当前实现指纹，见 `retrieval_current_validation_20261014.json` / `.md`，不验证在线embedding或在线重排服务。

## 溯源与限制

- 语料：4861条；anatomy=3184、guideline=234、etiology=586、treatment=711、prevention=146。
- 官方评测语料SHA-256：`edc77541da196ce90eebd93b20d45b8eb808519e5420b1f8db8a0ec042c53519`。
- 候选缓存语料SHA-256：`3ccc9ac3d1131491532d7624e2922add137bca7a627d77031a18aead48ba80ff`；两者序列化方式不同，定义记录于JSON。
- primary30源题集SHA-256：`6e6ccea1c8bd8301df6267d05b438ffdc1d76089f53fbffcad4d4befa2386190`；当前题目清单SHA-256：`251b8768bc5e901e999d4138a99d44380f5c5288a29075f51f0fa0ad25e30c4d`。
- secondary69源题集SHA-256：`143e3537b17173ae8b2d507ac544b7e9889d68ac4030659f4acbf58179920436`；当前题目清单SHA-256：`ce986a337a75514c933022614dcb634e81859281a19af2a7ef4b4288c8c2204c`。
- Python 3.12.4；jieba 0.42.1；rank-bm25 0.2.2；numpy 2.5.2；chromadb 1.5.9；langchain-core 1.5.4；langchain-chroma 1.1.0；dashscope 1.26.7。
- 外部100条题集排除与原30题相同的问题后余70条，再对etio-16/diag-10重复问题去重，保留69个不同问题。外部原文件未复制；报告仅保存当前问题复现清单。
- 来源身份采用NFKC、basename、去空白及casefold，教材第三版已知长名映射为 `neuroanatomy_clinical_cases.pdf`；只拆分.pdf后的多来源分隔符，保留单文件名逗号。两组共享该规则。
- 仅第一查询变体；未覆盖多变体聚合、不匹配过滤和答案生成，来源命中不证明片段语义正确或临床有效。
- 69题共享同一资料库，可能与30题语义近似；题集参与了配置探索，不是独立临床盲测。
- 本报告新计算旧控制组和重放最终配置的新增API调用为0；未进行额外调参。
- JSON保留逐题查询、指标、source/page排名、片段SHA-256、版本、语料/题集/实现hash，不包含片段正文或embedding。

## 项目验证

主任务最终验证：生产路由补修后，CI规定全集256项通过；最终30题检索硬门禁通过；离线安全/引用coverage=1、pass_rate=1。额外非CI的 `test_agentic_rag.py` 上次运行有7项失败，集中于旧mock只配置ainvoke而节点已使用astream、RetrieveNode旧kwargs断言；未修改这些历史测试。生产端到端回归另外覆盖Router富化只参与召回、原始问题重排、跨轮去重及路由数组同步对齐。
