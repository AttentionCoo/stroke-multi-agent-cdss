# 模型层技术文档（Model Layer Technical Documentation）

> 版本对应：main 分支（2026-08）· 配套阅读：[全链路流式重构策略.md](全链路流式重构策略.md) · [Agentic-RAG与协作式多智能体架构.md](Agentic-RAG与协作式多智能体架构.md) · [tool-calling-design.md](tool-calling-design.md) · [retrieval-pipeline-design.md](retrieval-pipeline-design.md)

本文档覆盖 **`model/` 目录（Python FastAPI + LangGraph 模型推理服务）** 的全部核心技术，说明每一项技术是什么、为什么存在、以及它们如何共同构成整个模型层。所有代码路径、配置、事件契约均与当前 main 分支实现一致。

---

## 目录

1. [定位与架构总览](#1-定位与架构总览)
2. [技术栈清单](#2-技术栈清单)
3. [服务入口与生命周期](#3-服务入口与生命周期)
4. [多模型路由（ModelRouter）](#4-多模型路由modelrouter)
5. [LangGraph 推理图编排（核心）](#5-langgraph-推理图编排核心)
6. [流式输出管道与 SSE 事件契约](#6-流式输出管道与-sse-事件契约)
7. [思考链事件翻译（StreamEventTranslator）](#7-思考链事件翻译streameventtranslator)
8. [Agentic RAG 检索](#8-agentic-rag-检索)
9. [医疗工具调用（Tool Calling）](#9-医疗工具调用tool-calling)
10. [结构化输出（Structured Outputs）](#10-结构化输出structured-outputs)
11. [检查点持久化与 HITL 医生复核](#11-检查点持久化与-hitl-医生复核)
12. [多专家会诊（reason / debate / consensus）](#12-多专家会诊reason--debate--consensus)
13. [安全校验与合规审计](#13-安全校验与合规审计)
14. [提问提取与按问题直答](#14-提问提取与按问题直答)
15. [安全、并发与错误契约](#15-安全并发与错误契约)
16. [LLM 用量跟踪与成本估算](#16-llm-用量跟踪与成本估算)
17. [评测闭环](#17-评测闭环)
18. [配置体系](#18-配置体系)
19. [目录结构](#19-目录结构)
20. [端到端链路示例](#20-端到端链路示例)

---

## 1. 定位与架构总览

模型层是一个**无状态 HTTP 推理服务**（FastAPI），对外暴露 `/model/*`、`/ai/*`、`/admin/*` 三类接口，由 Java 后端通过 SSE 长连接转发调用。

```text
前端(Vue3) ←SSE→ Java(Spring WebFlux) ←HTTP/JWT→ 模型层(FastAPI) ←HTTPS→ DashScope(qwen)
                                                          │
                                                          ├─ ChromaDB 本地向量库(5 collection)
                                                          ├─ BM25 内存倒排索引
                                                          ├─ Sqlite 检查点(思考链/HITL)
                                                          └─ MySQL/Redis 由后端负责(模型层不直连)
```

模型层内部按"**请求入口 → 编排图 → 检索/工具/会诊/校验 → 流式事件**"组织：

```text
app/main.py        薄入口: FastAPI 组装 + 路由注册 + /health
app/bootstrap.py    资源初始化(lifespan) + init_all_resources
app/runtime.py      运行时状态容器(resources/_KbJobs) + JWT 鉴权
app/api/*.py        路由: /model 推理流·KB·工具·info | /ai 分析 | /admin 配置热更新
app/agents/         LangGraph 图、节点、工具、流事件翻译、提问提取
app/rag/            检索: embeddings / reranker / retrievers / data_loader / qa_generator
app/config/         配置加载器 + YAML(模型路由/提示词/专家/规则/报告模板/参数限制)
app/utils/          安全脱敏、并发闸、错误码、用量跟踪、命名、上下文摘要
app/evaluation/     离线规则评测 + RAGAS 基线门禁
```

**设计原则**：这是一个"**编排为主的工作流 + 局部 Agent 能力**"的系统——推理图是确定性的，模型只能在图给定的边内做选择；真正自主的部分是工具调用循环与 Agentic RAG 检索闭环。医疗场景用"受控"换取可审计与可追责。

---

## 2. 技术栈清单

| 类别 | 技术 | 版本 | 用途 |
|---|---|---|---|
| Web 框架 | FastAPI / Starlette / Uvicorn | 0.141.1 / 1.6.0 / 0.52.3 | REST + SSE 流式接口 |
| SSE | sse-starlette | 3.4.8 | EventSourceResponse + 心跳 |
| 编排 | LangGraph | 1.2.11 | 确定性状态图推理 |
| LangChain | langchain / langchain-core | 1.3.15 / 1.5.4 | LLM 调用、工具、回调 |
| LLM 接入 | langchain-openai | 1.5.0 | DashScope OpenAI 兼容模式 |
| 向量库 | chromadb / langchain-chroma | 1.5.9 / 1.1.0 | 5 collection 语义检索 |
| 关键词检索 | rank-bm25 | 0.2.2 | 医学术语精准召回 |
| 重排 | dashscope (gte-rerank API) | 1.26.7 | 语义重排 + 医学加权 |
| 结构化输出 | Pydantic | 2.13.4 | Schema 约束 LLM 输出 |
| 检查点 | langgraph-checkpoint-sqlite / aiosqlite | 3.1.1 / 0.21.0 | 断点续跑 + HITL |
| 文档解析 | pypdf | 6.16.0 | PDF 指南加载 |
| 配置 | PyYAML / pydantic-settings | 6.0.3 / 2.15.0 | YAML 配置中心 |
| 评测 | ragas（本地脚本，不进 requirements） | 0.2.x | 检索/生成指标 |

模型（2026-08 起全部推理角色统一为 qwen-turbo）：`main/fast/turbo/consensus = qwen-turbo`；影像识别保持 `qwen-vl-plus`（多模态）。

---

## 3. 服务入口与生命周期

### 3.1 薄入口 `app/main.py`

main.py 只做四件事：建 FastAPI 实例、注册 CORS、挂载三个路由、定义 `/health`。

```python
app = FastAPI(lifespan=lifespan)
app.include_router(model_router)   # /model/*
app.include_router(ai_router)      # /ai/*
app.include_router(admin_router)   # /admin/*
```

**例子——`/health` 的就绪门禁**（这是整栈重启后"AI 服务暂时不可用"问题的关键修复）：

```python
@app.get("/health")
async def health_check():
    ready = resources.get("model") is not None
    return JSONResponse(
        status_code=200 if ready else 503,   # 未就绪返回 503
        content={"status": "ready" if ready else "starting", "model_loaded": ready},
    )
```

模型冷启动约 90 秒（加载检索库、构建智能体）。`/health` 未就绪时返回 **503**，使 docker healthcheck 与 `depends_on: service_healthy` 真正等待就绪，后端不会在模型没起来时转发请求。

### 3.2 资源初始化 `app/bootstrap.py`

`init_all_resources(checkpointer=None)` 按 7 步初始化并写入全局 `resources` 容器：

1. 配置管理器（Prompt/报告/专家/校验/参数限制）
2. **LLM**：`ModelRouter` 按角色建 4 个实例（main/fast/turbo/consensus）+ 用量回调
3. 上下文摘要服务（qwen-turbo）
4. **检索引擎** `UnifiedSearchEngine`（加载 5 collection + BM25）
5. 医疗助手 `MedicalAssistant`
6. **智能体** `QwenAgent`（构建 LangGraph 图）
7. 附属服务（影像识别、命名模型）

`lifespan` 在**应用主事件循环**内先 `await open_checkpointer()` 创建 Sqlite 检查点（aiosqlite 连接绑定事件循环），再在线程池里跑 `init_all_resources`：

```python
checkpointer = await open_checkpointer()
agent, naming, ... = await loop.run_in_executor(resources["executor"], init_all_resources, checkpointer)
```

---

## 4. 多模型路由（ModelRouter）

### 4.1 为什么需要

业务代码不能硬编码模型名——要能"不改代码只改配置"切换模型、按角色分配不同模型。`ModelRouter` 从 `model/app/config/models.yaml` 按角色解析并缓存 LLM 实例。

### 4.2 配置 `models.yaml`

```yaml
provider_defaults:
  dashscope:
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: DASHSCOPE_API_KEY
    request_timeout: 120      # 阶段5: 单请求超时(秒)
    max_retries: 3            # 阶段5: 429/5xx 自动重试

roles:
  main:      { model: qwen-turbo, provider: dashscope, env_override: MODEL_MAIN }
  fast:      { model: qwen-turbo, provider: dashscope, env_override: MODEL_FAST }
  turbo:     { model: qwen-turbo, provider: dashscope, env_override: MODEL_TURBO }
  consensus: { model: qwen-turbo, provider: dashscope, env_override: MODEL_CONSENSUS }
```

### 4.3 解析优先级与环境变量覆盖

`resolve_model(role)` 的优先级：**环境变量 > yaml model > 内置默认**；旧变量 `CONSENSUS_MODEL` 兼容：

```python
env_names = [cfg.get("env_override", ""), _LEGACY_ENV_OVERRIDES.get(role, "")]
for env_name in [n for n in env_names if n]:
    env_val = os.getenv(env_name, "").strip()
    if env_val:
        return env_val
```

**例子**：部署时设 `MODEL_MAIN=qwen-max`，不重建镜像即可让主推理改用更强模型；其余角色仍为 turbo。

### 4.4 关键细节（都是踩坑后的修复）

- **`stream_usage=True` 显式开启**：DashScope 自定义 base_url 下 langchain 默认不开流式用量，不开启则流式回答统计不到 token；
- **`request_timeout` / `max_retries`**：provider 级默认、role 级可覆盖，429/5xx 自动退避重试；
- **实例缓存**：同角色复用同一 ChatOpenAI（连接池复用）。

---

## 5. LangGraph 推理图编排（核心）

### 5.1 图结构

`app/agents/orchestrators/clinical_graph.py` 用 `StateGraph(ClinicalState)` 构建整条推理链：

```text
intent ──┬─ irrelevant → reject ────────────────► END
         ├─ knowledge → knowledge_answer ────────► END
         └─ consultation → memory → analysis → tool_use
              → research_plan → evidence_router → retrieve
              → evidence_judge ──不足──► query_rewrite → evidence_router(再检索, 有界)
              → reason → debate → consensus_agent
              → validate ──未过(反思, ≤3次)──► reason(回环)
              → compliance(合规审计) → human_review(HITL, 可选)
              → generate_report ──► END
```

**状态**：`ClinicalState`（`app/agents/core/schema.py`）是一个 TypedDict，含病例文本、上下文、检索任务/查询、证据、专家意见、校验状态、合规审计、HITL 复核字段等 40+ 字段。LangGraph 把每个字段当作一个 channel，节点返回的 dict 合并进状态。

### 5.2 条件路由（模型能"选"的地方）

```python
graph.add_conditional_edges(
    "evidence_judge", self._route_evidence,
    {"rewrite": "query_rewrite", "reason": "reason"},
)

def _route_evidence(self, state):
    return "rewrite" if state.get("need_retrieve") else "reason"
```

模型在证据评估后"决定"证据是否充分、要不要改写重查；但**流程本身是代码定的**，这正是"受控编排"。

### 5.3 反思循环（有界）

`validate` 校验失败且 `reflection_count < max_reflection_count` → 路由回 `reason` 重新会诊（携带 `validation_feedback` 供反思），最多 3 次，之后"强制输出 + 安全警告"：

```python
if state['validation_passed']:
    return "pass"
if state['reflection_count'] < self.max_reflection_count:
    return "retry"
return "fail"
```

---

## 6. 流式输出管道与 SSE 事件契约

### 6.1 三流模式（LangGraph 1.x）

LangGraph 1.x 移除了 `astream_events`，改用 `astream(stream_mode=["updates", "messages", "custom"])`：

| stream_mode | 产出 | 用途 |
|---|---|---|
| `updates` | 节点完成 `{node: output}` | node_start / node_done |
| `messages` | `(message_chunk, metadata)` | 报告打字机 token |
| `custom` | 节点内 `stream_writer` 写入的增量 | 思考链实时快照 node_token |

节点内通过 `astream_text()`（`nodes/base.py`）把 LLM 增量实时写入 custom 流：

```python
async def astream_text(llm, messages, label, expert=None):
    writer = get_stream_writer()
    async for chunk in llm.astream(messages):
        writer({"node": label, "chunk": str(c), "expert": expert})
```

### 6.2 SSE 事件契约（前端/Java 依赖，勿改语义）

| 事件 | 关键字段 | 说明 |
|---|---|---|
| `node_start` | node/label/status=running | 节点开始 |
| `node_token` | node/content/status=running | 实时快照（增量替换显示） |
| `node_done` | node/summary/content/status=done | 节点完成（content 为全文） |
| `token` | content | 报告/知识回答流式增量 |
| `node_stats` | node/stats | 检索质量看板（retrieve/evidence_judge） |
| `ask_doctor` | questions/message | 会诊结束的信息缺口追问 |
| `human_review` | thread_id/payload | HITL 挂起（`/model/resume` 续跑） |
| `done` | name/all_info/usage | 完成，含 LLM 用量 |
| `error` | error.code/message/retryable | 结构化错误（脱敏） |

**例子（done 事件的 usage，经历完整修复链路后）**：

```json
{"type":"done","request_id":"ab12","name":"溶栓评估",
 "all_info":"...","usage":{"calls":3,"input_tokens":1248,"output_tokens":172,
 "by_model":{"qwen-turbo":{"calls":3,"input_tokens":1248,"output_tokens":172,"cost":0.0005}},
 "cost":0.0005,"seconds":8.2}}
```

### 6.3 HITL 挂起事件

当 `human_review=true` 且医生复核节点触发 `interrupt()` 时，updates 流出现 `__interrupt__`，被翻译为：

```json
{"type":"human_review","status":"pending","thread_id":"46968b13...",
 "payload":{"type":"human_review_required","title":"会诊结论待医生复核",
            "consensus":"...","proposal":"...","key_risks":[...]}}
```

---

## 7. 思考链事件翻译（StreamEventTranslator）

`app/agents/streaming/translator.py` 把三流原始 chunk 翻译为前端事件，与图执行解耦（重构自 qwen_agent 后单文件 894→365 行）。

职责：节点展示文案表 `_NODE_DISPLAY`、实时缓冲 `_live_buffers`（按节点/专家聚合增量）、全文渲染 `_node_full_content`、摘要 `_node_summary`、检索看板 `_node_stats_event`、tool_call 展开。

**例子——custom 流增量如何变成 node_token**：

```python
buf = self._live_buffers.setdefault(node, {})
buf[key] = buf.get(key, "") + text            # 增量累积
snapshot = self._render_live(node, buf)        # 渲染快照
translated.append({"type": "node_token", "node": node,
                   "label": _NODE_DISPLAY[node]["running"],
                   "content": snapshot, "status": "running"})
```

**多专家实时滚动**：reason 节点以 `expert` 标签写入，`_render_live` 把每位专家的增量渲染成 `▶ 【全科医生】(实时生成中)\n…`，前端并行滚动展示。

---

## 8. Agentic RAG 检索

### 8.1 职责拆分（阶段2 重构后）

| 文件 | 职责 |
|---|---|
| `app/rag/embeddings.py` | DashScopeEmbeddings（批量缓存 512 条） |
| `app/rag/reranker.py` | BGEReranker（gte-rerank API + Medical Evidence Score + 降级链标记） |
| `app/rag/retrievers.py` | HybridRetriever / UnifiedSearchEngine / 集合路由 / BM25 兼容（重新导出前两者） |
| `app/rag/data_loader.py` | PDF 加载、分块、chunk 级元数据、垃圾过滤 |
| `app/rag/qa_generator.py` | QA 对自建引擎（冷启动可选） |

### 8.2 5 Collection 主题隔离

`anatomy / guideline / etiology / treatment / prevention` 物理隔离，Evidence Router 按决策类型路由：

```python
COLLECTION_KEYS = ["anatomy", "guideline", "etiology", "treatment", "prevention"]
```

### 8.3 混合检索 + RRF + 重排

```text
查询 → Query Translator(术语标准化/同义词/Query Abstraction/Source Constraint)
     → 类别过滤 → BM25(rank_bm25) ∥ 向量(Chroma) → RRF 融合
     → gte-rerank 语义重排 → Medical Evidence Score 医学加权 → 输出
```

**RRF 融合**：`RRF(d) = Σ 1/(60+rank(d))`，无需校准异构分数。

**Medical Evidence Score 权重（9 项）**：

```text
Final = 0.20 语义 + 0.15 证据类型 + 0.10 指南权威 + 0.10 证据等级
      + 0.10 时效 + 0.10 subtopic + 0.10 决策节点 + 0.10 干预 + 0.05 时间窗
      − 0.30 不匹配 subtopic 惩罚
```

**降级链**：gte-rerank 不可用/限流 → 规则回退排序，`metadata["rerank_layer"] = "gte_api" | "rule_fallback"` 供质量看板追溯。

### 8.4 Agentic 闭环（证据评估 → 改写重查）

`research_plan`（决策规划 + PICO 查询）→ `evidence_router`（证据类型/类别/关键词）→ `retrieve` → `evidence_judge`（相关性/可信度/时效/覆盖度评分）→ 不足则 `query_rewrite` 再查，默认最多两轮。

**例子——证据编号**：每条证据 `R{轮次}-Q{查询}-E{结果}`，专家意见必须引用真实编号，如 `【证据 R1-Q1v3-E3】`。

### 8.5 向量库健康检查（阶段2）

`UnifiedSearchEngine._check_store_health` 在启动/热更新时校验"分块数 vs collection 条数"一致性，不一致写入 `health_warnings`，经 `/model/kb/status`、`/model/info` 暴露，防止"库空但服务正常"的静默故障。

---

## 9. 医疗工具调用（Tool Calling）

### 9.1 18 个工具（`app/agents/tools/`）

| 分组 | 工具 |
|---|---|
| 量表评估 | nihss_score, mrs_score, gcs_score |
| 溶栓治疗 | thrombolysis_window_check, rtpa_dose_calc |
| 禁忌症检查 | contraindication_check |
| 诊断分型 | toast_classify |
| 大血管闭塞筛查 | lvo_screening |
| 附加评估 | aspects_score, cha2ds2_vasc_score, has_bled_score, swallow_screen, rtpa_monitoring_checklist, vte_pressure_ulcer_prevention, hemorrhage_transformation_risk, followup_plan |
| 药物安全(DDI) | drug_interaction_check（18 组交互+60+别名） |
| 诊断编码 | icd10_coding（20 条脑卒中相关规则） |

### 9.2 实现模式（以 DDI 为例）

工具 = `StructuredTool.from_function(name, description, args_schema=Pydantic, func=adapt_model_func(...))`；实现函数接收 Pydantic 模型，`adapters.py` 适配为 langchain kwargs：

```python
def _drug_interaction_check(inputs: DrugInteractionInput) -> Dict:
    canonical = [_normalize(d) for d in inputs.drugs]
    ...  # 两两查 _INTERACTIONS, 按严重度排序
    return {"checked_drugs": ..., "interactions": [...], "note": "仅供辅助参考, 请由药师/医生审核"}

drug_interaction_check_tool = StructuredTool.from_function(
    name="drug_interaction_check",
    description="检查药物-药物相互作用(DDI)...",
    args_schema=DrugInteractionInput,
    func=adapt_model_func(DrugInteractionInput, _drug_interaction_check),
)
```

### 9.3 tool_use 节点（真正的 function-calling 循环）

`ToolUseNode` 让 LLM `bind_tools(18个工具)` 自主决定调用，最多 2 轮：

- **临床量表优先**：病例已明确给出 NIHSS/mRS/GCS 分数时跳过计算，以临床输入为准（`source=clinical_input`）；
- **估算标注**：无临床分数、由文本症状估算的 → `source=estimated` + 估算提示，避免冒充临床评估；
- **规则兜底**：LLM 未调用时按病例线索自动调度（偏瘫/失语→NIHSS、发病时长→时间窗、房颤→TOAST、治疗意向→禁忌症…）；
- **一致性校验**：工具结果与病例明确分数冲突时附加警示。

**Level 优先级**：L1 基础评估 → L2 禁忌症 → L3 剂量计算；`rtpa_dose_calc` 不得先于禁忌症检查。

### 9.4 统一执行器

`registry.call_tool(name, args)` 统一包装：未知工具返回可用列表、参数校验错误脱敏（只暴露字段与约束类型）、日志对 `patient_info` 截断脱敏。LLM 可直接调用，也可通过 `/model/tools/call` 独立调用。

---

## 10. 结构化输出（Structured Outputs）

### 10.1 Schema（`app/agents/schemas.py`）

intent / evidence_router / research_plan 三个关键节点的输出用 Pydantic 约束：

```python
class IntentResult(BaseModel):
    type: Literal["consultation", "knowledge", "irrelevant"]
    reason: str = ""
```

### 10.2 快路径 + 回退双保险

`make_structured_runner(llm, schema)`（`nodes/base.py`）：Mock/无 `with_structured_output` 的 LLM 返回 None；构建失败返回 None。节点先走结构化（Literal 校验失败自动回退），再走"流式生成 + JSON 解析"旧路径：

```python
if self._structured_runner is not None:
    result = await self._structured_runner.ainvoke(messages)
    if isinstance(result, IntentResult):
        return {"intent_type": result.type}
# 回退: 原有文本解析路径
```

**设计要点**：硬路由字段用 Literal（非法枚举触发回退）；`evidence_type` 等留空串由节点 normalize 统一兜底，保持既有语义。

---

## 11. 检查点持久化与 HITL 医生复核

### 11.1 Sqlite 检查点（`app/agents/orchestrators/checkpoint.py`）

- `CHECKPOINTER_PATH` 未配置 → 内存检查点（测试/无持久化）；配置后 → `AsyncSqliteSaver`；
- **必须在应用主事件循环内创建**（aiosqlite 连接绑定事件循环；曾在线程里创建导致"threads can only be started once"）；
- **必须全程持有上下文管理器**（GC 会关闭连接）；
- 普通线程结束后立即 `adelete_thread` 清理，仅 HITL 待复核线程保留；启动期按 7 天 TTL 兜底清理 `prune_stale_threads`。

### 11.2 HITL 医生复核

`human_review=true` 时，`compliance → human_review` 节点调用 `interrupt(payload)` 挂起：

```python
decision = interrupt({...会诊结论、关键风险、校验反馈...})
approved = bool(decision.get("approved", False))
feedback = str(decision.get("feedback", "") or "").strip()
```

- 批准 → `generate_report`；
- 驳回 → 医生意见写入 `validation_feedback`，路由回 `reason` 重新会诊（有界：`HITL_MAX_REJECTS` 默认 2 次，超过强制出报告）；
- `/model/resume`（模型侧）+ `/model/info` 展示检查点类型。

**例子——完整 HITL 调用链**：`POST /model/get_result {question, human_review:true}` → 流中出现 `human_review` 事件与 `thread_id` → `POST /model/resume {thread_id, approved:true}` → 继续生成报告 → `done{status:completed}`。

---

## 12. 多专家会诊（reason / debate / consensus）

模拟三甲医院 MDT：

- **reason**：全科医生、神经专科医生、临床药师**并行**独立意见（`asyncio.gather`），按专家标签实时流式打印；
- **debate**：每位专家阅读同伴意见，明确同意点/冲突点/修正结论，输出质询全文；
- **consensus_agent**：中立主持人输出 PROPOSAL + CRITIQUE（共识、被否决分歧及原因）。

三位专家由同一 `llm_proposer`（main 角色）驱动，prompt 内置专家角色定义与"用户指示优先"契约。

---

## 13. 安全校验与合规审计

### 13.1 双层校验（validate）

- **规则引擎**：命中 `rules_config.yaml` 硬性禁忌症（如活动性出血）直接拦截；
- **LLM 反思**：深层医学逻辑与指南合规审查；
- 反思循环有界（≤3 次），失败强制输出 + 安全警告。

### 13.2 合规审计节点（compliance，纯规则零 LLM 成本）

`validate → compliance → human_review`：

- **PHI 检测**：对会诊草稿做 HIPAA 18 类扫描（复用 `security.detect_phi`）；
- **绝对化断言**：`100%`、`必定` 等，**排除"绝对禁忌证/适应证"合法术语**（负向断言 `绝对(?!禁忌|适应)`）；
- **具体剂量**（警告级，不判失败）；
- 审计留痕：`compliance_passed/issues/audit`（时间戳 + 免责声明）写入状态 + 服务端日志 `[compliance] passed=...`。

### 13.3 PHI 脱敏（HIPAA Safe Harbor 18 类中文本可识别的 15 类）

`mask_sensitive`（身份证/手机号/银行卡/邮箱/IP/URL/车牌/日期/90+岁/病历号/医保号/证件号/序列号/座机），日志入账前必须过一遍；`detect_phi` 返回命中类别。

---

## 14. 提问提取与按问题直答

### 14.1 问题：追问被当完整会诊

用户追问"该患者需要抗凝吗？"曾被意图节点误判为 knowledge，得到脱离患者上下文的泛答。

### 14.2 三层修复

1. **意图结合历史上下文**（`intent_node.py`）：提示词注入 `all_info`；规则兜底 `_force_consultation`——输入引用"该患者/这个患者/他/她"且历史含患者信息 → 强制 consultation；
2. **提问提取器**（`app/agents/utils/question_extractor.py`）：识别三类形态——
   - 显式列表："请回答以下问题：1. … 2. …"
   - **结构化考题**："请写出该患者的：（1）定位诊断（含依据）；（2）TOAST…（简述理由）；（3）危险因素…"
   - 自然问句：以 ?/？/吗/呢 结尾或 是否/如何/为什么 开头
   - 防误判：化验值（INR 1.1）、"补充信息：…"陈述不提取
3. **确定性提取优先于 LLM**（`analysis_node.py`）：规则命中 ≥1 问即用规则结果，杜绝 LLM 编造问题（曾编造出"该患者是否需要溶栓?"）。

命中 `user_questions` 后，reason/debate/report 切换到"按原问题逐项回答"契约（`### 问题N：…` + 直接结论 + 理由 + 证据 + 信息缺口），知识问答节点也注入患者上下文。

**例子**（真实端到端）：

```text
输入: 患者男69岁突发右侧肢体无力2小时。请问该患者是否适合静脉溶栓？
输出: ### 问题1：该患者是否适合静脉溶栓？
      结论：不足以支持
      理由：- 未完成头颅影像学检查，无法排除脑出血【证据 R1-Q1v1-E3】
            - 未提供当前血压值…
      风险权重排序 / 信息缺口 / 下一步建议
```

---

## 15. 安全、并发与错误契约

### 15.1 请求并发闸（`app/utils/security.py`）

单用户默认 2、全局默认 8 的在途请求上限，超限直接 429（SSE 流外拒绝），防止滥用拖垮模型服务；`/model/info` 展示 `in_flight_requests`。

### 15.2 错误脱敏（`app/utils/error_codes.py`）

对外只给错误码 + 通用文案（E1001 超时 / E1002 安全拒绝 / E1003 OOM / E1099 未知），细节只进服务端日志：

```python
{"type":"error","error":{"code":"E1099","message":"未知错误","retryable":false,...}}
```

### 15.3 输入约束与 CORS

question≤2万字符、all_info≤10万、影像≤5张、KB 上传≤10 个且单文件≤20MB；CORS 默认关闭（`MODEL_CORS_ORIGINS` 按需放行）。

---

## 16. LLM 用量跟踪与成本估算

`app/utils/usage.py`：contextvars 请求级账本 + `UsageCallbackHandler`（挂到 ChatOpenAI callbacks）。

经历过的两个关键修复：

1. **流式/结构化路径 `llm_output` 为空**：langchain-core 1.x 下 token 在 `generation.message.usage_metadata`，回调双路径提取（`llm_output.token_usage` 或 `usage_metadata` 求和）；
2. **DashScope 自定义 base_url 不返回流式用量**：显式 `stream_usage=True`；
3. **线程池丢失 contextvars**：命名/摘要经 `run_in_executor` 时用 `contextvars.copy_context().run` 包裹，保证线程内也能记账。

**例子**：

```json
{"calls":3,"input_tokens":1248,"output_tokens":172,
 "by_model":{"qwen-turbo":{"calls":3,"input_tokens":1248,"output_tokens":172,"cost":0.0005}},
 "cost":0.0005,"seconds":8.2}
```

---

## 17. 评测闭环

### 17.1 两级门禁（CI 每次执行）

- **RAGAS 检索硬门禁**（`app/evaluation/gate.py`）：Recall@3≥0.783 / MRR≥0.757 / NDCG@10≥0.763（软门禁 Recall@10/faithfulness 仅告警），指标四舍五入到 3 位对比基线；
- **离线规则评测**（`app/evaluation/benchmark.py --gate`）：6 题冻结用例（禁剂量/禁确诊语气/引用白名单），coverage=1.0、pass_rate≥0.8。

### 17.2 资产

`evaluation/ragas_snapshot.json`（30 题基线快照）、`offline_cases.jsonl` + `offline_predictions.jsonl`（冻结真实预测）、`BASELINE-2026-08-15.md`（升级基线）、`UPGRADE-2026-08-16.md`（升级总结）。

---

## 18. 配置体系

| 文件 | 内容 | 热更新 |
|---|---|---|
| `config/models.yaml` | 模型路由（角色/超时/重试/环境变量覆盖） | 需重启 |
| `config/prompts.yaml` | 提示词模板 | `/admin/reload_config` |
| `config/report_templates.yaml` | 5 种报告模板（emergency/analysis/outpatient/consultation/fast） | 同上 |
| `config/expert_config.yaml` | 专家角色与优先级 | 同上 |
| `config/rules_config.yaml` | 禁忌症规则与校验参数 | 同上 |
| `config/limits_config.yaml` | 参数限制（子问题数/证据字符/提案字符） | 同上 |

---

## 19. 目录结构

```text
model/
├── app/
│   ├── main.py                  # 薄入口: 路由注册 + /health(503 就绪门禁)
│   ├── bootstrap.py             # lifespan + init_all_resources(7步初始化)
│   ├── runtime.py               # resources 容器 + _KbJobs + JWT 鉴权
│   ├── api/                     # /model /ai /admin 三组路由 + 请求模型
│   ├── agents/
│   │   ├── core/schema.py       # ClinicalState(TypedDict)
│   │   ├── schemas.py           # 结构化输出 Pydantic
│   │   ├── orchestrators/
│   │   │   ├── clinical_graph.py# 推理图(节点/条件边/反思循环/合规/HITL)
│   │   │   ├── qwen_agent.py    # 门面: run/resume/流消费/缺口追问/检查点清理
│   │   │   ├── checkpoint.py    # Sqlite 检查点 + TTL 清理
│   │   │   └── nodes/           # 18 个节点(意图/记忆/分析/工具/规划/路由/检索/评估/改写/推理/辩论/共识/校验/合规/复核/报告/知识/拒绝)
│   │   ├── streaming/translator.py  # 三流→SSE 事件翻译
│   │   ├── tools/               # 18 个医疗工具 + registry
│   │   └── utils/               # question_extractor / json_utils / text_utils
│   ├── rag/                     # embeddings / reranker / retrievers / data_loader / qa_generator
│   ├── config/                  # 配置加载器 + 6 个 YAML
│   ├── services/                # 影像识别 / PubMed
│   ├── utils/                   # security / usage / error_codes / context_summary / naming_model
│   └── evaluation/              # gate / benchmark
├── evaluation/                  # RAGAS 快照 / 冻结用例 / 基线文档
├── scripts/                     # smoke / eval_ragas / enrich_* / migrate
├── tests/                       # 200 个离线测试
└── requirements.txt / requirements.lock  # uv 锁文件可复现构建
```

---

## 20. 端到端链路示例

### 20.1 一次临床问诊（简化）

```text
1. POST /model/get_result
   {"question":"患者男69岁突发右侧肢体无力2小时，NIHSS 16分，CT未见出血",
    "all_info":"既往高血压、房颤","show_thinking":true}

2. intent        → consultation
3. memory        → 激活患者分层记忆
4. analysis      → 结构化上下文 + 检索子问题 + user_questions([])
5. tool_use      → LLM 调用 nihss_score / contraindication_check / toast_classify
                   结果注入上下文, 临床已给分时跳过计算
6. research_plan → 决策节点[是否溶栓/CTA-LVO/血压/病因] + PICO 查询
7. evidence_router→ treatment→[指南,共识]; anatomy→[教材]
8. retrieve      → BM25∥向量 → RRF → gte-rerank → Medical Evidence Score
9. evidence_judge→ 质量评分, 不足→query_rewrite 再查(有界)
10. reason        → 三专家并行独立意见(流式并行打印)
11. debate        → 交叉质询全文
12. consensus_agent→ PROPOSAL + CRITIQUE
13. validate      → 规则+LLM 双层校验, 未过→反思回环(≤3次)
14. compliance    → PHI/绝对化断言/剂量审计, [compliance] 日志留痕
15. human_review  → 默认直通(未开启复核)
16. generate_report→ 打字机流式输出报告, done 携带 usage
```

### 20.2 一次结构化考题（按题直答）

```text
输入: 请写出该患者的：（1）定位诊断和定性诊断（含依据）；（2）最可能的TOAST病因分型（简述理由）；（3）主要的脑卒中危险因素（至少列出4项）。

question_extractor 提取 → ["定位诊断和定性诊断（含依据）",
                            "最可能的TOAST病因分型（简述理由）",
                            "主要的脑卒中危险因素（至少列出4项）"]

输出:
### 问题1：定位诊断和定性诊断（含依据）   → 左侧MCA供血区急性缺血性卒中 + 依据
### 问题2：最可能的TOAST病因分型（简述理由）→ 暂归不明原因型(SUE), 需影像/心脏评估
### 问题3：主要的脑卒中危险因素（至少列出4项）→ 高血压/糖尿病/吸烟/年龄>65
```

### 20.3 一次 HITL 医生复核

```text
POST /model/get_result {question, human_review:true}
  → ... → validate → compliance → human_review(interrupt 挂起)
  → SSE: {"type":"human_review","thread_id":"…","payload":{…}}

POST /model/resume {thread_id, approved:false, feedback:"请补充CTA评估"}
  → 驳回: 反馈写入 validation_feedback, 路由回 reason 重新会诊
  → 再次挂起(第2次) 或 达到上限后强制生成报告
```

---

## 附：测试与门禁

```bash
cd model
# 全量离线测试(200 个)
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_rag.py \
  --ignore=tests/test_agentic_rag.py --ignore=tests/test_thinking_events.py
# 流式冒烟
.\.venv\Scripts\python.exe scripts/smoke_langgraph_v1.py
# 评测门禁
.\.venv\Scripts\python.exe -m app.evaluation.gate --ragas evaluation/ragas_snapshot.json
.\.venv\Scripts\python.exe -m app.evaluation.benchmark --cases evaluation/offline_cases.jsonl \
  --predictions evaluation/offline_predictions.jsonl --output /tmp/offline_report.json \
  --gate --min-coverage 1.0 --min-pass-rate 0.8
```
