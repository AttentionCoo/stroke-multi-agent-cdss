# LangChain 迁移可行性分析报告

**项目**：Synapse MD · Python 后端  
**报告日期**：2026-04-01  
**分析范围**：`/Users/mhy/NeuroAgentSystem/model`（26 个 .py 文件）

---

## 1. 现状总览

### 1.1 已使用 LangChain 的部分

| 组件 | 文件 | 用法 |
|------|------|------|
| `ChatTongyi` | `main.py:80-81` | 实例化 qwen-max / qwen-plus，`streaming=True` |
| `ChatOpenAI`（对接 DeepSeek） | `utils/naming_model.py:21-28` | 实例化命名模型，自定义 `api_base` |
| `SystemMessage` / `HumanMessage` | `qwen_agent.py`（多处）、`qwen_assistant.py` | 手动组装 messages 列表 |
| `Chroma` 向量存储 | `makeData/retrieve.py` | 通过 `langchain-chroma` 构建/加载向量库 |
| `BM25Retriever` | `makeData/retrieve.py` | 混合检索的稀疏检索部分 |
| `RecursiveCharacterTextSplitter` | `makeData/retrieve.py` | 文档分块 |
| `PyPDFLoader`（或类似 PDF loader） | `makeData/retrieve.py` | PDF 文档加载 |

**总结**：仅使用了 LangChain 的**模型接入层**和**向量库层**，Chain、LCEL、PromptTemplate、OutputParser、Memory、Tool、LangGraph 等核心组件**一概未使用**。

### 1.2 "手搓"部分数量统计

| 类别 | 数量 | 主要文件 |
|------|------|----------|
| 硬编码 Prompt（f-string/三引号字符串） | 16+ 处 | `qwen_agent.py`（13处）、`vision_service.py`（3处）、`context_summary.py`（2处）、`medical_agent.py`（2处） |
| 手动 `ainvoke` 调用 | 9 处 | `qwen_agent.py` |
| 手动 `invoke` 调用 | 5 处 | `medical_agent.py`、`naming_model.py`、`context_summary.py` |
| 手动 `astream` 调用 | 4 处 | `qwen_agent.py`、`qwen_assistant.py` |
| 绕过 LangChain 的直接 HTTP/SDK 调用 | 4 处 | `rerankerAPI.py`、`retrieve.py`、`vision_service.py`、`pubmed_service.py` |
| 手写 JSON/文本输出解析 | 3 处 | `qwen_agent.py`、`context_summary.py` |
| 手写状态机/流程编排 | 1 套 | `qwen_agent.py`（`SimpleGraph` + `_run_clinical_reasoning_core`） |

---

## 2. 迁移清单

