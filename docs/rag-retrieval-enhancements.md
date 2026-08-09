# RAG 检索（Retrieve）提升方法总结

> 本文档系统总结本项目在医疗 RAG 检索链路中采用的全部提升方法，
> 覆盖"数据组织 → 查询构造 → 召回 → 重排 → 评估"全链路。
> 对应代码均已在 `model/` 落地，评估基线见 `model/evaluation/`。

---

## 一、问题背景：检索链路的数据质量瓶颈

RAGAS 初测（5 题）暴露的检索短板：

| 指标 | 初测值 | 含义 |
|---|---|---|
| context_precision | 0.37 | 检索到的上下文大量无关 |
| context_recall | 0.43 | 关键知识经常没召回 |
| faithfulness | 0.46 | 答案不忠实于上下文 |

**核心结论**：不是生成模型差，而是"临床决策 → 证据空间"的映射没有真正进入 retrieve。
问题链：**数据污染 → Metadata 错误 → Collection 路由错误 → Retriever 召回错误**。

发现的隐藏问题：

1. **collection 是静态桶，metadata 是动态标签** —— 入库时按页面级标签分桶，后续标签更新后桶不迁移，导致"TOAST 详情 chunk 躺在 treatment/prevention collection，etiology 查询召不到"。
2. **评估链路绕过真实 query transformation** —— 评测用原始 query 直连 retrieve，而线上经过 rewrite/router，两者不是一个系统（评测虚高）。
3. **页面级关键词提取的标签误标传播** —— 整页含 "TOAST" → 该页所有 chunk 都标 toast_classification（如高压氧内容 chunk 被标病因标签）。
4. **PICO 英文化压制中文召回** —— 纯英文 OR 组使 embedding 系统性偏向英文文档。
5. **BM25 不解析布尔语法** —— PICO 式（引号/括号/AND/OR）对 embedding 有效但 BM25 检索退化。

---

## 二、方法总览（按实施顺序）

| # | 方法 | 解决的问题 | 关键代码 |
|---|---|---|---|
| 1 | Multi-Collection 主题隔离 | 单库 embedding 空间混乱、无关内容进入检索 | `retrievers.py` `route_collection` / `EVIDENCE_TYPE_COLLECTIONS` |
| 2 | 医学重排失败回退 | Rerank API 失败退化为纯 embedding 排序 | `retrievers.py` `_fallback_medical_rank` |
| 3 | Chunk 级元数据（规则） | 页面级误标传播 | `data_loader.py` `_recompute_chunk_metadata` |
| 4 | 垃圾 chunk 过滤 | 参考文献页/版权页/目录页/过短碎片污染召回 | `data_loader.py` `is_reference_chunk` |
| 5 | 存量库重分桶 | 静态桶与动态标签脱节 | `scripts/enrich_metadata.py` |
| 6 | Medical Evidence Score 9 项加权 | 排序只看 embedding 相似度 | `retrievers.py` `_apply_medical_score` |
| 7 | BM25 词袋清洗 | PICO 布尔式使 BM25 退化 | `retrievers.py` `_clean_bm25_query` |
| 8 | Query Translator：PICO + 双语 + 中文优先 | 查询构造不贴近临床决策、英文压制中文 | `query_translator.py` `build_pico_query` |
| 9 | LLM 语义分类器 | 规则无法区分的难例（高压氧 vs 影像） | `scripts/enrich_llm.py` |
| 10 | 评估固化：30 题 benchmark + 检索指标 | 小样本噪声、无回归基线 | `scripts/eval_ragas.py` + `evaluation/` |

---

## 三、方法详解

### 1. Multi-Collection 主题隔离

**问题**：单一 collection（`langchain`）混合解剖教材/指南/RCT/病例，embedding 空间混乱；
"血脂指南"类无关内容会进入解剖/溶栓检索。

**方案**：按主题拆分为 5 个物理隔离 collection：

