# 循证检索流程设计文档（Evidence Retrieval Pipeline）

> 本文档描述脑卒中多智能体系统中「临床决策驱动检索」的完整实现。
> 核心目标：让系统从"医学知识问答 RAG"升级为"Clinical Decision Support Agent"——
> 不问"这个病是什么"，而问"医生下一步需要做什么决定，需要什么证据支持"。

---

## 1. 总体架构

检索不是独立的搜索调用，而是嵌入 LangGraph 推理链的**决策驱动证据检索层**：

```
病例输入
   │
   ▼
⑤ research_plan  ★Clinical Decision Planner（决策节点 + PICO + 优先级）
   │
   ▼
⑥ evidence_router ★Evidence Router Agent（证据类型 + 知识类别 + 关键词）
   │
   ▼
⑦ retrieve       循证检索（核心 RAG 层）
   │  ├── Medical Query Translator（临床语言 → 医学检索式）
   │  ├── HybridRetriever（向量 + BM25 + RRF + Rerank）
   │  ├── 类别过滤（category metadata）
   │  ├── Evidence Mismatch Filter（剔除不匹配类别）
   │  └── Retrieval Failure Recovery（0 结果多级恢复）
   │
   ▼
⑧ evidence_judge 证据质量评估（不足则 query_rewrite 回 ⑥，最多 2 轮）
   │
   ▼
⑨ reason 专家推理
```

---

## 2. 前置：Clinical Decision Planner（决策规划）

**文件**：`model/app/agents/orchestrators/nodes/research_node.py`

把"临床问题"转成"临床决策节点"，每个节点携带固定 Schema：

```json
{
  "decision_name": "是否进行静脉溶栓(IV thrombolysis)",
  "decision_type": "treatment",
  "patient_evidence": ["发病90分钟", "CT无出血"],
  "uncertainty": ["血小板计数", "抗凝用药"],
  "required_evidence": ["AHA卒中指南"],
  "evidence_type": "treatment",
  "priority": 10,
  "pico": {
    "population": "急性缺血性卒中发病4.5小时内患者",
    "intervention": "阿替普酶静脉溶栓(alteplase IV thrombolysis)",
    "comparison": "不溶栓(no thrombolysis)",
    "outcome": "功能独立/症状性颅内出血"
  }
}
```

**关键规则**（prompt 中约束）：
- 决策按优先级降序：先再灌注 → LVO 评估 → 血压 → 病因 → 二级预防
- 定位类(anatomy)决策优先级低于治疗类
- 禁止从神经定位直接推导病因（定位证据与病因证据分离）
- 检索任务必须是临床决策问题，不是文献性能问题（如"敏感性与特异性"）

**PICO → 检索式**（`_pico_to_query`）：提取 Intervention + Population + Outcome 核心词
（优先括号内英文标准术语），生成如：
`alteplase IV thrombolysis acute ischemic stroke within 4.5h functional independence`

---

## 3. Evidence Router Agent（证据路由）

**文件**：`model/app/agents/orchestrators/nodes/evidence_router_node.py`

用 LLM 判断每个检索查询的路由策略：

```json
{
  "query": "是否静脉溶栓",
  "evidence_type": "treatment",
  "target_categories": ["指南", "专家共识", "规范"],
  "keywords": ["alteplase", "thrombolysis"]
}
```

- **evidence_type**：treatment / diagnosis / anatomy / etiology / prognosis / prevention
- **target_categories**：治疗/诊断/病因→指南/共识/规范；解剖定位→教材
- **keywords**：附加医学标准检索关键词

LLM 失败时**规则兜底**：按决策节点的 evidence_type → 类别映射
（`EVIDENCE_TYPE_CATEGORIES`）。

**图接线**：`research_plan → evidence_router → retrieve`，
`query_rewrite → evidence_router → retrieve`（router 缺失时直连，向后兼容）。

---

## 4. Medical Query Translator（临床语言 → 医学检索式）

**文件**：`model/app/agents/services/query_translator.py`

核心职责：把"医生语言"转成"医学数据库语言"，生成**多组检索变体**（多路召回）。

### 4.1 Query Abstraction（患者变量抽象）

移除患者特定变量（NIHSS/ASPECTS/GCS/年龄/血压/血小板），保留医学概念：

```
NIHSS18分 ASPECTS10分 房颤 急性缺血性卒中 完全性失语 右侧偏瘫
        ↓
房颤 急性缺血性卒中 完全性失语 右侧偏瘫
```

> 论文不会写 "NIHSS=18"，而写临床概念。

### 4.2 同义词扩展（Medical Synonym Expansion）

40+ 医学术语映射，中英文/缩写/全称：