| 序号 | 文件路径 | 行号范围 | 当前实现方式（手搓） | 建议替换为（LangChain 组件） | 迁移难度 | 优先级 | 备注 |
|------|----------|----------|----------------------|------------------------------|----------|--------|------|
| 1 | `qwen_agent.py` | 121–177 | 自实现 `SimpleGraph` / `_CompiledGraph` 状态机 | `langgraph.graph.StateGraph` | 高 | P1 | 项目已有结构最接近 LangGraph 设计，是最值得迁移的部分；但迁移量大 |
| 2 | `qwen_agent.py` | 388–557 | 手动串联 6 节点推理管线（`_node_analysis → _node_retrieve → _node_reason → stream_final_report`） | LangGraph `StateGraph` 节点 + 条件路由 | 高 | P1 | 与序号 1 同属一次迁移；拆分并行节点可利用 LangGraph 原生并行 |
| 3 | `qwen_agent.py` | 228–251 | 手写 `_parse_json`（3 层 fallback：直接解析→markdown→括号提取） | `JsonOutputParser` 或 `PydanticOutputParser` | 低 | P1 | 现有逻辑已相当健壮；迁移后可统一错误处理风格 |
| 4 | `context_summary.py` | 19–39 | 手写 `parse_score_response`（正则提取浮点数） | `PydanticOutputParser`（Score schema） | 低 | P1 | 代码量小，迁移成本极低 |
| 5 | `qwen_agent.py` | 1141–1164 | 手写 `_parse_answer_letters`（正则提取选项字母） | `PydanticOutputParser`（MCQAnswer schema） | 低 | P2 | 当前实现含较多领域特殊处理（单选补C逻辑），迁移时需保留业务规则 |
| 6 | `qwen_agent.py` | 25–52, 299–313, 448–456, 702–729, 740–762, 780–798, 883–898, 940–965, 999–1018, 1040–1059, 1084–1108, 1120–1131, 1174–1186 | 13 处散落的硬编码 f-string Prompt | `ChatPromptTemplate.from_messages()` + 变量注入 | 中 | P1 | 部分 Prompt 已通过 `prompts.yaml` 管理，其余需补充；建议全部迁入 YAML 再套 `ChatPromptTemplate` |
| 7 | `vision_service.py` | 166–213 | 3 处硬编码系统 Prompt（`_DEFAULT_REPORT_SYSTEM` 等） | `ChatPromptTemplate` + YAML 外置 | 中 | P2 | 视觉模型用 dashscope 原生 SDK，暂无 LangChain 多模态支持，Prompt 管理可独立迁移 |
| 8 | `context_summary.py` | 61–79, 110–127 | 2 处硬编码 Prompt（价值评估、摘要合并） | `ChatPromptTemplate` + YAML 外置 | 低 | P2 | 文件较独立，迁移不影响主链路 |
| 9 | `medical_agent.py` | 18–27 | 2 处硬编码 fallback Prompt（`_FALLBACK_SEARCH_PROMPT` 等） | 统一纳入 `prompts.yaml` + `PromptManager` | 低 | P2 | 已有 PromptManager 机制，只需补 key 即可 |
| 10 | `qwen_agent.py` | 197–199, 263–273 | 手写工具字典 + `_run_tool` 分发逻辑 | `@tool` 装饰器 + `ToolNode`（LangGraph） | 中 | P2 | 目前工具只有 `retrieve_evidence` 一个，迁移价值有限；等 Agent 架构重构时一并处理 |
| 11 | `main.py` | 329–345 | 手动调用 `context_summary.update_all_info` 管理对话摘要 | `ConversationSummaryBufferMemory` 或自定义 `BaseMemory` | 中 | P2 | 当前 `all_info` 机制含价值阈值筛选逻辑，LangChain Memory 接口无此语义，需包装 |
| 12 | `rerankerAPI.py` | 52–55 | `requests.post` 直接调用 DashScope Rerank REST API | `langchain_community` 中的 `DashScopeRerank` 或封装为 `BaseDocumentCompressor` | 中 | P2 | 官方 `langchain-community` 已有 DashScope Rerank 支持，需确认版本兼容性 |
| 13 | `retrieve.py` | 105–112 | `dashscope.TextReRank.call()` 原生 SDK 调用 | 同序号 12，统一为 LangChain `ContextualCompressionRetriever` | 中 | P2 | 与序号 12 是同功能的两套实现，整合时可二选一 |
| 14 | `vision_service.py` | 87–93 | `dashscope.MultiModalConversation.call()` 调用 Qwen VL | 暂无合适 LangChain 封装 | 高 | P2（**不建议**） | 详见第 4 节 |
| 15 | `services/pubmed_service.py` | 104–108, 121–124 | `httpx` 直接调用 PubMed API | 封装为 LangChain `BaseTool` 或 `BaseRetriever` | 低 | P2 | 逻辑清晰，封装价值在于统一接口，非 Bug 修复 |
| 16 | `qwen_agent.py` | 874–934 | 函数内部临时实例化 `ChatTongyi`（每次调用都 new 一个） | 复用已有 `llm_proposer`/`llm_critic` 实例，或提取为模块级单例 | 低 | **P0** | **当前有缺陷**：每次 `/ai/analyze` 请求都创建新 LLM 实例，浪费连接资源，需尽快修复 |

---

## 3. 迁移建议与风险提示

### 3.1 建议迁移顺序

