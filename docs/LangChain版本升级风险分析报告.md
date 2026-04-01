# LangChain 版本升级风险分析报告

**项目**：Synapse MD · Python 后端  
**报告日期**：2026-04-01  
**当前版本**：`langchain==0.1.20` / `langchain-community==0.0.38`  
**目标版本**：`langchain>=0.3.x` / `langchain-community>=0.3.x`  
**版本跨度**：横跨 0.1 → 0.2 → 0.3 三个大版本，约 18 个月的破坏性变更积累  

> **阅读说明**：本报告聚焦"升级会让什么东西坏掉"，每一条风险均附有对应代码位置和具体表现，按严重程度排列。

---

## 总体风险评级

| 维度 | 评级 | 说明 |
|------|------|------|
| 启动时 ImportError | 🔴 高 | 多处 import 路径在新版本已迁移，升级后服务无法启动 |
| 模型调用行为变更 | 🟡 中 | ChatTongyi 参数语义变化，streaming 行为不同 |
| 向量库数据兼容性 | 🟡 中 | 已持久化的 chroma_db 数据格式可能与新版 chromadb 不兼容 |
| 依赖链版本冲突 | 🔴 高 | 当前 requirements.txt 存在已知的版本号矛盾 |
| SSE 流式通路 | 🟡 中 | astream 内部行为有细微变化，影响心跳机制 |
| 业务逻辑回归 | 🟢 低 | 手搓逻辑占比高，大部分核心推理不依赖 LangChain 版本 |

---

## 第一部分：当前依赖版本存量问题（升级前就已存在）

升级之前，有两处**现有版本号矛盾**需要先确认是否已造成潜在问题。

### 1.1 langchain-openai 与 openai 版本不匹配

```
langchain-openai==0.1.7   # 发布于 2024-06 前后，支持 openai>=1.10.0
openai==1.109.1           # 极新版本，发布于 2025 年
```

**涉及代码**：`utils/naming_model.py:21-28`

```python
self.llm = ChatOpenAI(
    model_name="deepseek-chat",
    openai_api_base="https://api.deepseek.com/v1",  # 旧参数名
    openai_api_key=api_key,
    temperature=0.3,
    max_tokens=300,
    request_timeout=25
)
```

**风险**：`langchain-openai==0.1.7` 的内部实现调用 `openai` SDK 的方式与 `openai==1.109.1` 之间存在大版本 API 跨越，虽然 LangChain 做了一定兼容包装，但 `request_timeout` 参数在 `openai>=1.0` 中已更名为 `timeout`，可能被静默忽略，导致命名服务无超时保护而挂起。

**结论**：这是**存量风险，升级前应先验证**命名模型是否按预期超时。

---

### 1.2 Pydantic v2 与 LangChain 0.1.x 的兼容模式

```
pydantic==2.12.5
langchain==0.1.20
```

LangChain 0.1.x 通过 `pydantic.v1` 兼容层支持 Pydantic v2，这套兼容层在 LangChain **0.3.x 中被完全移除**。当前能运行说明兼容层生效，但升级到 0.3.x 后，原来通过兼容层掩盖的问题会立即暴露。

---

## 第二部分：升级到 0.3.x 的逐项破坏性变更

### R1：RecursiveCharacterTextSplitter / PyPDFLoader Import 路径变更

**严重程度**：🔴 高（直接导致启动失败）  
**涉及文件**：`makeData/retrieve.py`（未确认具体行号，需对照实际 import）

**变更详情**：

从 LangChain 0.2.x 起，文本处理工具类从 `langchain` 主包拆分到独立包 `langchain_text_splitters`，文档加载器全量归入 `langchain_community.document_loaders`：

| 旧 Import（0.1.x） | 新 Import（0.3.x） | 是否需要新依赖 |
|---|---|---|
| `from langchain.text_splitter import RecursiveCharacterTextSplitter` | `from langchain_text_splitters import RecursiveCharacterTextSplitter` | 是：`pip install langchain-text-splitters` |
| `from langchain.document_loaders import PyPDFLoader` | `from langchain_community.document_loaders import PyPDFLoader` | 无（已在 community 包内） |
| `from langchain.vectorstores import Chroma` | `from langchain_chroma import Chroma` | 是：`langchain-chroma`（已有） |