```
Chroma
├── anatomy_collection     解剖教材（category=教材）
├── guideline_collection   无明确主题的指南/共识/规范内容
├── etiology_collection    病因（TOAST/影像/LVO）
├── treatment_collection   急性期治疗（溶栓/取栓/血压）
└── prevention_collection  二级预防（抗凝/抗血小板/血脂）
```

**归属规则**（`route_collection`，优先级从高到低）：
教材 → anatomy；LLM 语义 `domain`（如有）→ 对应 collection；
治疗 subtopic → treatment；病因 subtopic → etiology；预防 subtopic → prevention；其余 → guideline。

**检索路由**（`EVIDENCE_TYPE_COLLECTIONS`）：Decision Planner 的 `evidence_type` 决定检索哪些 collection：

```python
"treatment"  → ["treatment"]
"anatomy"    → ["anatomy"]
"etiology"   → ["etiology"]
"prevention" → ["prevention"]
"diagnosis"  → ["guideline", "etiology"]
"prognosis"  → ["guideline", "prevention"]
```

**迁移**：`scripts/migrate_multi_collection.py` 从旧库 `get` 出已算好的 embedding 原样分发写入
5 个 collection —— **零额外 API 成本**，幂等可重跑，旧库保留。

**效果**：anatomy 路由检索 100% 命中教材，物理隔离生效。

---

### 2. 医学重排失败回退（不退化）

**问题**：`gte-rerank` API 失败（AccessDenied/限流）时直接返回原始 RRF 顺序，
`Medical Evidence Score` 完全不执行 —— 排序停留在纯 embedding 相似度（2019 旧指南排在 2023 指南前面）。

**方案**（`BGEReranker`）：
- 三条失败路径（未启用 / API 非 OK / 异常）统一走 `_fallback_medical_rank`：
  1. 把 RRF score 归一化为 0-1 的 `relevance_score`（`_normalize_rrf_to_relevance`）
  2. 执行 `_apply_medical_score` 规则加权排序
- 限流（`Throttling.RateQuota`）增加 1s 退避重试一次。

**效果**：即使 Rerank API 完全不可用，排序也不退化为纯 embedding 相似度。

---

### 3. Chunk 级元数据（Chunk-level Enrichment）

**问题**：页面级关键词提取 → 整页标签被所有 chunk 继承：
```
页面: [TOAST分类][高压氧治疗][传统医学]  → 页面标签 toast_classification
                                              ↓
                          所有 chunk 都标 toast（误标传播）
```

**方案**（`data_loader.py`）：分块后用 **chunk 文本**重算内容级标签，替换页面级继承：

```python
def _recompute_chunk_metadata(chunk):
    """用 chunk 文本重算 subtopic/decision_node/intervention/
    time_window/evidence_level/phase; 保留 source/page/category 结构字段。"""
```

**效果**：TOAST 误标 chunk（高压氧内容）重算后 subtopic 变为空/imaging，不再因 toast 标签获得病因匹配加分。

---

### 4. 垃圾 chunk 过滤

**问题**：MCA 解剖检索命中教材"参考文献页"（通篇作者引用，无临床价值）。

**方案**（`data_loader.py` `is_reference_chunk`）：
- **强特征组合计数**（参考文献页专属，正文几乎不出现）：
  - `et al.` / `etal.`（clean 后无空格形态）
  - 连续 ≥3 作者名列表（`ZhuL,ZengJ,LiaoS,`）
  - 期刊年份页码（`Brain.1962Dec;85:741`）
- 判定：总强特征 ≥3 **且** 年份页码标记 ≥2（避免英文正文零星 `et al.` 误删）
- **弱特征兜底**：`[数字]`/`(年份)`/`Vol.`/`doi`/`PMID` 引用密度
- 过短碎片：`<100` 字符剔除

**效果**：anatomy 删除 934 条垃圾 chunk（参考文献/版权页/目录页），无正文误伤（抽查确认）。

---

### 5. 存量库重分桶（静态桶 × 动态标签协调）

**问题**：collection 归属是入库时按页面级标签定的（静态），chunk 级标签重算后
（动态）两者脱节 —— TOAST 详情 chunk 在 treatment/prevention collection，
而 `etiology` 查询只查 etiology_collection，**召回失败**。