```
P0 先修（与 LangChain 无关的缺陷）
└─ 序号 16：qwen_agent.py:874 临时 LLM 实例改为复用

第一批（低风险、高回报）
├─ 序号 3：_parse_json → JsonOutputParser
├─ 序号 4：parse_score_response → PydanticOutputParser
└─ 序号 9：medical_agent.py fallback Prompt → prompts.yaml

第二批（Prompt 集中管理）
├─ 序号 6：qwen_agent.py 13 处硬编码 Prompt → ChatPromptTemplate + YAML
├─ 序号 8：context_summary.py Prompt → YAML
└─ 序号 7：vision_service.py Prompt → YAML（仅 Prompt 部分，不动 SDK 调用）

第三批（架构重构，工作量最大）
├─ 序号 1+2 合并：SimpleGraph + 推理管线 → LangGraph StateGraph
│   ├─ 需同步处理序号 10（Tool 规范化）
│   └─ 需保留 TokenAggregator 心跳机制（LangGraph 无此概念）
└─ 序号 11：all_info 对话摘要 → 自定义 BaseMemory

第四批（外部接口规范化）
├─ 序号 12+13 合并：Rerank → LangChain ContextualCompressionRetriever
└─ 序号 15：PubMed → BaseTool
```

### 3.2 兼容性风险

**风险 1：LangChain 版本跨度大（最高风险）**

- 当前锁定 `langchain==0.1.20` / `langchain-community==0.0.38`，已落后约 3 个大版本
- LangGraph 需要 `langchain>=0.2`，迁移前**必须先升级 LangChain**
- `ChatTongyi` 在新版本中已移至 `langchain-community`，接口有变动
- 建议：升级前在隔离环境做完整回归测试

**风险 2：SSE 流式输出与 Java 中间件的衔接**

- `main.py:244–262` 的 `asyncio.wait + pending_task` 心跳机制是专门为保活 Java WebClient 连接设计的
- LangGraph 的 `astream_events` 接口**不直接支持**超时心跳注入
- 迁移序号 1+2 时，需在 LangGraph 执行层外面保留现有的 `generate()` 包装层，只把内部节点逻辑迁入 LangGraph

**风险 3：`TokenAggregator` 聚合机制**

- `token_aggregator.py` 对高频 thinking token 做了批量合并，降低 SSE 事件频率
- 迁移到 LangGraph `astream_events` 后，事件颗粒度由框架控制，需重新适配

**风险 4：Prompt 变量格式不兼容**

- 现有 `prompts.yaml` 使用 Python `.format()` 语法（`{variable}`）
- `ChatPromptTemplate` 使用相同语法，**兼容**
- 但需注意：Prompt 中含花括号的 JSON 示例需转义为 `{{` / `}}`

### 3.3 需新增的依赖包

```
langgraph>=0.2.0           # 替换 SimpleGraph
langchain>=0.2.0            # 升级（当前 0.1.20）
langchain-community>=0.2.0  # 升级（当前 0.0.38）
langchain-core>=0.2.0       # 显式声明
```

---

## 4. 不建议迁移的部分

| 项目 | 文件 | 原因 |
|------|------|------|
| **Qwen VL 多模态调用** | `vision_service.py:87-93` | LangChain 对 Qwen VL 的多模态（图片+文字混合 messages）支持不完整，`dashscope.MultiModalConversation` 的 `incremental_output=True` 流式参数在 LangChain 包装中无对应实现，强行迁移会丢失流式能力 |
| **PubMed httpx 调用** | `services/pubmed_service.py` | PubMed 是外部数据源而非 LLM，封装为 `BaseTool` 有一定规范价值，但功能上无任何收益；当前 `httpx` 异步实现已足够规范，不值得为了"统一"而迁移 |
| **`all_info` 对话摘要机制** | `main.py:329-345` + `context_summary.py` | 当前实现有"按价值阈值（0.4）决定是否写入"的筛选逻辑，这是领域特有设计；LangChain `ConversationSummaryBufferMemory` 无此语义，迁移需要完整重写，且**没有功能收益**，只是改了调用方式 |
| **BM25 + Chroma 混合检索器的合并逻辑** | `makeData/retrieve.py` | 已使用 LangChain 的 `BM25Retriever` 和 `Chroma`，整体框架已经规范；混合检索的合并/去重逻辑属于业务逻辑，不应交给框架管理 |

---

## 附录：依赖版本快照

```
# 当前锁定版本（requirements.txt）
langchain==0.1.20
langchain-community==0.0.38
langchain-chroma==0.1.4
langchain-openai==0.1.7
chromadb==0.5.23
dashscope==1.25.9
openai==1.109.1
transformers==4.38.2
sentence-transformers==2.7.0
torch==2.1.0
rank_bm25==0.2.2
```