```python
"mca": ["middle cerebral artery", "mca syndrome", "mca infarction", "mca occlusion", "大脑中动脉"],
"aphasia": ["失语", "language disorder", "speech disturbance", "言语障碍"],
"thrombolysis": ["alteplase", "rt-pa", "tissue plasminogen activator", "静脉溶栓", "阿替普酶"],
```

### 4.3 OR-AND 医学检索范式

抽取医学概念，组合为概念 OR 组 + AND 连接：

```
("mca" OR "middle cerebral artery" OR "mca syndrome") AND
("aphasia" OR "失语" OR "language disorder") AND
("hemiparesis" OR "hemiplegia" OR "偏瘫")
```

- 同义词**跨概念去重**（mca 只出现一次，避免交叉重复）

### 4.4 Source Constraint（证据源约束）

按证据类型附加来源约束词，避免撞上二级预防等无关内容：

| 证据类型 | 附加约束 |
|---|---|
| anatomy | `AND ("neurology textbook" OR "neuroanatomy")` |
| treatment | `AND ("recommendation" OR "meta-analysis")` |
| etiology | `AND ("TOAST" OR "diagnostic criteria")` |

### 4.5 变体生成

`translate_query(query, evidence_type)` 返回多组变体（按优先级）：
1. 抽象后查询 + 证据关键词 + Source Constraint
2. OR-AND 组合式（医学检索范式）
3. 原始查询 + 证据关键词
4. 同义词替换变体

### 4.6 Clinical Query Planner（PICO + search_query）

决策节点升级为完整 Clinical Query Planner：

```json
{
  "decision_id": "AIS_IVT_001",
  "decision_name": "是否进行静脉溶栓",
  "evidence_type": "treatment",
  "evidence_source": ["AHA guideline", "ESO guideline", "RCT"],
  "pico": {
    "population": "急性缺血性卒中发病4.5小时内患者",
    "intervention": "阿替普酶静脉溶栓(alteplase IV thrombolysis)",
    "comparison": "不溶栓(no thrombolysis)",
    "outcome": "功能独立/症状性颅内出血"
  },
  "search_query": [
    "acute ischemic stroke intravenous alteplase within 4.5 hours guideline",
    "AHA ASA guideline alteplase recommendation"
  ]
}
```

- `search_query`：1-2 条可直接检索的英文专业查询（含疾病实体+干预+时间窗/人群）
- 检索任务优先取 search_query，回退用 PICO 拼检索式

### 4.7 Medical Evidence Reranker（医学评分重排）

BGEReranker 在语义 rerank 基础上融合医学评分：

```
Final Score = 0.35 语义相似度
            + 0.25 证据类型匹配
            + 0.20 指南权威（authority）
            + 0.10 时效性（year）
            + 0.10 人群/主题匹配（subtopic）
            + 淘汰惩罚（决策类型不匹配的 subtopic -0.3）
```

**实测**：溶栓指南 0.81 > 血脂指南 0.3883（血脂被显著降权）。`evidence_type` 全链路透传。

---

## 5. HybridRetriever（混合检索）

**文件**：`model/app/rag/retrievers.py`

三路混合检索 + 融合 + 重排：

```
query
  ├── 向量检索（Chroma + DashScope text-embedding-v2, dim 1536）
  ├── BM25 关键词检索（精确医学术语命中）
  │
  └── RRF 融合（Reciprocal Rank Fusion, k=60）
        │
        ▼
     候选 top-k×4
        │
        ▼
     BGE Rerank（gte-rerank, 重排 top-k）
```

**类别过滤**（`category_filter`）：向量 + BM25 双路按 category metadata 过滤，
支持允许列表（`["指南"]`）与排除列表（`["!教材"]`）。

---

## 6. Evidence Mismatch Filter（证据类型一致性过滤）

**文件**：`model/app/agents/services/retrieval_service.py` → `_filter_mismatched`

检索后按 evidence_type 剔除不匹配类别：

- anatomy（定位）查询召回血脂/他汀指南 → **立即丢弃，不送 LLM**
- treatment（溶栓）→ 丢弃教材
- 全部不匹配时保留前 2 条供评估（避免 0 结果），并记录 mismatch 日志

---

## 7. Retrieval Failure Recovery（0 结果多级恢复）

`_recover_retrieval`：0 结果时逐级尝试：

1. **去掉类别过滤**回退（Evidence Router 过严时）
2. **同义词 OR 扩展**检索
3. **核心概念子集**降低限定（取前 2 个概念）

---

## 8. Evidence Grader + 查询重写循环

**文件**：`model/app/agents/orchestrators/nodes/evidence_node.py`

### 8.1 EvidenceJudgeNode（证据质量评估）

输入：临床决策 + 检索证据；输出：

```json
{
  "quality": 0.0,
  "is_sufficient": false,
  "missing_information": [],
  "assessment": "...",
  "evidence_mismatch": false
}
```

