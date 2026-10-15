# 当前主检索链路离线复验（2026-10-14）

以当前 UnifiedSearchEngine.search 实际查询隔离 Chroma。只复用历史 query embedding，不复用缓存候选或缓存排名；所有重排器显式 disabled，运行当前规则回退。

召回80、重排12、请求top20、原始问题排序；全部99题用当前第一查询变体重新执行，外部API调用0。

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

## 快照对比

- primary30/jieba：对综合报告重放的逐题指标差异=[]；source/page排名差异=[]；查询差异=[]。
- primary30/jieba：对原在线embedding实际快照的逐题指标差异=[]；source/page排名差异=['diag-01']。
- primary30/whitespace：对综合报告重放的逐题指标差异=[]；source/page排名差异=[]；查询差异=[]。
- primary30/whitespace：对原在线embedding实际快照的逐题指标差异=[]；source/page排名差异=[]。
- secondary69/jieba：对综合报告重放的逐题指标差异=[]；source/page排名差异=[]；查询差异=[]。
- secondary69/whitespace：对综合报告重放的逐题指标差异=[]；source/page排名差异=[]；查询差异=[]。

## 溯源与限制

- 真实Chroma查询228次；缓存embedding读取228次；API调用及被阻止请求尝试均为0。
- 原始资料库全部文件内容 SHA-256 和大小在验证前后完全一致；当前实现 hash 验证前后完全一致。
- 语料 SHA-256：`edc77541da196ce90eebd93b20d45b8eb808519e5420b1f8db8a0ec042c53519`；4861条片段，两种BM25索引均完整覆盖。
- 当前文件hash、embedding缓存hash、逐题排名/计分及原始库前后文件清单见同名JSON。
- 真实查询隔离 Chroma、当前 BM25、融合和规则排序；仅 embedding 使用历史缓存，未验证在线 embedding 服务或 gte API。
- 69题已参与配置探索且共享同一语料，不是独立盲测；本验证不做新的调参。
- 只评测当前第一查询变体，未覆盖服务层多变体聚合、不匹配过滤、答案生成和 RAGAS 评分。
- 所有指标均按期望来源覆盖，不证明片段语义正确或临床有效。
- 保持原始实际运行报告及其运行时 hash，不将本次缓存 embedding 的验证冒充新在线运行。