**方案**（`scripts/enrich_metadata.py`）：
- 对每个 chunk：重算 chunk 级标签 → `route_collection` 判定新归属
- 新归属 ≠ 当前 collection → **移动**（旧桶 delete + 新桶 add，**带原 embedding**，零 API 成本）
- 更新标签、删除垃圾、QA 对跳过、失败回撤（add 失败不删源桶）

**效果**：672+103 条跨桶归位，TOAST 详情进入 etiology_collection 并可被召回。

---

### 6. Medical Evidence Score（9 项医学加权）

**问题**：RRF 排序只有语义/关键词信号，没有医学信号（证据等级/权威/时效/主题/干预）。

**方案**（`_apply_medical_score`）：

```
Final Score = 0.20 语义相似度
            + 0.15 证据类型匹配(guideline/consensus/RCT ↔ evidence_type)
            + 0.10 指南权威(authority 3-5)
            + 0.10 证据等级(A/B/C)
            + 0.10 时效性(年份, 2015 为基准)
            + 0.10 主题(subtopic)匹配
            + 0.10 决策节点(decision_node)匹配
            + 0.10 干预(intervention)匹配(含别名: rt-pa → alteplase)
            + 0.05 时间窗(time_window)匹配(数字边界防"13小时"误中"3小时")
            − 0.30 淘汰惩罚(仅当全部 subtopic 均不匹配时)
```

**关键修复**：
- 淘汰惩罚 `any → all`：`thrombolysis,lipid_management` 混合主题 chunk 不误杀
- `intervention` 别名匹配：查询 `rt-pa` 命中 `intervention=alteplase`
- `clinical_intent` 匹配：LLM 标签与 evidence_type 期望意图一致 +0.10 / 不一致 -0.10（`general` 不惩罚）

**效果**：treatment 检索 top3 全部为 `intervention=alteplase` 的证据（修复前首条无关）。

---

### 7. BM25 词袋清洗

**问题**：PICO 式（`("mca" OR "middle cerebral artery")`）对 embedding 有效，
但 BM25 把引号/括号当字面 token，召回退化。

**方案**（`_clean_bm25_query`）：BM25 检索前清洗为词袋：
- 去掉引号/括号
- 仅剥离**前后有空白的** AND/OR/NOT（不误删医学缩写 `OR=1.5` 比值比）

```python
'("mca" OR "middle cerebral artery") localization' → 'mca middle cerebral artery localization'
```

---

### 8. Query Translator：PICO + 双语 + 中文优先

**问题**：translator 只有概念 OR-AND 组合；PICO 式纯英文使 embedding/BM25
系统性偏向英文文档（top20 里英文 2019 指南占 7 条、中国 2023 指南 0 条）。

**方案**（`query_translator.py`）：
- **PICO 结构化**：`(P 人群) AND (I 干预) AND (时间窗) AND (clinical_question)`
  ```
  "NIHSS18 房颤卒中 3小时 是否溶栓"
  → ("急性缺血性卒中" OR "ischemic stroke" OR "房颤" OR "atrial fibrillation" ...)
    AND ("静脉溶栓" OR "thrombolysis" OR "alteplase" ...)
    AND ("3小时" OR "3h") AND ("eligibility")
  ```
- **中英双语保留**（`_core_terms`：term + 首个中文同义词 + 首个英文同义词，排除 term 自身）
- **中文查询变体排序**：中文 query → 原始中文 enriched 优先，PICO 后置；
  英文 query → PICO 优先
- `SYNONYM_MAP` 补口语词（`溶栓`/`卒中`），修复"是否溶栓"抽不到干预概念

**效果**：treatment 7 题中 5 题 recall 从 0 → 1.0；MRR 0.58 → 0.76。

---

### 9. LLM Chunk Semantic Enrichment

**问题**：规则无法区分"高压氧 chunk 标 imaging 但内容属于治疗"类难例。

**方案**（`scripts/enrich_llm.py`）三层分类，**不全量 LLM 标**：

