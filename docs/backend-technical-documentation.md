# 神经多智能体系统 — 后端技术文档

> **版本**: v1.0  
> **日期**: 2026-07-05  
> **适用范围**: 后端 Java 服务 + Python AI 模型层  
> **领域**: 神经内科/脑卒中临床决策支持系统 (CDSS)

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术栈总览](#2-技术栈总览)
3. [架构设计](#3-架构设计)
4. [Java 后端服务](#4-java-后端服务)
5. [Python AI 模型层](#5-python-ai-模型层)
6. [数据库设计](#6-数据库设计)
7. [API 接口规范](#7-api-接口规范)
8. [SSE 实时流式通信](#8-sse-实时流式通信)
9. [安全体系](#9-安全体系)
10. [配置管理](#10-配置管理)
11. [限流与熔断](#11-限流与熔断)
12. [部署架构](#12-部署架构)
13. [核心业务流程](#13-核心业务流程)
14. [错误码体系](#14-错误码体系)
15. [附录](#15-附录)

---

## 1. 系统概述

### 1.1 项目定位

**神经多智能体系统 (Neuro Multi-Agent System)** 是一个面向神经内科/脑卒中领域的**临床决策支持系统 (CDSS)**。系统通过多智能体协作的 AI 推理引擎，结合循证医学证据检索 (RAG)，为医生提供专业的临床推理、风险评估和诊疗建议。

### 1.2 核心能力

| 能力 | 描述 |
|------|------|
| **多轮临床问诊** | SSE 流式对话，支持图文混合输入，上下文持久化 |
| **多智能体推理** | LangGraph 编排 3 位专家（全科/神经专科/药师）并行推理 + 综合 |
| **循证医学检索** | 基于 ChromaDB 向量数据库 + 本地脑卒中指南文档库的 RAG 检索 |
| **双层安全校验** | 规则引擎（禁忌症匹配）+ LLM 批判反思（最多 3 次迭代） |
| **健康风险分析** | 异步非流式风险评估，支持健康数据与医患对话同步 |
| **影像识别** | 支持检验报告单 / 药品包装图片的 OCR 识别与专业解读 |
| **PubMed 检索** | 代理 PubMed 文献检索，辅助循证决策 |
| **患者管理** | 患者信息 CRUD，关联 AI 分析意见 |

### 1.3 系统边界

```
┌──────────────────────────────────────────────────────────────┐
│                      前端 (Vue 3 + Vite)                      │
│                    http://localhost:5173                      │
└────────────┬──────────────────────────────┬──────────────────┘
             │  REST + SSE (Axios/fetch)    │
             ▼                              ▼
┌────────────────────────┐    ┌────────────────────────────────┐
│  Java 后端 (Spring Boot)│◄──►│  Python AI 模型层 (FastAPI)     │
│  http://localhost:8080  │JWT │  http://localhost:8000          │
│                        │    │                                 │
│  ┌──────────────────┐  │    │  ┌───────────────────────────┐  │
│  │ 用户认证/患者管理 │  │    │  │ LangGraph 临床推理编排      │  │
│  │ SSE 流代理/缓存   │  │    │  │ RAG 向量检索引擎           │  │
│  │ 限流/熔断/会话管理│  │    │  │ 多专家并行推理             │  │
│  └──────────────────┘  │    │  │ 规则+LLM 双层校验          │  │
└────────┬───────────────┘    │  └───────────────────────────┘  │
         │                     │              │                   │
         ▼                     │              ▼                   │
┌─────────────────┐           │  ┌────────────────────────────┐  │
│  MySQL 8 (medai) │           │  │ ChromaDB 向量数据库         │  │
│  Redis           │           │  │ 阿里云 DashScope (Qwen)    │  │
│  阿里云 OSS      │           │  │ PubMed API                 │  │
└─────────────────┘           │  └────────────────────────────┘  │
                              └────────────────────────────────┘
```

---

## 2. 技术栈总览

### 2.1 Java 后端

| 类别 | 技术 | 版本 |
|------|------|------|
| 语言 | Java | 21 |
| 框架 | Spring Boot | 3.3.13 |
| 构建 | Maven | — |
| ORM | MyBatis-Plus | 3.5.5 |
| 数据库驱动 | MySQL Connector/J | — |
| 缓存 | Spring Data Redis + Redisson | 3.27.2 |
| 安全 | Spring Security + JJWT | 0.9.1 |
| 响应式 HTTP | Spring WebFlux (WebClient) | — |
| 对象存储 | Aliyun OSS SDK | 3.17.4 |
| 工具库 | Hutool | 5.8.16 |
| 简化代码 | Lombok | — |
| HTTP 客户端 | Apache HttpClient 5 | — |

### 2.2 Python AI 模型层

| 类别 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.11+ |
| Web 框架 | FastAPI | 0.128.0 |
| 服务器 | Uvicorn | 0.40.0 |
| LLM 编排 | LangGraph | 0.2.20 |
| LLM 调用 | LangChain + langchain-openai | 0.2.x |
| LLM 后端 | 阿里云 DashScope (Qwen-Max/Plus/Turbo) | — |
| 向量数据库 | ChromaDB | 0.5.23 |
| 嵌入模型 | Sentence Transformers (HuggingFace) | — |
| SSE 流 | sse-starlette | 2.1.3 |
| PDF 解析 | pdfplumber, PyPDF, pdfminer | — |
| 数据校验 | Pydantic | — |
| HTTP 请求 | httpx, requests | — |

---

## 3. 架构设计

### 3.1 整体架构

系统采用 **三层分离** 架构：

- **接入层 (Java)**: 用户认证、业务 CRUD、SSE 流代理与缓存、限流熔断
- **推理层 (Python)**: AI 临床推理、RAG 检索、多智能体协作
- **数据层**: MySQL（业务数据）、Redis（会话/缓存）、ChromaDB（向量知识库）、OSS（文件存储）

### 3.2 服务间通信

```
前端 ←→ Java 后端:     REST (JSON) + SSE (text/event-stream)
Java 后端 ←→ Python:  HTTP/1.1 (JWT 鉴权, WebClient 非阻塞调用)
Python ←→ LLM:       HTTPS (DashScope API, OpenAI 兼容协议)
Python ←→ ChromaDB:  本地文件系统 (持久化向量索引)
Java ←→ MySQL:       JDBC (HikariCP 连接池)
Java ←→ Redis:       Lettuce (响应式 Redis 客户端)
```

### 3.3 关键设计决策

| 决策 | 理由 |
|------|------|
| Java 做接入层, Python 做推理层 | 利用 Spring Boot 成熟的企业级能力（安全/事务/连接池）+ Python AI 生态优势 |
| SSE 代替 WebSocket | 单向推送场景（AI 流式输出）更简单；天然支持 HTTP 重连与 `Last-Event-ID` 协议 |
| MyBatis-Plus 代替 JPA | 复杂查询灵活；团队更熟悉 SQL |
| Redisson 实现分布式限流 | 基于 Redis 的原子操作，支持多实例部署 |
| 共享 JWT Secret 做服务间认证 | 轻量级；无需独立认证中心 |
| ChromaDB 本地部署 | 数据量可控（12 篇指南文档）；降低运维复杂度 |
| LangGraph 编排多智能体 | 有向图天然映射临床推理流程；支持条件路由、循环、状态持久化 |

---

## 4. Java 后端服务

### 4.1 项目结构

```
backend/ai/MyServer/src/main/java/com/it/
├── MyServerApplication.java          # Spring Boot 启动类
├── cache/
│   └── SSEEventCache.java            # SSE 断线续传事件缓存
├── config/
│   ├── SecurityConfig.java           # Spring Security 配置
│   ├── CorsConfig.java               # CORS 跨域配置
│   ├── RedisConfig.java              # Redis 序列化配置
│   ├── RedissonConfig.java           # Redisson 分布式锁/限流配置
│   ├── WebMvcConfig.java             # MVC 拦截器注册
│   ├── MyBatisPlusConfig.java        # MyBatis-Plus 分页插件
│   └── OSSConfig.java                # 阿里云 OSS 客户端配置
├── controller/
│   ├── LoginController.java          # 登录/注册
│   ├── QuesController.java           # AI 流式问答（SSE）
│   ├── AiController.java             # AI 分析接口
│   ├── PatientController.java        # 患者 CRUD
│   ├── DocumentController.java       # OSS 文档管理
│   ├── LearningMaterialController.java # 学习材料
│   ├── PubMedController.java         # PubMed 代理
│   ├── InitialPageController.java    # 聊天列表
│   ├── ChangeKeyController.java      # 个人信息修改
│   ├── UploadController.java         # 文件上传
│   └── MonitorController.java        # 限流监控
├── handler/
│   └── GlobalExceptionHandler.java   # 全局异常处理
├── interceptor/
│   ├── RefreshTokenInterceptor.java  # JWT 刷新拦截器 (order=0)
│   └── Tokeninterceptor.java         # 鉴权拦截器 (order=1)
├── mapper/                           # MyBatis-Plus Mapper 接口
│   ├── UserMapper.java
│   ├── TalkMapper.java
│   ├── ContMapper.java
│   ├── PatientMapper.java
│   ├── AiOpinionMapper.java
│   ├── HealthDataMapper.java
│   ├── LearningMaterialMapper.java
│   └── ChangeKeyMapper.java
├── po/                               # 数据传输对象 (DTO)
│   ├── dto/UserDTO.java              # 线程本地用户信息
│   ├── Req/QuesRequest.java          # 请求体
│   └── Resp/Result.java              # 统一响应体
├── pojo/                             # 数据库实体 (Entity)
│   ├── User.java
│   ├── Talk.java
│   ├── Cont.java
│   ├── Patient.java
│   ├── AiOpinion.java
│   ├── HealthData.java
│   ├── LearningMaterial.java
│   └── ChangeKey.java
├── service/
│   ├── LoginService.java             # 登录逻辑
│   ├── RegiService.java              # 注册逻辑
│   ├── AIStreamingService.java       # ★ 核心：SSE 流式对话服务
│   ├── AiAnalysisService.java        # AI 分析（含熔断/限流/重试）
│   ├── PatientService.java           # 患者管理
│   ├── ContService.java              # 对话内容
│   ├── TalkService.java              # 对话会话
│   ├── InitialPageService.java       # 首页列表
│   ├── ChangeKeyService.java         # 信息修改
│   ├── OssDocumentService.java       # OSS 文档
│   ├── LearningMaterialService.java  # 学习材料
│   └── ConversationPersistenceService.java  # 对话持久化
└── utils/
    ├── JWT.java                      # JWT 工具类
    ├── ThreadLocalUtil.java          # ThreadLocal 工具
    ├── AliOssUpload.java             # OSS 上传工具
    └── IpUtil.java                   # IP 提取工具
```

### 4.2 核心服务详解

#### 4.2.1 AIStreamingService（SSE 流式对话服务）

这是系统的**核心服务**，负责整个 AI 对话流程的编排：

```
请求进入
  │
  ├─ 1. 创建/验证 Talk（对话会话）
  ├─ 2. 注册 SSE 缓存 (SSEEventCache.registerStream)
  ├─ 3. 构建 SSE 事件流 (SseEmitter / Flux)
  │     │
  │     ├─ 3a. 发送 init 事件 (talkId)
  │     ├─ 3b. 发送 resume 事件 (历史上下文回放，多轮对话)
  │     │
  │     ├─ 3c. 调用 Python /model/get_result (WebClient)
  │     │      │
  │     │      └─ 事件映射:
  │     │           Python token    → 前端 chunk
  │     │           Python thinking → 前端 thinking
  │     │           Python done     → 前端 done (含 name, all_info)
  │     │           Python error    → 前端 error (含 code, retryable)
  │     │
  │     ├─ 3d. 每条事件写入 SSEEventCache (seq 分配)
  │     │
  │     └─ 3e. 流结束后:
  │            - completeStream (标记过期时间)
  │            - 异步持久化对话到 cont 表
  │            - 更新 talk 标题
  │
  └─ 4. 断线重连处理:
        读取 Last-Event-ID → SSEEventCache.getReplayStream
        → 回放丢失事件 + 续接直播
```

**事件序列号格式**: `{talkId}:{seq}`，其中 seq 从 1 单调递增，最大 200（环形缓冲区）。

#### 4.2.2 AiAnalysisService（AI 分析服务）

处理非流式 AI 分析请求，包含完善的弹性机制：

| 机制 | 配置 | 说明 |
|------|------|------|
| 信号量限流 | 20 permits | 最大并发分析数 |
| 熔断器 | Resilience4j | 50% 失败率 → 开路 10s |
| 超时控制 | WebClient 超时 | 连接 10s，读取 600s |
| 重试 | 指数退避 | 最多 3 次（仅可重试错误） |

#### 4.2.3 SSEEventCache（断线续传缓存）

基于 Project Reactor 的 `Sinks.Many` 实现：

```
数据结构:
  ConcurrentHashMap<String, Sinks.Many<SequencedEvent>>  sinks
  ConcurrentHashMap<String, AtomicLong>                   seqCounters
  ConcurrentHashMap<String, Long>                         expiryTimes

生命周期:
  注册(registerStream) → 追加事件(addEvent) → 完成(completeStream)
                                                     │
                                                     ▼
                                            TTL 5分钟后清理(cleanExpired)
  清理定时任务: 每 60 秒执行一次
```

**容量限制**: 每个 talkId 最多缓存 200 条事件（`ringBufferSize`），超出后最旧事件被挤出。单条事件超过 200KB 时跳过缓存。

### 4.3 中间件与拦截器链

```
请求 → [CORS Filter] → [RefreshTokenInterceptor (order=0)]
                            │
                            ├─ 从 Header 提取 Token ("token" 或 "Authorization: Bearer xxx")
                            ├─ 解析 JWT，提取 userId + jti
                            ├─ 验证 Redis 中 jti 一致性（单点登录强制）
                            ├─ 从 Redis 恢复 UserDTO → ThreadLocal
                            ├─ 刷新 Redis TTL（30 分钟滑动过期）
                            └─ 失败则返回 401
                            │
                       [TokenInterceptor (order=1)]
                            │
                            ├─ 检查 ThreadLocal 是否有用户
                            ├─ 记录客户端 IP
                            └─ 未认证返回 401
                            │
                       [Controller]
                            │
                       [GlobalExceptionHandler]
```

**单点登录机制**: 每次登录生成唯一 `jti`，存储在 Redis `login:user:{userId}` 中。新登录会覆盖旧 jti，旧 Token 立即失效。

### 4.4 统一响应格式

```json
{
  "code": 200,
  "msg": "success",
  "data": { }
}
```

分页响应额外包含 `total`、`page`、`pageSize` 字段。

---

## 5. Python AI 模型层

### 5.1 项目结构

```
model/
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py                              # FastAPI 入口 (lifespan 资源管理)
│   ├── agents/
│   │   ├── assistant.py                     # MedicalAssistant 门面
│   │   ├── constants.py                     # 常量定义
│   │   ├── core/
│   │   │   ├── schema.py                    # ClinicalState, ClinicalContext (TypedDict/Pydantic)
│   │   │   ├── exceptions.py                # 自定义异常
│   │   │   ├── results.py                   # 结果封装
│   │   │   └── decorators.py                # 工具装饰器
│   │   ├── infra/
│   │   │   └── reranker.py                  # BGE 重排序器
│   │   ├── orchestrators/
│   │   │   ├── clinical_graph.py            # ★ LangGraph 临床推理图构建器
│   │   │   ├── qwen_agent.py                # Qwen Agent 编排器（节点运行器）
│   │   │   └── nodes/
│   │   │       ├── base.py                  # 基础节点类
│   │   │       ├── intent_node.py           # 意图识别节点
│   │   │       ├── analysis_node.py         # 病例分析节点
│   │   │       ├── retrieve_node.py         # 证据检索节点
│   │   │       ├── reason_node.py           # ★ 多专家推理节点（并行）
│   │   │       ├── validate_node.py         # 双层校验节点
│   │   │       └── report_node.py           # 报告生成节点
│   │   ├── pipelines/
│   │   │   └── rag_pipeline.py              # RAG 管道封装
│   │   ├── schemas/
│   │   │   └── retrieval.py                 # 检索相关数据模型
│   │   ├── services/
│   │   │   ├── query_generation.py          # 检索查询生成
│   │   │   ├── retrieval.py                 # 检索执行
│   │   │   └── synthesis.py                 # 证据综合
│   │   ├── utils/
│   │   │   ├── json_parser.py               # JSON 解析器
│   │   │   ├── llm_helper.py                # LLM 调用辅助
│   │   │   ├── retry.py                     # 重试装饰器
│   │   │   └── text_utils.py                # 文本处理
│   │   └── bailian/                         # 百炼 Agent（健康风险分析）
│   ├── config/
│   │   ├── config_loader.py                 # YAML 配置加载器（支持热更新）
│   │   ├── prompts.yaml                     # ★ 所有 LLM Prompt 模板（~380行）
│   │   ├── expert_config.yaml               # 专家角色定义
│   │   ├── report_templates.yaml            # 5 种报告模板
│   │   ├── limits_config.yaml               # 参数限制配置
│   │   └── rules_config.yaml                # 禁忌症校验规则
│   ├── rag/
│   │   ├── data_loader.py                   # PDF 加载 + 文本分割
│   │   ├── qa_generator.py                  # QA 对生成
│   │   ├── retrieve.py                      # ★ 统一检索引擎
│   │   └── retrievers.py                    # 嵌入模型 + 向量库 + 混合检索
│   ├── services/
│   │   ├── pubmed_service.py                # PubMed 检索服务
│   │   └── vision_service.py                # ★ 影像识别服务（多模态）
│   └── utils/
│       ├── context_summary.py               # 上下文摘要服务
│       ├── download_models.py               # 模型下载工具
│       ├── error_codes.py                   # 错误码定义
│       ├── naming_model.py                  # 对话命名模型
│       └── token_aggregator.py              # Token 聚合器
└── data/documents/                          # 12 篇脑卒中指南 PDF
```

### 5.2 资源初始化流程 (Lifespan)

```
FastAPI 启动
  │
  ├─ [1/7] 加载 5 个配置管理器 (YAML → 内存)
  │       - Prompt 管理器: 10+ 模板
  │       - 报告管理器: 5 种报告模式
  │       - 专家管理器: 3 位专家 (全科/神经专科/药师)
  │       - 校验管理器: 3 类禁忌症规则 + 反射配置
  │       - 参数限制管理器: 字数/数量上限
  │
  ├─ [2/7] 初始化 3 个 Qwen 模型实例
  │       - qwen-max:    复杂推理 (Proposer, Report)
  │       - qwen-plus:   分析/校验 (Critic, Analysis, Retrieval)
  │       - qwen-turbo:  快速任务 (Intent, QuickAnalyze, Summary, HealthRisk)
  │
  ├─ [3/7] 初始化上下文摘要服务 (ConversationSummaryService)
  ├─ [4/7] 初始化向量检索引擎 (UnifiedSearchEngine + ChromaDB)
  ├─ [5/7] 初始化医疗助手 (MedicalAssistant)
  ├─ [6/7] 初始化临床推理智能体 (QwenAgent + LangGraph 编译)
  └─ [7/7] 初始化视觉识别服务 + 命名模型
```

### 5.3 LangGraph 临床推理图

#### 5.3.1 图拓扑

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  intent │  意图分类
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         irrelevant  knowledge  consultation
              │          │          │
         ┌────▼────┐ ┌──▼────────┐ ┌▼──────────┐
         │ reject  │ │knowledge  │ │ analysis   │  结构化病例分析
         └────┬────┘ │_answer    │ └─────┬──────┘
              │      └────┬──────┘       │
              │           │              ▼
              │           │      ┌──────────────┐
              │           │      │   retrieve   │  RAG 证据检索
              │           │      └──────┬───────┘
              │           │             │
              │           │             ▼
              │           │      ┌──────────────┐
              │           │      │   reason     │  3 专家并行推理 → 综合
              │           │      └──────┬───────┘
              │           │             │
              │           │             ▼
              │           │      ┌──────────────┐
              │           │      │  validate    │  规则引擎 + LLM 反思
              │           │      └──────┬───────┘
              │           │             │
              │           │    ┌────────┼────────┐
              │           │    │        │        │
              │           │  pass    retry     fail
              │           │    │    (≤3次)      │
              │           │    │        │        │
              │           │    │   ┌────▼───┐    │
              │           │    │   │ reason  │    │
              │           │    │   └────────┘    │
              │           │    │                 │
              │           │    ▼                 ▼
              │           │  ┌──────────────────────┐
              │           │  │   generate_report    │
              │           │  └──────────┬───────────┘
              │           │             │
              ▼           ▼             ▼
            ┌─────────────────────────────┐
            │            END              │
            └─────────────────────────────┘
```

#### 5.3.2 各节点职责

| 节点 | LLM | 输入 | 输出 | 耗时(估) |
|------|-----|------|------|---------|
| **intent** | qwen-turbo | 用户原始输入 | `intent_type`: consultation/knowledge/irrelevant | ~1s |
| **analysis** | qwen-plus | case_text + all_info | 结构化 ClinicalContext + clinical_questions[] | ~5s |
| **retrieve** | qwen-plus | clinical_questions | 向量检索 + 重排序后的 evidence | ~3s |
| **reason** | qwen-max × 3 (并行) | context + evidence | 3 专家意见 → 综合 Proposal + Critique | ~20s |
| **validate** | 规则引擎 + qwen-plus | proposal + evidence | validation_passed + feedback | ~8s |
| **report** | qwen-max | context + evidence + proposal + critique | 最终报告 (按 report_mode 模板) | ~15s |

#### 5.3.3 多专家并行推理 (ReasonNode)

```python
# 推理流程
全科医生 (qwen-max)  ─┐
神经专科医生 (qwen-max) ─┼─ asyncio.gather ─► 意见综合 (qwen-max)
临床药师 (qwen-max)    ─┘                        │
                                          ┌─────┴──────┐
                                          │  PROPOSAL   │
                                          │  CRITIQUE   │
                                          └────────────┘
```

每位专家使用独立的系统提示词（来自 `expert_config.yaml`），并行调用后由主治医师角色综合为统一提案。

#### 5.3.4 反思循环 (Validate → Retry)

```
reason → validate:
  │
  ├─ 规则引擎检查（规则来自 rules_config.yaml）:
  │    - 溶栓禁忌: 近期大手术/活动性出血/血小板<100/血压>180:110/CT高密度
  │    - 抗凝禁忌: 出血倾向/活动性溃疡
  │    - 双抗禁忌: 既往脑出血史
  │
  ├─ LLM 批判反思 (qwen-plus, 8 维度审查):
  │    1. 诊断逻辑  2. 鉴别诊断  3. 时间窗判断  4. 多系统风险
  │    5. 治疗安全性 6. 证据匹配度 7. 表述安全性 8. 致命遗漏
  │
  └─ 路由决策:
       validation_passed = true  → pass → generate_report
       validation_passed = false → retry → reason (最多 3 次)
       超过 3 次                 → fail → generate_report (附警告)
```

### 5.4 RAG 检索引擎

#### 5.4.1 检索引擎架构

```
PDF 文档预处理 (离线):
  data/documents/*.pdf
    → pdfplumber/PyPDF 文本提取
    → RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
    → Sentence Transformers 向量化
    → ChromaDB 持久化 (./chroma_db_unified)

在线检索 (实时):
  用户问题
    → QueryGeneration (qwen-plus, 生成精准检索关键词)
    → HybridRetriever: 向量检索 (语义) + BM25 (关键词)
    → BGEReranker 重排序
    → EvidenceSynthesis (qwen-plus, 证据综合)
    → 最终 evidence 文本
```

#### 5.4.2 知识库内容

系统内置 **12 篇**中国脑卒中相关指南/共识：

- 中国急性缺血性卒中诊治指南 2023
- 中国急性缺血性卒中早期血管内介入诊疗
- 中国急性脑梗死后出血转化诊治共识 2019
- 中国脑卒中防治指导规范（2021 年版）
- 中国重症卒中管理指南 2024
- 急性缺血性卒中血管内治疗中国
- 急性缺血性脑卒中急诊急救中国专家共识 (2018 版)
- 急性缺血性脑卒中早期血管内介入治疗流程与规范专家共识
- 急性缺血性脑卒中血管内治疗中国专家共识
- 脑卒中中西医结合防治指南 (2023 版)
- 脑血管病防治指南（2024 年版）

### 5.5 视觉识别服务 (VisionAnalysisService)

支持多模态图片分析（基于 Qwen-VL）：

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **image_report** | 图片包含检验报告特征 | OCR 识别 → 异常指标解读 → 综合分析 |
| **image_drug** | 图片包含药品包装特征 | 药品识别 → 详细信息 → 用药安全提示 |
| **image_general** | 一般医学图片 | 通用医学图片分析 + 安全约束 |

### 5.6 上下文摘要服务 (ConversationSummaryService)

实现多轮对话的上下文压缩：

```
每次对话完成:
  1. 评估本轮价值 (conversation_value_score prompt → qwen-turbo)
     评分: 1.0(关键) / 0.6(有价值) / 0.2(一般) / 0.0(无价值)

  2. 若 score >= 0.4，更新 all_info:
     conversation_summary_merge → qwen-turbo
     输出: 3-6 条中文要点，保留关键病情/检查/风险/建议

  3. 新的 all_info 存入 done 事件，前端下次请求时回传
```

### 5.7 三种 LLM 的角色分工

| 模型 | 场景 | 选择理由 |
|------|------|---------|
| **qwen-max** | Proposer（推理）、Report（报告）、3 专家推理 | 需要深度推理，容错率低 |
| **qwen-plus** | Critic（审查）、Analysis（分析）、Retrieval（检索）、Evidence Synthesis（证据综合） | 中等复杂度，需要较快速度 |
| **qwen-turbo** | Intent（意图）、QuickAnalyze（快速分析）、HealthRisk（风险评估）、Summary（摘要）、Naming（命名） | 简单任务，追求低延迟低成本 |

---

## 6. 数据库设计

### 6.1 数据库概览

- **数据库**: MySQL 8
- **数据库名**: `medai`
- **字符集**: UTF-8
- **连接池**: HikariCP（最大 15，最小空闲 5）

### 6.2 表结构

#### 6.2.1 `med_user` — 用户表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键，自增 |
| username | VARCHAR(64) | 用户名，唯一 |
| password | VARCHAR(128) | BCrypt 加密密码 |
| avatar | VARCHAR(512) | 头像 URL (OSS) |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

#### 6.2.2 `talk` — 对话会话表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键（IdWorker 雪花 ID 赋值） |
| user_id | BIGINT | FK → med_user.id |
| title | VARCHAR(128) | 对话标题（首条消息摘要） |
| content | TEXT | 会话完整内容 |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

#### 6.2.3 `cont` — 对话消息表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键 |
| talk_id | BIGINT | FK → talk.id |
| user_id | BIGINT | FK → med_user.id |
| role | VARCHAR(16) | 角色：user / assistant |
| content | TEXT | 消息文本内容 |
| images | LONGTEXT | JSON 数组，Base64 图片 |
| create_time | DATETIME | 创建时间 |

#### 6.2.4 `patient` — 患者表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED PK | 主键，自增 |
| name | VARCHAR(64) | 患者姓名 |
| history | TEXT | 病史 |
| notes | TEXT | 医生备注 |
| doctor_id | BIGINT UNSIGNED | FK → med_user.id |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

#### 6.2.5 `ai_opinion` — AI 分析意见表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED PK | 主键，自增 |
| patient_id | BIGINT UNSIGNED | FK → patient.id |
| risk_level | VARCHAR(16) | 风险等级：low/medium/high |
| suggestions | TEXT | AI 建议 |
| analysis_details | TEXT | 分析详情 |
| source_type | VARCHAR(16) | 来源：health_data / sync_talk |
| source_id | BIGINT UNSIGNED | 关联原始数据 ID |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

#### 6.2.6 `health_data` — 健康数据表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED PK | 主键，自增 |
| patient_id | BIGINT UNSIGNED | FK → patient.id |
| data_content | TEXT | JSON 格式健康数据 |
| create_time | DATETIME | 创建时间 |

#### 6.2.7 `learning_material` — 学习材料表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED PK | 主键，自增 |
| title | VARCHAR(128) | 标题 |
| category | VARCHAR(64) | 分类（如 cardiovascular） |
| type | VARCHAR(32) | 类型：document/video/link |
| url | VARCHAR(512) | 资源 URL |
| content | TEXT | 文本内容 |
| create_time | DATETIME | 创建时间 |
| update_time | DATETIME | 更新时间 |

#### 6.2.8 `change_key` — 密码/信息变更记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键 |
| user_id | BIGINT | FK → med_user.id |
| old_value | VARCHAR | 旧值（加密） |
| new_value | VARCHAR | 新值（加密） |
| type | VARCHAR | 变更类型 |
| create_time | DATETIME | 创建时间 |

### 6.3 索引策略

- 所有主键默认为聚簇索引
- `talk.user_id`、`cont.talk_id`、`patient.doctor_id` 建议建立非聚簇索引（高频查询字段）
- `ai_opinion.patient_id` 建议建立联合索引 `(patient_id, create_time)` 用于按时间倒序查询

---

## 7. API 接口规范

### 7.1 Java 后端接口 (Port 8080)

#### 7.1.1 用户模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/user/register` | 否 | 用户注册 |
| POST | `/api/user/login` | 否 | 用户登录，返回 JWT Token |
| POST | `/api/user/logOut` | 否 | 用户退出，清除 Redis 会话 |
| POST | `/api/user/upload` | 否 | 上传头像到 OSS |

**注册请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**登录响应体**:
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiJ9...",
    "userId": 1,
    "username": "doctor_zhang",
    "avatar": "https://oss.example.com/avatars/1.jpg"
  }
}
```

#### 7.1.2 对话模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/user/title` | 是 | 获取对话列表 |
| DELETE | `/api/user/deleteTalk/{talk_id}` | 是 | 删除对话 |
| GET | `/api/user/ques/getQues/{talk_id}` | 是 | 获取对话历史消息 |
| POST | `/api/user/ques/streamingQues` | 是 | **SSE 流式 AI 问答（核心）** |

**流式问答请求体**:
```json
{
  "talkId": 0,
  "question": "患者65岁女性，突发右侧肢体无力2小时...",
  "images": [],
  "reportMode": "emergency",
  "showThinking": true
}
```

**流式问答请求头**:
```
Content-Type: application/json
token: eyJhbGciOiJIUzI1NiJ9...
Last-Event-ID: 12345:56    (可选，断线重连时携带)
```

#### 7.1.3 AI 分析模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/ai/analyze` | 是 | 健康风险分析（关联患者） |
| POST | `/api/ai/sync-talk` | 是 | 同步医患对话到 AI 分析 |

#### 7.1.4 患者管理模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/patients` | 是 | 分页查询患者列表 |
| POST | `/api/patients` | 是 | 创建患者 |
| GET | `/api/patients/{id}` | 是 | 获取患者详情 |
| PUT | `/api/patients/{id}` | 是 | 更新患者信息 |
| DELETE | `/api/patients/{id}` | 是 | 删除患者 |

**查询参数**: `page`, `pageSize`, `name`（模糊搜索）

#### 7.1.5 文档与学习材料模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/documents` | 是 | 按分类列出 OSS 文档 |
| GET | `/api/documents/{id}/url` | 是 | 获取文档签名 URL（30 分钟有效） |
| GET | `/api/documents/match` | 是 | 按名称匹配文档 |
| GET | `/api/learning-materials` | 是 | 分页获取学习材料 |
| GET | `/api/learning-materials/{id}` | 是 | 获取学习材料详情 |

#### 7.1.6 其他模块

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/pubmed/search` | 是 | PubMed 文献检索（代理到 Python） |
| PUT | `/api/user/showInfo/changeKey` | 是 | 修改密码/个人信息 |
| GET | `/api/user/showInfo` | 是 | 获取当前用户信息 |
| GET | `/api/monitor/rate-limit/status` | 是 | 查看限流状态 |
| GET | `/api/monitor/rate-limit/reset` | 是 | 重置限流计数器 |

### 7.2 Python 模型层接口 (Port 8000)

#### 7.2.1 临床推理接口

**`POST /model/get_result`**（SSE 流式，核心接口）

请求体:
```json
{
  "question": "患者65岁女性，突发右侧肢体无力2小时，NIHSS 12分...",
  "round": 2,
  "all_info": "上一轮摘要...",
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "report_mode": "emergency",
  "show_thinking": true,
  "images": []
}
```

SSE 事件类型:

| 事件类型 | 方向 | 说明 |
|---------|------|------|
| `node_start` | Python → Java | 推理节点开始执行 |
| `token` | Python → Java | LLM 生成的单个 token |
| `thinking` | Python → Java | 思考过程（步骤/标题/内容） |
| `done` | Python → Java | 推理完成（含 name, request_id, all_info） |
| `error` | Python → Java | 推理异常（含 error_code, message, retryable） |
| `heartbeat` | Python → Java | 心跳（15 秒间隔，保持连接） |

#### 7.2.2 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/ai/analyze` | 健康风险分析（非流式） |
| POST | `/ai/quick-analyze` | 快速 AI 意见（非流式，跳过多专家推理） |
| POST | `/model/pubmed/search` | PubMed 文献检索 |
| POST | `/admin/reload_config` | 热更新配置（无需重启） |
| GET | `/admin/report_modes` | 列出可用报告模式 |

---

## 8. SSE 实时流式通信

### 8.1 事件流转

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Vue 前端  │────►│  Java 后端    │────►│ Python 模型层 │────►│  Qwen LLM │
│  (fetch)  │     │  (WebClient) │     │  (LangGraph) │     │ (DashScope)│
└──────────┘     └──────────────┘     └──────────────┘     └──────────┘
     │                   │                     │
     │  SSE text stream  │  JSON event stream  │  HTTP/SSE stream
     │  (chunk/thinking/ │  (token/node_start/ │  (OpenAI compat)
     │   done/error)     │   done/error)       │
     ▼                   ▼                     ▼
```

### 8.2 事件映射表

| Python 事件 | Java 内部处理 | 前端事件 | 前端行为 |
|------------|-------------|---------|----------|
| `token` | 追加到 answer buffer | `chunk` | 逐字打字机效果 |
| `node_start` | 追加到 thinking buffer | `thinking` | 显示推理步骤 |
| `done` | 提取 name + all_info | `done` | 停止渲染，保存结果 |
| `error` | 填充 error_details | `error` | 显示错误提示 |
| `heartbeat` | —（忽略） | —（不转发） | 保持 SSE 连接 |

### 8.3 断线重连协议

```
正常流:
  Client ──► POST /streamingQues (Last-Event-ID: 空)
  Client ◄── id: 12345:1  data: chunk "患者"
  Client ◄── id: 12345:2  data: chunk "65岁"
  Client ◄── id: 12345:3  data: chunk "女性"
  ...连接断开（seq=3 之后的消息丢失）...

重连 (自动，最多 3 次):
  Client ──► POST /streamingQues (Last-Event-ID: 12345:3)
  Server 检查 SSEEventCache:
    - talkId=12345 的 sink 存在? 是
    - 过滤 seq > 3 的事件:
      ◄── id: 12345:4  data: chunk "突发"
      ◄── id: 12345:5  data: chunk "右侧"
      ... (继续从 seq=4 开始推送，若流仍活跃则自动续接直播) ...
      ◄── id: 12345:N  data: done
  ● 重连成功，无消息丢失

重连失败 (缓存不存在/已过期):
  Client ◄── error: E2003 "会话已过期，请重新提问"
```

**重连窗口**: 流结束后 5 分钟内可重连。  
**事件上限**: 每个 talkId 最多缓存 200 条事件（环形缓冲区）。

### 8.4 超时配置

| 层级 | 配置项 | 值 | 说明 |
|------|-------|-----|------|
| 前端 | fetch 超时 | 600s | 与后端 read-timeout 一致 |
| Java → Python | connect-timeout | 10s | WebClient 连接超时 |
| Java → Python | read-timeout | 600s | WebClient 读取超时 |
| Python | SSE ping | 15s | 心跳间隔 |
| Tomcat | connection-timeout | 660s | 略大于 read-timeout |

---

## 9. 安全体系

### 9.1 认证架构

```
                    用户登录
                       │
                       ▼
              ┌─────────────────┐
              │  BCrypt 密码校验  │
              └────────┬────────┘
                       │ 成功
                       ▼
              ┌─────────────────┐
              │ 生成 JWT Token   │
              │ - userId        │
              │ - username      │
              │ - jti (UUID)    │
              │ - exp (7天)     │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │                           │
         ▼                           ▼
  ┌──────────────┐          ┌──────────────┐
  │ Redis 存储    │          │ 返回给前端    │
  │ login:user:id │          │ (Header/     │
  │   → jti      │          │  localStorage)│
  │ user:token:X  │          └──────────────┘
  │   → UserDTO   │
  └──────────────┘
```

### 9.2 JWT 结构

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
{
  "userId": 1,
  "username": "doctor_zhang",
  "jti": "a1b2c3d4-...",
  "iat": 1750000000,
  "exp": 1750604800
}
```

### 9.3 安全措施

| 措施 | 实现 | 说明 |
|------|------|------|
| 密码加密 | BCrypt | 不可逆哈希 |
| JWT 鉴权 | HS256 (共享密钥) | 7 天过期 |
| 单点登录 | Redis jti 校验 | 新登录踢掉旧会话 |
| 会话管理 | Redis TTL (30min 滑动) | 30 分钟无操作自动过期 |
| CSRF | 禁用 | 前后端分离 + JWT 无状态 |
| CORS | Spring Security 全局配置 | 允许所有来源（生产需限制） |
| 服务间认证 | 共享 JWT Secret | Java → Python 传递用户 Token |
| 敏感配置 | 环境变量 | DB_PASSWORD, API_KEY, JWT_SECRET |

### 9.4 认证流程

```
每次请求:
  1. RefreshTokenInterceptor (order=0)
     ├─ 提取 Token (Header: "token" 或 "Authorization: Bearer xxx")
     ├─ 解析 JWT → userId, jti
     ├─ 检查 Redis login:user:{userId} 中的 jti 是否匹配
     │   - 不匹配 → 401 "账号在其他地方登录"
     ├─ 从 Redis user:token:{token} 恢复 UserDTO → ThreadLocal
     ├─ 刷新 Redis TTL (30 分钟)
     └─ 异常 → 401

  2. TokenInterceptor (order=1)
     ├─ 检查 ThreadLocalUtil.getCurrentUser() != null
     ├─ 记录客户端 IP
     └─ 空 → 401
```

---

## 10. 配置管理

### 10.1 Java 后端配置

配置源优先级：**环境变量 > application-prod.yml > application.yml**

#### 核心环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_HOST` | MySQL 主机 | `127.0.0.1` |
| `DB_PORT` | MySQL 端口 | `3306` |
| `DB_NAME` | 数据库名 | `medai` |
| `DB_PASSWORD` | 数据库密码 | `******` |
| `AI_API_URL` | Python 服务地址 | `http://127.0.0.1:8000` |
| `AI_API_SHARED_JWT_SECRET` | 共享 JWT 密钥 | `******` |
| `OSS_ENDPOINT` | OSS 端点 | `https://oss-cn-beijing.aliyuncs.com` |
| `OSS_BUCKET` | OSS 桶名 | `darkside` |
| `OSS_REGION` | OSS 地域 | `cn-beijing` |
| `OSS_ACCESS_KEY_ID` | OSS AK | `******` |
| `OSS_ACCESS_KEY_SECRET` | OSS SK | `******` |
| `OSS_DOC_PREFIX` | 文档前缀 | `documents/` |

#### 关键 Spring 配置

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 15       # 连接池最大连接数
      minimum-idle: 5             # 最小空闲连接
      connection-timeout: 30000   # 获取连接超时 (ms)
      idle-timeout: 600000        # 空闲超时 (ms)
      max-lifetime: 1800000       # 连接最大存活时间 (ms)

  data.redis:
    lettuce.pool:
      max-active: 20              # Redis 连接池最大活跃
      max-idle: 10                # 最大空闲连接
      min-idle: 2                 # 最小空闲连接

  codec.max-in-memory-size: 50MB  # WebFlux 内存缓冲上限

server:
  port: 8080
  tomcat:
    connection-timeout: 660s      # 连接超时
    max-connections: 10000        # 最大连接数
    threads:
      max: 200                    # 最大工作线程
      min-spare: 10               # 最小空闲线程
      accept-count: 100           # 等待队列长度

ai:
  api:
    url: ${AI_API_URL}            # Python 服务地址
    connect-timeout: 10000        # WebClient 连接超时
    read-timeout: 600000          # WebClient 读取超时
  sse:
    ring-buffer-size: 200         # SSE 事件缓存窗口大小
    cache-ttl-minutes: 5          # SSE 缓存过期时间
```

### 10.2 Python 环境变量

| 变量 | 说明 | 必须 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API 密钥 | 是 |
| `SECRET_KEY` | JWT 共享密钥（需与 Java 一致） | 是 |
| `AI_JWT_SECRET` | JWT 密钥别名 | 是 |
| `MODEL_NAME` | 默认 LLM 模型 | 否 (默认 qwen-max) |
| `CHROMA_PERSIST_DIR` | ChromaDB 持久化目录 | 否 (默认 ./chroma_db_unified) |
| `PORT` | 服务端口 | 否 (默认 8000) |
| `HF_ENDPOINT` | HuggingFace 镜像 | 否 (默认 https://hf-mirror.com) |

### 10.3 配置热更新 (Python)

Python 模型层支持 **不重启更新配置**：

```bash
POST /admin/reload_config

# 热更新范围:
# - prompts.yaml       (Prompt 模板)
# - report_templates.yaml  (报告模板)
# - expert_config.yaml     (专家配置)
# - limits_config.yaml     (参数限制)
# - rules_config.yaml      (校验规则)
```

所有配置管理器实现 `reload()` 方法，使用文件修改时间戳判断变更。

---

## 11. 限流与熔断

### 11.1 限流配置

基于 Redisson 分布式限流器（`RRateLimiter`），支持多实例部署：

```yaml
rate-limiter:
  global:
    limit: 200      # 全局每秒 200 次
    interval: 1     # 时间窗口 1 秒
  ip:
    limit: 30       # 单 IP 每分钟 30 次
    interval: 60    # 时间窗口 60 秒
  user:
    limit: 3        # 单用户每分钟 3 次 AI 推理请求
    interval: 60    # 时间窗口 60 秒
```

**限流 Key 格式**:
- 全局: `rate_limit:global:{second_epoch}`
- IP: `rate_limit:ip:{ip}:{minute_epoch}`
- 用户: `rate_limit:user:{userId}:{minute_epoch}`

### 11.2 熔断配置 (Resilience4j)

```yaml
resilience4j:
  circuitbreaker:
    instances:
      default:
        register-health-indicator: true
        sliding-window-size: 100        # 滑动窗口大小
        minimum-number-of-calls: 10      # 最小调用次数（开始统计）
        failure-rate-threshold: 50       # 失败率阈值 50%
        wait-duration-in-open-state: 10s # 开路状态持续时间
```

**状态机**:
```
CLOSED ──(失败率>50%)──► OPEN ──(10s 后)──► HALF_OPEN ──(成功)──► CLOSED
                          │                      │
                          └─(10s 内拒绝所有请求)─┘  └─(失败)──► OPEN
```

熔断器应用于 `AiAnalysisService` 中对 Python 服务的调用。

### 11.3 AI 分析并发控制

```java
// AiAnalysisService 中的信号量控制
private final Semaphore analysisSemaphore = new Semaphore(20);

// 获取许可（超时 30s）
if (!analysisSemaphore.tryAcquire(30, TimeUnit.SECONDS)) {
    throw new RuntimeException("系统繁忙，请稍后重试");
}
try {
    // 执行 AI 分析
} finally {
    analysisSemaphore.release();
}
```

---

## 12. 部署架构

### 12.1 推荐部署拓扑

```
┌──────────────────────────────────────────────────────────┐
│                    Nginx (反向代理)                        │
│  - gzip 压缩                                              │
│  - SSL 终止                                               │
│  - 静态文件服务 (Vue dist/)                                │
│  - /api/* → Java:8080                                    │
│  - SSE 长连接 proxy_buffering off                         │
└────────┬─────────────────────────────────┬───────────────┘
         │                                 │
         ▼                                 ▼
┌─────────────────────┐       ┌──────────────────────────┐
│  Java 后端 :8080     │       │  Python 模型层 :8000       │
│  (java -jar)        │       │  (uvicorn)                │
│  JVM: -Xmx512m      │       │  chroma_db_unified/       │
│                     │       │  data/documents/          │
└────────┬────────────┘       └──────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌───────┐
│ MySQL  │ │ Redis │
│ :3306  │ │ :6379 │
└────────┘ └───────┘
```

### 12.2 部署步骤 (宝塔面板)

1. **MySQL**: 创建数据库 `medai`，执行 `schema_additions.sql`
2. **Redis**: 启动 Redis 服务（默认配置）
3. **Python 模型层**:
   ```bash
   cd model
   pip install -r requirements.txt
   cp .env.example .env
   # 编辑 .env，填入 DASHSCOPE_API_KEY, SECRET_KEY
   python -m app.utils.download_models  # 下载 Sentence Transformer 模型
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
   ```
4. **Java 后端**:
   ```bash
   cd backend/ai/MyServer
   mvn clean package -DskipTests
   export DB_PASSWORD=xxx
   export AI_API_SHARED_JWT_SECRET=xxx
   export AI_API_URL=http://127.0.0.1:8000
   export OSS_ACCESS_KEY_ID=xxx
   export OSS_ACCESS_KEY_SECRET=xxx
   java -jar target/MyServer-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
   ```
5. **前端**:
   ```bash
   cd frontend
   npm install && npm run build
   # 将 dist/ 部署到 Nginx 静态目录
   ```

### 12.3 Nginx 示例配置

```nginx
server {
    listen 80;
    server_name example.com;

    # 前端静态文件
    location / {
        root /www/wwwroot/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 代理（REST）
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # SSE 代理（关键配置）
    location /api/user/ques/streamingQues {
        proxy_pass http://127.0.0.1:8080;
        proxy_buffering off;          # ★ 必须关闭缓冲
        proxy_cache off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 660s;      # 匹配 Tomcat connection-timeout
        chunked_transfer_encoding on;
    }
}
```

### 12.4 资源需求

| 服务 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| Java 后端 | 2 核 | 512MB-1GB | 100MB (JAR) |
| Python 模型层 | 2 核 | 2-4GB | 500MB (模型+向量库) |
| MySQL | 1 核 | 512MB | 根据数据量 |
| Redis | 1 核 | 256MB | 最小 |
| **总计（最小）** | 6 核 | 4-6GB | 1GB+ |

---

## 13. 核心业务流程

### 13.1 完整 AI 问诊流程

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 用户输入  │───►│ Java后端  │───►│ Python   │───►│ LangGraph│───►│ LLM推理  │
│ 病例描述  │    │ 认证/代理 │    │ FastAPI  │    │ 编排     │    │ (Qwen)   │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                    │               │               │               │
                    │               │               │               ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 1. Intent 意图识别 │
                    │               │               │    │    consultation   │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 2. Analysis 分析  │
                    │               │               │    │   结构化病例+子问题│
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 3. Retrieve 检索  │
                    │               │               │    │   RAG 证据检索    │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 4. Reason 推理    │
                    │               │               │    │   3专家并行 → 综合 │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 5. Validate 校验  │
                    │               │               │    │   规则+LLM反思    │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │    ┌───pass/retry/fail─┐
                    │               │               │    │ (retry时回到4)     │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 6. Report 报告    │
                    │               │               │    │   按模板生成报告   │
                    │               │               │    └────────┬─────────┘
                    │               │               │             │
                    │               │               │             ▼
                    │               │               │    ┌──────────────────┐
                    │               │               │    │ 7. Summary 摘要   │
                    │               │               │    │   更新 all_info   │
                    │               │               │    └──────────────────┘
                    │               │               │
                    │               ◄───────────────┘
                    │               │   SSE 事件流
                    │               │   (token/thinking/done/error)
                    │               │
                    ◄───────────────┘
                    │  SSE 事件流
                    │  (chunk/thinking/done/error)
                    │
                    ▼
               ┌─────────┐
               │ 前端渲染  │
               │ 打字机效果 │
               └─────────┘
```

### 13.2 流式对话时序（关键路径）

```
    前端              Java后端           Python模型层        Qwen LLM
     │                  │                   │                  │
     ├─ POST /streaming─►                   │                  │
     │                  ├─ registerStream ──►│                  │
     │                  ├─ WebClient POST ──►│                  │
     │                  │                   ├─ intent ─────────►
     │                  │                   │◄─ result ────────┤
     │                  │                   ├─ analysis ───────►
     │  ◄── init ───────┤                   │◄─ done ──────────┤
     │  ◄── thinking ───┤◄─ node_start ────┤                   │
     │                  │                   ├─ retrieve ───────►
     │                  │                   │◄─ evidence ───────┤
     │                  │                   ├─ reason(3并行) ───►
     │                  │                   │◄─ proposal ───────┤
     │                  │                   ├─ validate ────────►
     │                  │                   │◄─ pass/retry ─────┤
     │                  │                   ├─ report ──────────►
     │  ◄── chunk[0] ───┤◄─ token[0] ──────┤◄─ chunk[0] ───────┤
     │  ◄── chunk[1] ───┤◄─ token[1] ──────┤◄─ chunk[1] ───────┤
     │  ◄── ... ────────┤◄─ ... ───────────┤◄─ ... ────────────┤
     │  ◄── thinking ───┤◄─ thinking ──────┤                   │
     │  ◄── chunk[N] ───┤◄─ token[N] ──────┤◄─ chunk[N] ───────┤
     │  ◄── done ───────┤◄─ done ──────────┤                   │
     │                  │                   │                   │
     │                  ├─ completeStream   │                   │
     │                  ├─ async persist    │                   │
     │                  │  (cont + talk)    │                   │
```

### 13.3 对话持久化策略

```
对话完成 (done 事件) 后的异步持久化:

┌─────────────────────────────────────────┐
│  ConversationPersistenceService         │
│                                         │
│  1. 构建 cont 记录 (role=user):         │
│     - talkId, userId, question, images  │
│                                         │
│  2. 构建 cont 记录 (role=assistant):    │
│     - talkId, userId, answer            │
│                                         │
│  3. 批量插入 cont 表                    │
│                                         │
│  4. 更新 talk 记录:                     │
│     - title = naming_model 结果         │
│       (取首条问题前 30 字)               │
│     - content = 完整 JSON 序列化         │
│     - update_time = now()               │
│                                         │
│  忽略错误 (不阻塞 SSE done 事件)          │
└─────────────────────────────────────────┘
```

---

## 14. 错误码体系

### 14.1 Java 后端错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| 200 | 200 | 成功 |
| 401 | 401 | Token 过期/无效/被踢下线 |
| 404 | 404 | 资源不存在 |
| 422 | 422 | 参数校验失败 |
| 500 | 500 | 服务器内部错误 |
| 503 | 503 | 服务不可用（AI 服务未就绪/限流） |

### 14.2 Python 模型层错误码

| 错误码 | 说明 | 可重试 |
|--------|------|--------|
| E1001 | LLM 调用超时 (DASHSCOPE_TIMEOUT) | 是 |
| E1002 | LLM 限流 (DASHSCOPE_RATE_LIMITED) | 是 |
| E1003 | LLM 认证失败 (DASHSCOPE_AUTH_FAILED) | 否 |
| E1004 | LLM 内容过滤 (DASHSCOPE_CONTENT_FILTERED) | 否 |
| E2001 | 意图识别失败 (INTENT_FAILED) | 是 |
| E2002 | 推理执行失败 (REASONING_FAILED) | 是 |
| E2003 | 会话已过期 (SESSION_EXPIRED) | 否 |
| E2004 | 校验失败已达上限 (VALIDATION_MAX_RETRIES) | 否 |
| E3001 | 输入过长 (INPUT_TOO_LONG) | 否 |
| E3002 | 输入包含敏感内容 (INPUT_SENSITIVE) | 否 |
| E4001 | RAG 检索失败 (RAG_RETRIEVAL_FAILED) | 否 |
| E5001 | 内部错误 (INTERNAL_ERROR) | 否 |

### 14.3 SSE 错误事件格式

```json
{
  "type": "error",
  "code": "E2002",
  "message": "推理执行失败，请稍后重试",
  "retryable": true,
  "request_id": "a1b2c3d4e5f6"
}
```

---

## 15. 附录

### 15.1 关键技术术语对照

| 缩写 | 全称 | 说明 |
|------|------|------|
| CDSS | Clinical Decision Support System | 临床决策支持系统 |
| SSE | Server-Sent Events | 服务器推送事件 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 |
| MDT | Multi-Disciplinary Treatment | 多学科会诊 |
| NIHSS | National Institutes of Health Stroke Scale | 美国国立卫生研究院卒中量表 |
| mRS | modified Rankin Scale | 改良 Rankin 量表 |
| DICOM | Digital Imaging and Communications in Medicine | 医学数字成像与通信 |
| BCrypt | Blowfish Crypt | 密码哈希算法 |
| JWT | JSON Web Token | 无状态认证令牌 |

### 15.2 报告模式说明

| 模式 Key | 名称 | 适用场景 | 输出结构 |
|----------|------|---------|---------|
| `emergency` | 急诊完整报告 | 急诊/急性卒中 | 9 段式完整报告 |
| `analysis` | 深度分析报告 | 疑难病例分析 | 6 段式分析报告 |
| `outpatient` | 门诊简洁报告 | 门诊快速参考 | 5 段式简洁输出 |
| `consultation` | MDT 会诊报告 | 多学科会诊 | 6 段式系统分析 |
| `fast` | 快速回复 | 简单咨询 | 3 段式快速输出 |

### 15.3 医学影像支持

| 图片类型 | 分析模式 | 输出 |
|---------|---------|------|
| 检验报告单 | OCR + 异常解读 + 综合分析 | 结构化表格 + 异常指标列表 + 建议 |
| 药品包装 | 药品识别 + 适应症 + 安全提示 | 药品信息 + 注意事项 |
| 其他医学图片 | 通用医学分析 | 描述 + 关联分析 |

### 15.4 项目文件清单

```
核心配置文件:
  backend/ai/MyServer/pom.xml                          Maven 依赖
  backend/ai/MyServer/src/main/resources/application.yml      Spring 主配置
  backend/ai/MyServer/src/main/resources/application-prod.yml 生产环境覆盖
  model/requirements.txt                               Python 依赖
  model/.env.example                                   环境变量模板
  model/app/config/prompts.yaml                        Prompt 模板（~380 行）
  model/app/config/expert_config.yaml                  专家配置
  model/app/config/report_templates.yaml                报告模板（~285 行）
  model/app/config/rules_config.yaml                   校验规则
  model/app/config/limits_config.yaml                  参数限制

核心入口:
  backend/ai/MyServer/src/main/java/com/it/MyServerApplication.java
  model/app/main.py

核心服务:
  backend/.../service/AIStreamingService.java          SSE 流式对话
  backend/.../cache/SSEEventCache.java                 SSE 断线续传
  backend/.../service/AiAnalysisService.java           AI 分析（含熔断）
  model/app/agents/orchestrators/clinical_graph.py     LangGraph 推理图
  model/app/agents/orchestrators/qwen_agent.py         推理编排器
  model/app/rag/retrieve.py                            统一检索引擎

数据库:
  backend/ai/MyServer/src/main/resources/db/schema_additions.sql
```

---

> **文档维护者**: 开发团队  
> **最后更新**: 2026-07-05  
> **相关文档**: `docs/` 目录下的架构文档与迁移指南
