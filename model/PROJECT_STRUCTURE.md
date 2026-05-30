# Neuro-Multi-Agent 项目架构与代码文件说明

经过近期的多智能体架构升级、混合特征抽取的检索增强体系（Dual-RAG）重构以及模块化分类，整个项目已完成高度解耦。以下为全项目系统文件所承担的**功能角色说明文档**（包含各个文件的核心类、函数及其相互联系联系）。

---

## 1. 全局入口与服务层

*   **`app/main.py`**
    *   **作用**：FastAPI 后端服务器入口点。负责注册核心 API 路由、加载中间件，并提供流式输出等外网对接能力。
    *   **核心类/函数**：
        *   `init_all_resources()`: 生命周期事件，统一触发模型、向量库、服务的预热与启动。
        *   `verify_token()`: 权限校验钩子确保接口防刷。
        *   `QueryRequest`, `AnalyzeRequest`: Pydantic 数据规范类，定义 HTTP 通讯结构。
    *   **模块联系**：串联起了 `clinical_graph.py` 的推理启动，并初始化底层的 `UnifiedSearchEngine` 与 `PubMedService`。

*   **`.env` / `requirements.txt` / `README.md`** 
    *   基础配置控制、第三方依赖以及说明文件。

---

## 2. RAG (混合检索生成系统) - `app/rag/`

提供系统最底层的“医学知识补全”功能。此模块向大模型输出医学权威上下文。

*   **`data_loader.py`**
    *   **作用**：文档解析与分块管道管理。
    *   **核心函数**：
        *   `load_pdfs_from_dir()`: 扫描并加载文件夹内的 PDF 内容。
        *   `clean_text()`, `split_documents()`: 数据预处理清洗，基于长度和符号对原始文本进行精细的 Chunk 分割。
*   **`qa_generator.py`**
    *   **作用**：调用 LLM 实现文档纯文本块的逆向提问提取。
    *   **核心类**：`QAGenerator`
        *   **核心方法** `generate_qa_for_chunks()`: 批量向大模型请求生成 QA 对，与原文本一并建立双视角检索索引。
*   **`retrievers.py`**
    *   **作用**：定义向量化模型、混合检索引擎及重排逻辑。
    *   **核心类/函数**：
        *   `DashScopeEmbeddings`: 封装阿里云文本嵌入 API，提供 `embed_documents` 与 `embed_query`。
        *   `BGEReranker`: 二次精排模型，`rerank()` 将召回候选集二次打分提纯。
        *   `HybridRetriever`: `search()` 综合融合了基于关键词的 BM25 和基于向量比对的过滤检索机制。
        *   `UnifiedSearchEngine`: 面向业务封装的高度集成接口。
    *   **模块联系**：此模块的数据流入大模型上下文（供给给 `retrieve_node.py`或`MedicalReActAgent`作为循证支持）。

---

## 3. Agents 多智能体决策层 - `app/agents/`

这是采用 LangGraph 构建的高维认知推理中枢系统。

*   **`orchestrators/` (核心决策编排网络)**
    *   **`clinical_graph.py`**:
        *   **核心类**：`ClinicalGraphBuilder` 
        *   **作用**：利用 `build()` 组装 LangGraph 图机制；`_route_intent()` 动态路由患者病情的节点走向。
    *   **`qwen_agent.py`**: 
        *   **核心类**：`QwenAgent`。封装 LangGraph 事件解析的方法，如 `_translate_event()` 流水转换机制和输出 `_parse_json()`。
    *   **`nodes/` (行为节点)**: 相互串发、接驳完成一套复杂的看诊流水线。
        *   `intent_node.py` (`IntentNode`): 首道大门，负责区分（咨询/闲聊百科/非脑卒中拒答）。
        *   `analysis_node.py` (`AnalysisNode`): 病例结构化专家，自动提取“现病史、既往史”，剥离“治疗”还是“诊断”微目标。
        *   `retrieve_node.py` (`RetrieveNode`): 接力器，发起 RAG 质询。
        *   `reason_node.py` (`ReasonNode`): Proposer-Critic(提议-批判) 模拟会诊，内部互相打架验证医疗安全。
        *   `report_node.py` (`ReportNode`): 最终排版并执行临床意见输出。

*   **`qwen/` (独立专业大语言模型层)**
    *   **`medical_agent.py`** (`MedicalReActAgent`):
        *   **作用核心方法**：`run()`, `fast_retrieve()`, `_synthesize_evidence()`。用于单独承接医疗术语推断处理的小型闭环环境。

*   **`bailian/`**
    *   **`health_risk_analyzer.py`**: 调用阿里云百炼大模型进行即态健康风险评测分析（极速版）。

*   **`pipelines/` (管道式执行器)**
    *   **`rag_pipeline.py`** (`RAGPipeline.run()`): 标准化串行控制。

---

## 4. 全局辅助工具与第三方整合服务

*   **`app/services/` (外部数据接驳)**
    *   **`pubmed_service.py`** (`PubMedService`):
        *   **方法**：`_common_params()`, `_parse_article()`, `_evidence_rank()` 分布执行查询组装、XML抽提以及论文权威性影响因子粗排，获取全球临床论文库支持。
*   **`app/config/` (中央配置库)**
    *   **`config_loader.py`**:
        *   `PromptManager` / `ReportTemplateManager`: 各自拥有 `get()`, `reload()`, `get_template()`方法，实现大段 Prompt 文字和 Markdown 报告渲染模板的内存预载与变量替代管理。避免了修改文案又要重启代码的麻烦。
*   **`app/utils/` (公共函数安全与限流)**
    *   `error_codes.py` (统一错误处理映射)。
    *   `context_summary.py` (包含上下文截断滑动窗，防 Token 超限)。

---

## 5. 常量数据集与产出目录（纯文件落盘区）

*   **`Data/documents/`**: PDF 原始文献资源池。
*   **`app/chroma_db_unified/`**: 引擎底座持久化的向量特征数据库。
*   **`data_exports/`**: 埋点生成的交互记录 CSV 文件。

---

## 6. 测试与科学评估体系

*   **`tests/`**: 用于测试核心微服务与验证（如 `test_rag.py` 单测 RAG 的切片分型；`test_api_client.py` 模拟前端 HTTP 访问联通性能）。
*   **`evaluation/`**: 自动化打分脚手架跑批模块脚本，用于医学常识标准集下，测试模型的幻觉程度。