```
Layer 1  规则高置信: 命中 ≥2 个不同关键词 → 跳过 LLM
Layer 2  LLM 分类:   无命中/仅单关键词弱命中 → qwen-plus 输出
         {domain, subtopic, clinical_intent, medical_entity,
          question_type, condition, confidence}
Layer 3  人工抽检:   confidence<0.6 样本写入 evaluation/llm_review_samples.json
```

- 已执行：1433 条（全部成功），110 条低置信样本供抽检
- `route_collection` 接入 `DOMAIN_TO_COLLECTION`：LLM `domain=treatment` 的高压氧 chunk 归位 treatment_collection
- `medical score` 用 `clinical_intent` 匹配（见方法 6）
- 使用链路：存量库 `enrich_llm → enrich_metadata`；重建后需重跑 enrich_llm

---

### 10. 评估固化：30 题 benchmark + 检索指标

**问题**：5 题小样本 + qwen-plus 评分噪声大，无法判断改进是否真实。

**方案**：
- `evaluation/stroke_ragas.json`：30 题（解剖 5 / 病因 5 / 治疗 10 / 预防 5 / 诊断 5），
  每题含 `expected_source`（期望来源文档）与 `ground_truth`
- `scripts/eval_ragas.py`：
  - **检索指标**（按期望来源对齐，无需 LLM）：`Recall@K` / `MRR` / `NDCG@10`
    （按来源去重，空来源不误判）
  - **RAGAS 生成指标**：faithfulness / answer_relevancy / context_precision / context_recall / answer_correctness
  - 走真实链路：`translate_query` → `route_collections` → 检索 → 生成
  - 自动生成 `evaluation/regression_report.md`

**基准结果（2026-08-08）**：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| Recall@3 | 0.683 | **0.783** |
| Recall@10 | 0.683 | **0.817** |
| MRR | 0.581 | **0.757** |
| NDCG@10 | 0.597 | **0.763** |

---

## 四、检索架构演进

```
修复前（问题阶段）                         修复后（当前）
─────────────────────────              ─────────────────────────
Question                                Question
  ↓                                        ↓
Translator(概念OR-AND, 无PICO)           Clinical Query Planner
  ↓                                        ↓
单 Chroma collection (langchain)          Router (evidence_type)
  ↓                                        ↓
Embedding + BM25                          Multi-Collection (5 主题隔离)
  ↓                                        ↓
RRF                                       Hybrid Retrieval (双语 PICO)
  ↓                                        ↓
gte-rerank (失败→原始顺序)                Metadata Filter (chunk 级标签)
  ↓                                        ↓
Qwen                                      BGE Reranker + Medical Score(9项)
                                           ↓
                                           LLM
```

## 五、评估链路（修正的隐藏 bug）

评测必须走**真实检索链路**，与线上一致：

```
eval question → translate_query(变体) → route_collections → UnifiedSearchEngine
    → top20 → Recall@K/MRR/NDCG(期望来源对齐)
    → top3 contexts → qwen-plus 生成答案 → RAGAS 指标
```

否则（直接 raw query 直连 retrieve）评测与线上是两套系统，结果虚高。

---

## 六、剩余短板与下一步

| 短板 | 说明 | 建议 |
|---|---|---|
| 检索排序 | TOAST 内容进 top5 但排第 5（召回成功、排序不足） | 引入本地 BGE-reranker 或修复 gte-rerank API 权限 |
| collection 边缘 case | tx-03/08、prev-01/04（跨主题 chunk 归属） | 检索时对"多主题"查询扩大 collection 集 |
| RAGAS 噪声 | 生成指标受小样本+LLM 评分波动 | benchmark 扩到 50+ 题、多次运行取均值 |
| LLM 标注重建 | 重建向量库后需重跑 enrich_llm | 在 build 流程中集成 LLM enrichment 步骤 |

---

*相关文档：`docs/retrieval-pipeline-design.md`（检索流程设计）、`model/evaluation/regression_report.md`（回归报告）、`model/evaluation/stroke_ragas.json`（benchmark 数据）*