- 决策的所需证据类型注入审查 prompt
- `evidence_mismatch=true`（如需要指南却召回教材）→ 触发带路由过滤的重检
- 质量 < 阈值或 mismatch → `need_retrieve=true`（最多 2 轮）

### 8.2 QueryRewriteNode（查询重写）

证据不足时生成下一轮更精确且不重复的查询，注入决策证据类型并提示
包含"指南/guideline"字样确保召回正确证据源。

---

## 9. 知识库结构

**向量库**：单 Chroma collection（`langchain`），5806 条
（5278 原文 chunk + 528 QA 对）。

**chunk 元数据**（`category` 分类）：

| 类别 | 来源 | 分块方式 | 用途 |
|---|---|---|---|
| 指南 | 12 篇中文卒中指南/共识/规范 | 固定窗口 512/128 | 治疗/诊断/病因查询 |
| 教材 | Neuroanatomy（1054 页） | 语义分块（粗切 800 + 边界微调） | 解剖定位查询 |
| 其他 | 英文指南等 | 固定分块 | 兜底 |

- 语义分块结果**缓存到磁盘**（`model_cache/semantic_chunks`），启动 264s → 72s
- 分类规则：`data_loader.py` 的 `CATEGORY_RULES` 按文件名关键词归入
  指南/专家共识/规范/教材/其他

**Evidence Metadata 增强**（`data_loader.enrich_metadata`）：
每个 chunk 自动生成结构化标签（从文件名+内容关键词）：

| 字段 | 示例 | 说明 |
|---|---|---|
| `evidence_type` | guideline/textbook/consensus | 由 category 映射 |
| `subtopic` | `['thrombolysis']` / `['lipid_management','secondary_prevention']` | 12 类内容关键词命中 |
| `phase` | acute / secondary / general | 临床阶段 |
| `year` | 2023 / 2024 | 文件名提取 |
| `authority` | 5(指南)/4(共识)/3(教材) | 来源权威评分 |

**12 类 subtopic**：thrombolysis / thrombectomy / blood_pressure / antiplatelet /
anticoagulation / lipid_management / secondary_prevention / toast_classification /
lvo_assessment / imaging / nihss_assessment / stroke_identification

检索时 `EXCLUDED_SUBTOPIC_BY_TYPE` 按决策类型淘汰不匹配主题
（treatment 查询淘汰 lipid_management/secondary_prevention）。

---

## 10. 完整检索示例

**病例**：69 岁男性，房颤，NIHSS 18，右侧偏瘫+失语，发病 90 分钟，CT 无出血。

| 步骤 | 输出 |
|---|---|
| Decision Planner | `[10] 是否静脉溶栓(treatment)`、`[9] 是否CTA评估LVO(treatment)`、`[7] 心源性栓塞病因(etiology)` |
| PICO | `alteplase IV thrombolysis acute ischemic stroke within 4.5h functional independence` |
| Evidence Router | treatment → 指南/共识 + alteplase/thrombolysis 关键词 |
| Query Translator | 变体1: 抽象后查询+guideline+Source Constraint；变体2: OR-AND 概念组合 |
| HybridRetriever | 召回 3 条：中国急性缺血性卒中诊治指南2023（类别:指南） |
| Mismatch Filter | 保留指南类，丢弃教材/血脂内容 |
| Evidence Grader | 评估质量与缺口，必要时重写查询再检 |

---

## 11. 关键文件索引

| 文件 | 职责 |
|---|---|
| `app/agents/orchestrators/nodes/research_node.py` | Clinical Decision Planner + PICO |
| `app/agents/orchestrators/nodes/evidence_router_node.py` | Evidence Router Agent |
| `app/agents/services/query_translator.py` | Medical Query Translator |
| `app/agents/services/retrieval_service.py` | 检索服务 + Mismatch Filter + Recovery |
| `app/rag/retrievers.py` | HybridRetriever / UnifiedSearchEngine / embeddings |
| `app/rag/data_loader.py` | 文档加载、分类、分块（固定 + 语义） |
| `app/agents/orchestrators/nodes/evidence_node.py` | EvidenceJudge + QueryRewrite |
| `app/agents/orchestrators/nodes/retrieve_node.py` | 检索节点（决策 → 检索接线） |

---

## 12. 设计原则与边界

- **决策驱动**：检索由临床决策节点驱动，而非泛化疾病知识
- **证据约束**：问题类型 → 证据类型 → 检索源（类别/关键词/Source Constraint）
- **医学检索范式**：OR-AND 概念组合 + 同义词扩展 + 患者变量抽象
- **质量门控**：Mismatch Filter 检索后即过滤；Grader 评估不足触发重检
- **安全兜底**：0 结果多级恢复；全不匹配保留少量供评估；检索失败不阻塞推理

> ⚠️ 医疗安全：检索到的证据为决策辅助，最终诊疗建议须由医生结合
> 完整病史、影像与实验室检查综合判断。