**表现**：升级后服务启动时 `makeData/retrieve.py` 抛出 `ImportError`，向量库初始化失败，整个服务无法就绪。

**修复方式**：
```python
# 修改前
from langchain.text_splitter import RecursiveCharacterTextSplitter
# 修改后
from langchain_text_splitters import RecursiveCharacterTextSplitter
```
同时在 `requirements.txt` 中新增 `langchain-text-splitters>=0.3.0`。

---

### R2：DashScopeEmbeddings Import 路径变更

**严重程度**：🔴 高（向量库初始化失败）  
**涉及文件**：`makeData/retrieve.py`（向量存储构建部分）

**变更详情**：

```python
# 旧（0.1.x）
from langchain_community.embeddings import DashScopeEmbeddings

# 新（0.3.x）
from langchain_community.embeddings import DashScopeEmbeddings  # ← 路径未变
# 但构造参数有变化：dashscope_api_key 参数名可能需改为 api_key
```

`DashScopeEmbeddings` 的 import 路径本身在 `langchain-community` 中相对稳定，但其内部依赖的 `dashscope` SDK 行为绑定版本：当前锁定 `dashscope==1.25.9`，升级 `langchain-community` 到 0.3.x 后可能拉入更新版 `dashscope`，导致 Embedding 调用行为不一致，进而破坏向量库的语义检索精度。

**表现**：
- 轻则：新写入的向量与旧向量使用不同版本模型编码，语义距离计算失真，检索准确率下降
- 重则：`DashScopeEmbeddings` 构造失败，向量库无法加载，服务启动报错

---

### R3：ChatTongyi 构造参数语义变化

**严重程度**：🟡 中（功能可用，但行为不符合预期）  
**涉及文件**：`main.py:80-81`、`qwen_agent.py:900-905`

**当前代码**：
```python
# main.py:80-81
llm_max = ChatTongyi(model_name="qwen-max", streaming=True)
llm_plus = ChatTongyi(model_name="qwen-plus", streaming=True)

# qwen_agent.py:900-905（每次 /ai/analyze 请求都 new 一个）
llm_fast_temp = ChatTongyi(
    model_name="qwen-plus",
    temperature=0.1,
    streaming=False
)
```

**变更详情**：

**（a）`streaming` 构造参数被弃用**

LangChain 0.2.x 开始，`streaming=True` 在构造器中设置的语义从"全局开关"改为"仅影响 `.invoke()` 默认行为"。在 0.3.x 中，推荐做法是不在构造器中设置，而是通过调用方式区分：
- 需要流式 → 使用 `.astream()`
- 需要非流式 → 使用 `.ainvoke()`

当前代码已经分别使用了 `.astream()` 和 `.ainvoke()`，所以实际上 `streaming=True` 这个参数已经是冗余的。但在 `streaming=False` 的情况下（`qwen_agent.py:904`），如果新版本忽略该参数并默认返回流式，会导致 `ainvoke` 返回值从 `AIMessage` 变成 `AIMessageChunk`，破坏 `_parse_json(getattr(response, "content", ""), {})` 的解析逻辑。

**（b）`model_name` 参数被弃用**

在 `langchain-community>=0.2.0` 中，`ChatTongyi` 的 `model_name` 参数已被标记为 deprecated，正式参数名改为 `model`。直接升级会产生 `DeprecationWarning`，未来版本会直接报错：

```python
# 旧（会触发 DeprecationWarning，未来版本 TypeError）
ChatTongyi(model_name="qwen-max", streaming=True)

# 新
ChatTongyi(model="qwen-max")
```

**表现**：日志中出现大量 DeprecationWarning；`/ai/analyze` 接口在极端情况下可能因返回类型变化导致 JSON 解析失败，返回兜底的"中风险"结论。

---

### R4：ChatOpenAI `openai_api_base` 参数被移除

**严重程度**：🟡 中（DeepSeek 命名服务静默失效）  
**涉及文件**：`utils/naming_model.py:21-28`

**当前代码**：
```python
self.llm = ChatOpenAI(
    model_name="deepseek-chat",
    openai_api_base="https://api.deepseek.com/v1",  # 已弃用参数
    openai_api_key=api_key,
    temperature=0.3,
    max_tokens=300,
    request_timeout=25                               # 已弃用参数
)
```

**变更详情**：

在 `langchain-openai>=0.1.8`（对应 `langchain>=0.2`）中：
- `openai_api_base` → `base_url`（直接对应 `openai` SDK 的 `base_url` 参数）
- `request_timeout` → `timeout`
- `max_tokens` → 保持兼容，但行为可能变化（某些模型需要用 `max_completion_tokens`）

**表现**：升级后 `ChatOpenAI` 构造器忽略 `openai_api_base` 参数，请求打向 `api.openai.com` 而非 `api.deepseek.com`，导致命名服务因域名不可达或 API Key 无效而失败。失败后的兜底逻辑（`main.py:275`）会将会话名称设置为 `"咨询"`，功能层面降级但不崩溃。

**修复方式**：
```python
self.llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=api_key,
    temperature=0.3,
    max_tokens=300,
    timeout=25
)
```

---

### R5：BM25Retriever 依赖包迁移

**严重程度**：🟡 中（依条件触发 ImportError）  
**涉及文件**：`makeData/retrieve.py`（BM25Retriever 初始化部分）

**变更详情**：

```python
# 旧（0.0.38）
from langchain_community.retrievers import BM25Retriever

# 新（0.3.x）—— 路径相同，但依赖 rank_bm25 版本要求提升
from langchain_community.retrievers import BM25Retriever  # import 路径不变
```

BM25Retriever 的 import 路径在 `langchain-community` 内保持稳定，但其 `from_documents()` 类方法内部使用 `rank_bm25` 的方式在新版本中要求 `rank_bm25>=0.2.2`（当前已满足 `rank_bm25==0.2.2`）。

真正的风险在于：**`langchain-community` 升级后可能拉取新版 `rank_bm25`，而旧版 `chroma_db_unified` 持久化数据的 BM25 索引格式未必兼容**（BM25 检索器每次从文档重建，无持久化问题，此处风险较低）。

---

### R6：已持久化向量库（chroma_db_unified）格式兼容性

**严重程度**：🟡 中（数据层面不可逆风险）  
**涉及文件**：`makeData/retrieve.py`、`CONFIG["persist_dir"]` 指向的磁盘目录

**背景**：

系统使用 `Chroma` 持久化向量库于 `./chroma_db_unified`，其中存储了所有 PDF 文档的向量数据。此数据由 `chromadb==0.5.23` 写入。

**变更详情**：

`chromadb` 的数据格式（SQLite schema 和 HNSW 索引文件格式）在 0.4.x → 0.5.x → 未来版本之间有过不向前兼容的迁移。升级 `langchain-community` 可能隐式升级 `chromadb`：

```
langchain-chroma==0.1.4  →  langchain-chroma>=0.1.x（新版）
    └─ 依赖 chromadb>=0.4.0（旧上限）→ 可能拉入 chromadb>=0.6.x
```

**表现**：启动时 `UnifiedSearchEngine` 加载旧格式持久化数据库失败，抛出 `chromadb.errors.InvalidCollectionException` 或 SQLite schema 不兼容异常，导致整个服务初始化失败（`lifespan` 中会 `raise`，FastAPI 进程退出）。

**这是唯一需要数据迁移的风险，且无法自动回滚。**

**规避方案**：
1. 升级前**备份** `chroma_db_unified/` 目录
2. 升级后如数据库无法加载，删除旧数据库目录，重新运行向量库构建流程
3. 重建需重新解析所有 PDF，耗时取决于文档数量

---

### R7：asyncio + astream 的心跳机制兼容性

**严重程度**：🟡 中（SSE 断流或心跳失效）  
**涉及文件**：`main.py:244-265`

**当前代码**：
```python
# main.py:244-265
pending_task = None
while True:
    if pending_task is None:
        pending_task = asyncio.ensure_future(async_gen.__anext__())

    done, _ = await asyncio.wait({pending_task}, timeout=10.0)

    if not done:
        yield json.dumps({"type": "heartbeat", ...}) + "\n"
        continue

    pending_task = None
    try:
        event = done.pop().result()
    except StopAsyncIteration:
        break
```

**风险点**：

此心跳机制依赖 `async_gen.__anext__()` 返回的是一个标准 Python `coroutine` 对象，可以被 `asyncio.ensure_future()` 包装为 `Task`，并被 `asyncio.wait()` 监控。

LangChain 的 `astream()` 方法在不同版本对异步生成器的内部实现有差异：
- **0.1.x**：直接 `yield chunk` 的标准异步生成器，`__anext__` 返回 coroutine，行为稳定
- **0.2.x+**：部分模型的 `astream()` 内部改用 `asyncio.Queue` 或事件循环驱动，`__anext__` 的语义不变，但**取消行为**有差异

当前代码的关键设计点是：`asyncio.wait` 超时不取消 task，task 继续在后台运行（已在注释中明确说明，见 `main.py:234-236`）。这个设计在新版本 LangChain 的 astream 实现中理论上仍然有效，但**没有官方保证**。

一旦新版本 astream 的 `__anext__` 在特定条件下抛出 `RuntimeError` 而非 `StopAsyncIteration`（部分生成器在 loop 关闭时会如此），心跳循环会直接走到 `except Exception as e` 分支，导致本次 SSE 流以 error 事件结束而非正常 done。

---

### R8：langchain_core.messages 的 TypedDict 接口变更

**严重程度**：🟢 低（有警告，不影响功能）  
**涉及文件**：`qwen_agent.py:11`

```python
from langchain_core.messages import HumanMessage, SystemMessage
```

`HumanMessage` 和 `SystemMessage` 的 import 路径在 0.1.x → 0.3.x 中**保持稳定**，这是 LangChain 明确保证稳定的公共 API。但在 0.3.x 中，这两个类底层从 Pydantic v1 模型全面迁移到 Pydantic v2 模型，不再依赖兼容层。

**表现**：如果项目其他地方有直接操作 `HumanMessage.__fields__`（Pydantic v1 API）而非 `HumanMessage.model_fields`（Pydantic v2 API），会产生 `AttributeError`。通过 grep 检查，当前代码仅使用 `HumanMessage(content=...)` 和 `SystemMessage(content=...)` 构造方式，**无此风险**。

---

## 第三部分：依赖链整体冲突分析

升级不能只升 `langchain`，整个依赖树必须协同更新。以下是各包之间的版本约束矩阵：

### 3.1 强依赖关系图

```
langchain==0.3.x
  ├── langchain-core==0.3.x        （必须同步升级）
  ├── langchain-community==0.3.x   （必须同步升级）
  │     ├── ChatTongyi
  │     ├── BM25Retriever
  │     ├── DashScopeEmbeddings
  │     └── PyPDFLoader
  ├── langchain-openai==0.2.x+     （需升级，否则与 openai>=1.50 冲突）
  │     └── openai>=1.40.0
  └── langchain-chroma==0.1.x+
        └── chromadb>=0.5.0        （↑ 可能触发 R6 数据格式问题）

langgraph>=0.2.0（若计划迁移 SimpleGraph）
  └── langchain-core>=0.2.0       （已满足）
```

### 3.2 必须同步升级的包清单

| 包名 | 当前版本 | 目标版本 | 原因 |
|------|----------|----------|------|
| `langchain` | 0.1.20 | >=0.3.0 | 主包升级 |
| `langchain-core` | (隐式) | >=0.3.0 | 必须与主包同步，否则 ImportError |
| `langchain-community` | 0.0.38 | >=0.3.0 | ChatTongyi、BM25、Embeddings |
| `langchain-openai` | 0.1.7 | >=0.2.0 | 兼容 openai>=1.40 |
| `langchain-chroma` | 0.1.4 | >=0.1.4（谨慎） | 尽量不动，避免触发 R6 |
| `langchain-text-splitters` | 无 | >=0.3.0 | 新增依赖（R1） |

### 3.3 不建议随 LangChain 一起升级的包

| 包名 | 当前版本 | 理由 |
|------|----------|------|
| `chromadb` | 0.5.23 | R6 风险，升级需数据迁移，单独规划 |
| `dashscope` | 1.25.9 | 与向量检索、Rerank、VL 三个服务耦合，独立测试后再升 |
| `pydantic` | 2.12.5 | 已是 v2，升级 LangChain 后无需改动 |
| `openai` | 1.109.1 | 已超前，升级 langchain-openai 后会自动拉取兼容版本 |

---

## 第四部分：按迁移批次的风险矩阵

结合迁移报告的四个批次，各批次升级时的实际风险：

### 第一批（低风险组件替换）迁移时的附带风险

迁移 `_parse_json → JsonOutputParser`、`parse_score_response → PydanticOutputParser` 时，需要升级 `langchain-core` 到 0.3.x。

**附带触发**：R1（Import 路径）、R8（Pydantic 模型变更）  
**评估**：R8 在当前代码中已确认无影响；R1 必须同时修复。

### 第二批（Prompt 管理）迁移时的附带风险

迁移 Prompt 到 `ChatPromptTemplate` 时，`langchain-core` 版本已升，无新增风险。

**注意点**：`prompts.yaml` 中如有内嵌 JSON 示例（含 `{` `}`），迁移到 `ChatPromptTemplate` 时必须全部转义为 `{{` `}}`。当前 `_RISK_API_PROMPT_TEMPLATE`（`qwen_agent.py:25-52`）中有多处 `{{...}}` 已正确转义，但 `score_turn_value` 的 fallback prompt（`context_summary.py:79`）中有 `{{"score": 0.0-1.0, "reason": "..."}}`，需确认转义是否完整。

### 第三批（LangGraph 架构重构）迁移时的附带风险

这是风险最集中的批次：

1. **新增 LangGraph 依赖**需要 `langchain-core>=0.3`，此时 R1/R2/R3/R4 必须全部已修复
2. **`TokenAggregator` 与 LangGraph `astream_events` 的整合**：  
   LangGraph 的 `astream_events(version="v2")` 输出的是结构化事件流（`on_chat_model_stream`、`on_tool_end` 等），与当前 `run_clinical_reasoning` 输出的 `{"type": "thinking", "step": ..., "content": ...}` 格式完全不同。`main.py` 的 `generate()` 包装层需要做事件格式适配，不能直接替换。
3. **`SimpleGraph` 的节点返回值约定**：当前节点函数返回 `dict`，由 `_CompiledGraph.ainvoke` 做 `state.update()`。LangGraph 的节点函数需要返回 `TypedDict` 的子集，`State` 定义必须与 `ClinicalState`（`qwen_agent.py:105-119`）对齐，迁移时字段命名需完全一致。

### 第四批（外部接口规范化）迁移时的附带风险

Rerank 接口迁移涉及 `langchain-community` 中 `DashScopeRerank` 的可用性：

在 `langchain-community==0.0.38` 中，`DashScopeRerank` **不存在**（该类在 0.2.x 版本的 community 包中才被引入）。因此迁移 Rerank 组件**必须先升级 langchain-community**，不能提前规划到第四批而延迟升级。

---

## 第五部分：升级策略建议

### 5.1 分阶段升级路径（最低风险）

```
阶段 0：备份与环境准备
  ├── 备份 chroma_db_unified/ 目录（R6 的唯一数据风险）
  ├── 创建新 conda/venv 环境，不在生产环境上直接升级
  └── 固定 chromadb==0.5.23（在 requirements.txt 中硬钉，防止被拉升）

阶段 1：最小化升级（仅升核心包，验证服务能启动）
  langchain==0.1.20 → 0.3.x
  langchain-core → 0.3.x
  langchain-community==0.0.38 → 0.3.x
  langchain-openai==0.1.7 → 0.2.x+
  langchain-text-splitters → 0.3.x（新增）
  
  修复项（必须同步完成，否则服务无法启动）：
  ├── R1：修复 RecursiveCharacterTextSplitter / PyPDFLoader import 路径
  ├── R3：ChatTongyi(model_name=...) → ChatTongyi(model=...)
  └── R4：ChatOpenAI(openai_api_base=...) → ChatOpenAI(base_url=...)

阶段 2：验证核心功能
  ├── 运行 pytest test_get_model_result.py
  ├── 手动测试 /model/get_result 接口（consultation / knowledge / irrelevant 三条路径）
  ├── 手动测试 /ai/analyze 接口
  └── 验证 SSE 心跳是否正常（模拟慢响应场景）

阶段 3（可选）：LangGraph 迁移
  在阶段 2 验证通过后，再进行 SimpleGraph → LangGraph 的重构
```

### 5.2 硬钉版本的 requirements.txt 建议

```
# LangChain 生态（协同升级）
langchain>=0.3.0,<0.4.0
langchain-core>=0.3.0,<0.4.0
langchain-community>=0.3.0,<0.4.0
langchain-openai>=0.2.0,<0.3.0
langchain-text-splitters>=0.3.0,<0.4.0
langchain-chroma>=0.1.4,<0.2.0      # 谨慎：与 chromadb 版本强绑定

# 向量库（硬钉，防止数据格式问题）
chromadb==0.5.23                     # ← 硬钉，不随 langchain-chroma 升级

# 下游 AI SDK（独立测试后再升）
dashscope==1.25.9
openai>=1.40.0,<2.0.0
```

---

## 第六部分：回滚方案

如果升级后发现不可预期的问题：

1. **代码回滚**：所有修改在 git 中提交为独立 commit，`git revert` 或 `git checkout` 恢复
2. **依赖回滚**：保留升级前的 `requirements.txt`，在隔离环境重建即可
3. **数据回滚（R6 专项）**：从备份目录还原 `chroma_db_unified/`，这是唯一无法通过代码回滚解决的问题

**关键原则**：R6（向量库数据格式）是本次升级中**唯一不可逆的风险**，必须在升级前完成备份，其余所有风险均可通过代码和依赖回滚完全恢复。

---

## 附录：风险汇总速查表

| 编号 | 风险描述 | 严重程度 | 涉及文件 | 是否阻塞启动 | 是否可回滚 |
|------|----------|----------|----------|-------------|-----------|
| R1 | TextSplitter / PDFLoader Import 路径变更 | 🔴 高 | `makeData/retrieve.py` | 是 | 是 |
| R2 | DashScopeEmbeddings 参数/版本变化 | 🔴 高 | `makeData/retrieve.py` | 是 | 是 |
| R3 | ChatTongyi `model_name`/`streaming` 参数弃用 | 🟡 中 | `main.py:80-81`，`qwen_agent.py:900` | 否（警告） | 是 |
| R4 | ChatOpenAI `openai_api_base` 参数移除 | 🟡 中 | `utils/naming_model.py:21-28` | 否（降级） | 是 |
| R5 | BM25Retriever 依赖链变化 | 🟡 中 | `makeData/retrieve.py` | 否 | 是 |
| R6 | Chroma 持久化数据格式不兼容 | 🟡 中 | `chroma_db_unified/`（磁盘） | 条件性 | **数据需手动备份** |
| R7 | asyncio + astream 心跳机制兼容性 | 🟡 中 | `main.py:244-265` | 否（偶发） | 是 |
| R8 | langchain_core.messages Pydantic v2 迁移 | 🟢 低 | `qwen_agent.py:11` | 否 | 是 |
| 存量 | langchain-openai 与 openai 版本差距 | 🟡 中 | `utils/naming_model.py` | 否（静默失效） | 是 |
| 存量 | Pydantic v2 兼容层在 0.3.x 移除 | 🟡 中 | 全局 | 条件性 | 是 |
