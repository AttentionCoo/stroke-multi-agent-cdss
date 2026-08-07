<p align="center">
  <h1 align="center">🧠 MedLLM / Stroke-Multi-Agent-CDSS</h1>
  <p align="center">
    <strong>多智能体深度检索脑卒中临床辅助决策支持系统 (CDSS)</strong>
  </p>
  <p align="center">
    <em>证据先行 · 过程透明 · 结果合规 · 时效硬管控</em>
  </p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/release/python-3110/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://jdk.java.net/21/"><img src="https://img.shields.io/badge/Java-21-ED8B00?style=flat-square&logo=openjdk&logoColor=white" alt="Java"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vue.js&logoColor=white" alt="Vue3"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://spring.io/projects/spring-boot"><img src="https://img.shields.io/badge/Spring_Boot-3.3.13-6DB33F?style=flat-square&logo=springboot&logoColor=white" alt="Spring Boot"></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-7-FF4438?style=flat-square&logo=redis&logoColor=white" alt="Redis"></a>
  <a href="https://www.langchain.com/langgraph"><img src="https://img.shields.io/badge/LangGraph-0.2-1C3C3C?style=flat-square&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/AttentionCasria/stroke-multi-agent-system/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square" alt="Status">
</p>

---

> 本项目是一套面向脑卒中（Stroke）临床场景的智能医疗辅助决策原型。系统以本地医学文献与临床指南为知识底座，融合 **Hybrid RAG（混合检索增强生成）**、**LangGraph 多智能体协同推理**、结构化绿道预评估与医生复核审计，支持从病例输入、证据检索到辅助分析和人工复核的完整演示流程。

---

## ⚡ 快速启动

推荐使用 Docker Compose 一次性启动前端、后端、模型服务、MySQL 与 Redis。启动前请先确认 Docker Desktop 已运行，并按以下步骤创建根目录与模型服务的环境变量：

**第一步：创建环境变量文件**

```bash
# Linux / macOS
cp .env.example .env
cp model/.env.example model/.env

# Windows PowerShell
Copy-Item .env.example .env
Copy-Item model/.env.example model/.env
```

**第二步：配置密钥**

编辑根目录 `.env`，为数据库、Redis、服务间鉴权设置独立强密码；再编辑 `model/.env`，至少填入模型密钥，并确保两处 `SECRET_KEY` 完全一致：

```env
DASHSCOPE_API_KEY=sk-您的阿里云百炼平台密钥
SECRET_KEY=与根目录.env一致的随机字符串（至少32位）
```

> 💡 **提示**：`DASHSCOPE_API_KEY` 从 [阿里云百炼平台](https://bailian.console.aliyun.com/) 获取；`SECRET_KEY` 可任意生成一段随机字符串。

**第三步：启动全部服务**

回到项目根目录执行：

```bash
docker compose up --build -d
docker compose ps
```

启动完成后优先访问前端页面：

| 服务 | 访问地址 | 用途 |
|------|----------|------|
| 前端 | `http://localhost/` | 登录与临床辅助分析工作台 |
| 后端 | `http://localhost:8080` | Spring Boot API 服务 |
| 模型服务 | `http://localhost:8000/docs` | FastAPI 接口文档 |

后续代码没有变化时，日常启动只需要执行：

```bash
docker compose up -d
```

如果服务没有全部启动成功，先执行 `docker compose ps` 查看状态，再用 `docker compose logs -f <服务名>` 查看日志。更多环境变量、手动启动和排错命令见 [快速接入与本地部署](#-快速接入与本地部署)。

---

## 📑 目录导航

- [⚡ 快速启动](#-快速启动)
- [🌟 项目核心亮点与创新](#-项目核心亮点与创新)
- [🏗️ 全栈系统架构与技术矩阵](#️-全栈系统架构与技术矩阵)
- [🧠 医学多智能体矩阵协同推理机制](#-医学多智能体矩阵协同推理机制)
- [⚙️ 系统整体功能模块](#️-系统整体功能模块)
- [🛠️ 系统核心协同流程](#️-系统核心协同流程)
- [📂 项目目录结构](#-项目目录结构)
- [📊 权威医学评测与效果验证](#-权威医学评测与效果验证)
- [🚀 快速接入与本地部署](#-快速接入与本地部署)
- [📝 核心 API 契约](#-核心-api-契约)
- [📖 技术文档索引](#-技术文档索引)
- [🔄 版本更新日志](#-版本更新日志)
- [🤝 贡献指南](#-贡献指南)
- [⚠️ 免责声明](#️-免责声明)

---

## 🌟 项目核心亮点与创新

### 🛡️ 1. 医疗安全三角架构（Tri-Layer Architecture）

系统摒弃了传统大模型问答的"单点输出"，构建了三层递进的安全控制架构：

| 层级 | 名称 | 核心技术 | 职责 |
|:---:|------|----------|------|
| **外层** | 结构化流程层 | 绿道评估模块 + LangGraph 状态图 | 在原有模型流程外增加字段完整性、时间窗、关键阈值预检查，以及医生复核和审计记录 |
| **中层** | 多专家协同层 | 独立意见 + 交叉质询 + 主持人共识 | 由**全科医生**、**神经专科医生**、**临床药师**先独立判断，再阅读同伴意见并质询冲突，最后由中立主持人形成可审计共识 |
| **后层** | 模型校验层 | 规则配置 + LLM 反思 | 保留原有模型推理与校验算法，对模型结果进行规则提示和反思循环 |

### 🔎 2. 证据前置的深度定制 Hybrid RAG

- **双路混合检索**：基于 ChromaDB（语义向量）+ BM25（医学术语精准匹配）的双路并发检索引擎，优先召回权威卒中指南与最新文献。
- **RRF 融合排序**：使用倒数排序融合（Reciprocal Rank Fusion）合并双路检索结果，按 `RRF(d) = Σ 1 / (60 + rank(d))` 累加文档在各检索通道中的排名得分，在无需校准异构相关性分数的情况下兼顾语义召回与关键词命中。
- **高级 QA 自建引擎**：系统精读医疗 PDF 并自动批量衍生提炼高质量 `Q:A` 对（附带原文页码标签），大幅提升急诊场景下的检索召回率。
- **深度重排与溯源**：RRF 融合后的候选文档再由 `gte-rerank` 进行深度语境打分与证据压缩，在最终报告中强制进行**文献名称与精准页码**的明确溯源。
- **Agentic RAG 检索循环**：临床检索规划器主动拆分任务，结合医学同义词扩展与 HyDE 描述生成查询；证据审查器按相关性、可信度、时效性和覆盖度评分，证据不足时自动改写查询并再次检索，默认最多两轮。
- **证据进入推理**：每条证据使用 `R{轮次}-Q{查询}-E{结果}` 编号，专家初始意见、交叉质询和最终共识均被要求引用真实证据编号，未覆盖的信息进入风险审查而不是被当作事实补全。

### ⚡ 3. 全栈响应式流式数据管道（Reactive Stream Pipeline）

后端通过 `WebClient`/Reactor 转发 SSE 流，模型服务使用 Python Asyncio，前端通过 Vue 3 `ReadableStream` 增量渲染。界面展示的是可观察的分析阶段、证据引用和校验状态，不展示或宣称暴露模型内部思维链。

### 🧠 4. 面向连续诊疗的三级患者记忆

选择关联患者后，Java 服务端在医生权限范围内组装**短期记忆**（当前会话）、**情景记忆**（历史健康数据与评估事件）和**语义记忆**（稳定病史与医生备注）。患者关联持久化在 `talk.patient_id`：空对话可首次绑定一位患者，之后如需切换患者必须新建对话，从源头避免跨患者历史混入。模型侧 `MemoryNode` 仅激活本轮所需的受限上下文；未选择患者时不加载长期记忆，显式选择无权访问的患者时后端会拒绝请求。

### 🆕 5. 分层测试与可复现评测

系统配备前端、后端与模型层自动化测试；新增离线评测运行器，对必需信息、禁用表述、引用白名单和结果哈希进行可复现检查。临床结论仍需使用冻结病例集和专家盲评另行验证。

---

## 🏗️ 全栈系统架构与技术矩阵

本项目采用典型的"前端交互、后端业务、模型推理"三层解耦架构，各层之间通过高并发、低延迟的响应式流进行数据穿透。

### 🛠️ 全栈技术矩阵

| 架构层级 | 核心技术栈 | 核心设计职责 |
|:---:|---|------|
| 🎨 **前端交互层** | Vue 3 (Composition API) · Vite 7 · Pinia · SCSS · Fetch / ReadableStream | 以用户体验为核心，持续接收后端流式推送并实时打字机渲染。支持医学文档（PDF）在线预览、图片上传（多模态扩展）以及多 Agent 思考步骤折叠展示 |
| ☕ **后端服务层** | Java 21 · Spring Boot 3.3.13 · Spring WebFlux · Redis 7 · Redisson · MySQL 8.0 · MyBatis-Plus | 采用响应式编程模型支持高并发吞吐。通过 JWT 实现身份认证与安全控制，利用 Redisson 分布式锁控制并发，通过 WebClient 对底层 Python 模型服务进行流式非阻塞调用与转发 |
| 🐍 **模型推理层** | Python 3.11+ · FastAPI · LangGraph · LangChain · Qwen-Max/Plus/Turbo · ChromaDB · BM25 · RRF · gte-rerank | 统一加载模型、Agentic RAG 检索循环、专家辩论与共识模块，通过异步生成器输出 `node_start`、`node_done`、`token`、`done` 标准事件 |

### 🔄 全链路流式数据管道（SSE Pipeline）

```text
用户病例输入 ──► Java 鉴权与限流隔离 ──► WebClient 异步非阻塞调用 ──► FastAPI 接收请求
  ──► Python Agent 多状态流式产出 (yield) ──► asyncio.Queue 队列 ──► Java (Flux 持续转发)
  ──► Vue3 (ReadableStream 接收与实时打字机渲染)
```

### 🔗 服务间通信拓扑

```text
前端 ←→ Java 后端:     REST (JSON) + SSE (text/event-stream)
Java 后端 ←→ Python:  HTTP/1.1 (JWT 鉴权, WebClient 非阻塞调用)
Python ←→ LLM:       HTTPS (DashScope API, OpenAI 兼容协议)
Python ←→ ChromaDB:  本地文件系统 (持久化向量索引)
Java ←→ MySQL:       JDBC (HikariCP 连接池)
Java ←→ Redis:       Lettuce (响应式 Redis 7 客户端)
```

---

## 🧠 医学多智能体矩阵协同推理机制（Multi-Agent System）

为解决传统单模型医疗决策盲点多、风险高的痛点，系统基于 **LangGraph** 创新设计了"业务专家轴（纵向） × 决策行为轴（横向）"的双轴矩阵多智能体协同架构，高度模拟三甲医院真实临床的"科室多学科会诊（MDT）"与"三级医疗把关"流程。

### 1. 双轴协同拓扑架构图

```text
                     【 决策行为轴 (横向 LangGraph 拓扑演进) 】

                      独立意见阶段         交叉质询阶段          主持人共识阶段
                     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  全科医生 (GP) ────►│ 整体风险立场 │ ───►│ 阅读并质询同伴│ ──┐ │              │
  神经专家 (NS) ────►│ 定位/时间窗立场│ ───►│ 修正专业结论  │ ──┼►│ 冲突裁决与共识│
  临床药师 (CP) ────►│ 禁忌证立场   │ ───►│ 标记用药冲突  │ ──┘ │ Proposal +   │
                     └──────────────┘     └──────────────┘     │ Critique     │
                            ▲                                  └──────┬───────┘
                            └────────── [校验失败后重新会诊] ─────────┘
```

### 2. 双轴矩阵核心深度解析

#### 📌 纵向维度：医学专家角色精准定义（Roles）

系统为各智能体注入了深度定制的系统提示词（System Prompts）与特异性知识库，使其具备垂直领域的专家特质：

| 专家角色 | LLM 引擎 | 核心职责 |
|----------|:--------:|----------|
| 🏥 **全科医生 (GP)** | qwen-max | 全盘审视患者整体生命体征，提取主诉、现病史、重要既往史与合并慢性病（高血压、糖尿病、高脂血症）的整体风险分级 |
| 🧠 **神经专科医生 (NS)** | qwen-max | 系统的"核心决策大脑"。专注于卒中特异性临床表现、责任血管解剖定位、NIHSS 评分计算、TOAST 分型，以及溶栓/取栓时间窗自适应决策 |
| 💊 **临床药师 (CP)** | qwen-max | 侧重全链路用药安全。严密审查抗血小板、抗凝、降压、降脂等药物的绝对/相对禁忌症、药物相互作用（DDI）及配伍高危风险 |

#### 📌 横向维度：Independent-Debate-Consensus 状态机拓扑（Pipeline）

通过 LangGraph 控制状态流转，横向行为轴被划分为标准的三阶段动态博弈：

1. **Independent（独立意见阶段）**：三大专家 Agent 并行启动，基于同一病例、患者记忆和带编号证据形成可供质询的专业立场。
2. **Debate（交叉质询阶段）**：每位专家阅读全部同伴意见，明确同意点、冲突点、修正结论及仍需人工确认的不确定性。
3. **Consensus（主持人共识与反思拦截阶段）**：
   - **动态共识机制**：中立主持人说明已达成共识、被否决分歧及原因，再输出 `PROPOSAL` 与 `CRITIQUE`。
   - **安全熔断器**：若规则引擎或独立质控发现硬性禁忌证、证据冲突或把信息缺口当成既定事实，系统将拦截当前共识并携带反馈重新发起专家会诊（最多 3 次）。

### 3. LLM 分层调度策略

| 模型 | 负责节点 | 选择理由 |
|------|----------|----------|
| **qwen-max** | 专家独立意见、交叉质询、Report（报告） | 需要深度推理，容错率低 |
| **qwen-plus** | Analysis、ResearchPlan、EvidenceJudge、QueryRewrite、Consensus、Validate | 负责结构化、证据控制、共识与安全审查 |
| **qwen-turbo** | Intent（意图识别）、QuickAnalyze（快速分析）、HealthRisk（风险评估）、Summary（摘要）、Naming（命名） | 简单任务，追求低延迟低成本 |

---

## ⚙️ 系统整体功能模块

本项目围绕医疗辅助分析场景，构建了五个可演示模块：

### 1. 🤖 智能问诊与 AI 临床辅助分析模块

该模块是系统的核心功能入口。系统接收症状描述后进行结构化拆解：

- **结构化临床输出**：包括最可能诊断及依据、解剖定位分析（如责任血管评估）、病理机制解释、置信度评估及需排除的重要鉴别诊断。
- **安全路径切换**：具备"极速与安全双路径设计"——简单知识问答快速响应，涉及高风险临床诊断自动切入多智能体深度分析。
- **多模态支持**：支持检验报告单 OCR 识别、药品包装图片识别等视觉输入。

### 2. ⏱️ 急诊绿道结构化评估模块

- **结构化录入**：关联患者，记录最后正常时间、到院时间、血压、血糖、NIHSS、血小板、INR、抗凝药与影像关键结论。
- **时效与完整性**：动态展示 4.5 小时静脉溶栓参考窗口、24 小时取栓评估参考窗口和 DNT；缺失字段单独列出。
- **关键风险预检查**：按结构化数据提示出血、血压、血小板和 INR 等风险信号，并展示规则来源。该结果只用于信息核对，不替代医生判断。
- **人工复核闭环**：支持保存评估、修改前后差异、接受/退回/驳回、复核理由与不可变快照审计。
- **交付能力**：支持打印报告和 FHIR R4 风格原型 Bundle 导出；FHIR 仅用于互操作演示，尚未完成院内适配认证。

### 3. 👤 患者电子档案与个体化分析模块（EHR）

系统引入患者档案管理机制，支持长期随访与动态优化：

- **连续性健康管理**：记录患者基本信息、既往病史、用药史及医生备注。
- **上下文联动**：单次问诊结束后，后台异步模型自动总结当前对话重点并更新至 `all_info` 上下文，后续多轮就诊自动结合历史记录进行个体化风险评估。
- **健康数据分析**：支持健康数据与医患对话同步，自动生成 AI 风险分析意见。

### 4. 📚 医学知识学习与文献检索模块

- **本地指南增强**：内置 **12 篇**中国脑卒中相关权威指南与共识，提供在线阅读与结构化浏览，同时作为 RAG 底座为推理提供强力的证据支撑。
- **在线文献拓扑**：提供外部 PubMed 接口连接支持，可根据临床症状一键抓取最新外文高水平文献列表。

### 5. 🧪 自动化测试与评估模块

- **离线规则评测**：对冻结输入与预测结果执行必需信息、禁用表述、引用白名单检查，输出 JSON、Markdown 和 SHA-256 哈希。
- **多维度 API 测试**：覆盖核心推理接口、快速分析接口、同步分析接口的端到端测试。
- **架构迁移验证**：确保系统重构后功能完整性与行为一致性。

---

## 🛠️ 系统核心协同流程

当用户输入一个脑卒中病例（例如："患者男，65岁，突发左侧肢体无力3小时..."）时，系统内部的状态流转如下：

```text
用户输入病例
    │
    ▼
【外层·流程控制】意图识别 (过滤无关请求 / 分流"知识问答"与"临床问诊")
    │
    ├─ 无关请求 → 礼貌拒绝
    ├─ 知识问答 → 快速回答 (qwen-turbo)
    │
    ▼ (临床问诊)
【外层·流程控制】病例结构化分析 (提取主诉、既往史、时间窗、NIHSS评分等关键要素)
    │
    ▼
【外层·流程控制】检索规划与医学查询扩展 (任务拆分 + 同义词扩展 + HyDE)
    │
    ▼
【外层·流程控制】双路混合检索 → RRF 融合 → gte-rerank 重排
    │
    ▼
【外层·流程控制】证据质量评估 ── 不足 → 查询重写 → 再次检索（最多两轮）
    │                                                     │
    ▼                                                     │
【中层·专家协作】独立意见 → 交叉质询 → 主持人共识 ◄────────┐
    │                                                     │
    ▼                                                     │
【后层·反思拦截】双重校验与反思                            │
    ├─ 规则引擎检查：硬匹配禁忌症规则（如活动性出血拦截）   │
    └─ LLM反思校验：深层医学逻辑与临床指南合规审查         │
    │                                                     │
    ▼                                                     │
  [校验通过？] ─── 否 (触发反思循环，最多3次重试) ──────———┘
    │ 是 (或超过最大重试次数，附警告)
    ▼
【外层·流程控制】报告生成 (输出含安全警告、文献溯源页码的最终临床报告)
    │
    ▼
【外层·流程控制】上下文总结更新 (后台异步模型总结对话重点，更新 EHR 患者档案)
```

---

## 📂 项目目录结构

```text
stroke-multi-agent-system/
├── frontend/                              # 🎨 前端工程 (Vue 3 + Vite 7)
│   ├── src/
│   │   ├── api/                           # API 封装（含 strokeAssessment 评估接口）
│   │   ├── components/                    # UI 组件
│   │   │   ├── form/                      # 表单组件 (登录、注册、编辑)
│   │   │   ├── svg/                       # SVG 图标组件
│   │   │   └── workspace/                 # 问诊、绿道、患者、文献与分析进度工作区
│   │   ├── router/                        # Vue Router 路由配置
│   │   ├── stores/                        # Pinia 状态管理 (用户状态、主题)
│   │   ├── utils/                         # 工具函数 (请求封装、图片压缩、引用解析、暂停控制)
│   │   └── views/                         # 页面视图 (登录、智能问诊)
│   ├── package.json
│   └── vite.config.js
│
├── backend/                               # ☕ 后端工程 (Spring Boot 3 + WebFlux)
│   └── stroke-server/
│       ├── src/main/java/com/it/
│       │   ├── cache/                     # SSE 断线续传事件缓存 + 在线用户追踪
│       │   ├── config/                    # 配置类 (Security, Redis, Redisson, WebClient, Jackson, OSS)
│       │   ├── controller/                # SSE 转发、REST API 与文件上传控制层
│       │   ├── domain/stroke/             # 结构化卒中评估、复核与导出领域模块
│       │   ├── adapter/stroke/            # 评估模块 MyBatis 持久化适配器
│       │   ├── handler/                   # 全局异常拦截器
│       │   ├── interceptor/               # JWT 双重拦截器 (Token 校验 + 自动续期) + Redis 限流
│       │   ├── mapper/                    # MyBatis-Plus Mapper 接口
│       │   ├── po/                        # 参数与视图对象 (DTO, UO, VO)
│       │   ├── pojo/                      # 持久化实体 (患者档案, 对话记录, AI 意见, 健康数据)
│       │   ├── service/                   # 业务逻辑层 (流式转发, 异步持久化, OSS 文档)
│       │   │   └── impl/                  # 核心实现 (AIStreamingServiceImpl, AiAnalysisServiceImpl 等)
│       │   ├── utils/                     # 工具类 (JWT, ThreadLocal, OSS 上传, IP 工具)
│       │   └── StrokeServerApplication.java   # 启动入口
│       ├── src/main/resources/
│       │   ├── application.yml            # 主配置 (数据源、Redis、AI 服务地址)
│       │   ├── application-dev.yml        # 开发环境配置
│       │   ├── application-prod.yml       # 生产环境配置
│       │   └── db/                        # 数据库初始化脚本
│       ├── sql/                           # 数据库 Schema 脚本
│       └── BAOTA_DEPLOY.md               # 宝塔面板部署指南
│
├── model/                                 # 🐍 模型推理服务层 (Python FastAPI)
│   ├── app/
│   │   ├── agents/                        # 智能体核心模块
│   │   │   ├── core/                      # 状态机模式与 ClinicalState 状态定义
│   │   │   ├── orchestrators/             # LangGraph 推理图构建
│   │   │   │   ├── clinical_graph.py      # Agentic RAG 与会诊双循环状态图
│   │   │   │   ├── qwen_agent.py          # Qwen Agent 编排器
│   │   │   │   └── nodes/                 # 记忆、规划、检索、证据评估、辩论、共识与校验节点
│   │   │   ├── pipelines/                 # RAG 检索处理管道
│   │   │   ├── services/                  # 业务服务 (查询、检索、综合)
│   │   │   ├── bailian/                   # 百炼模型集成 (健康风险分析)
│   │   │   ├── infra/                     # 基础设施 (Reranker 重排器)
│   │   │   ├── schemas/                   # 数据模型定义
│   │   │   └── utils/                     # 工具函数 (JSON 解析, LLM 辅助, 重试机制)
│   │   ├── config/                        # 动态配置中心 (YAML, 支持热更新)
│   │   │   ├── expert_config.yaml         # 专家角色与提示词配置
│   │   │   ├── rules_config.yaml          # 禁忌症规则与校验参数
│   │   │   ├── limits_config.yaml         # 参数限制与关键词配置
│   │   │   ├── prompts.yaml               # 提示词模板 (~380 行)
│   │   │   └── report_templates.yaml      # 报告模板 (5 种模式)
│   │   ├── rag/                           # RAG 模块 (QA 自动生成、混合检索、RRF 融合与语义重排)
│   │   ├── services/                      # 外部服务 (PubMed 文献抓取、Vision 多模态识别)
│   │   ├── evaluation/                    # 可复现离线规则评测运行器
│   │   ├── utils/                         # 通用工具 (上下文摘要, 错误码, 命名模型)
│   │   └── main.py                        # FastAPI 异步服务入口 (lifespan 资源管理)
│   ├── data/
│   │   └── documents/                     # 脑卒中临床指南 PDF 文档 (12 篇)
│   ├── tests/                             # 自动化测试套件
│   │   ├── test_rag.py                    # RAG 召回率验证
│   │   ├── test_api_client.py             # API 客户端测试
│   │   ├── test_analyze_api.py            # 分析 API 测试
│   │   ├── test_quick_analyze.py          # 快速分析测试
│   │   ├── test_new_architecture.py       # 新架构验证
│   │   └── test_migration.py              # 迁移兼容性测试
│   ├── requirements.txt                   # Python 依赖清单
│   ├── start.bat                          # Windows 一键启动脚本
│   └── start.sh                           # Linux/Mac 一键启动脚本
│
└── docs/                                  # 📄 项目文档
    ├── backend-technical-documentation.md  # ★ 后端技术文档（完整）
    ├── LangChain版本升级风险分析报告.md
    ├── LangChain迁移可行性分析报告.md
    ├── 全链路流式重构策略.md
    └── 模型层重构完成报告.md
```

---

## 📊 可复现评测与验证状态（Evaluation）

仓库提供 `model/app/evaluation/benchmark.py` 离线评测运行器、6 个合成边界病例和结果归档规范。运行器不会调用大模型，因此不会改变现有推理算法；它只对待测输出检查必需信息、禁用表述与引用白名单，并记录输入/输出哈希。

```bash
cd model
python -m app.evaluation.benchmark \
  --cases app/evaluation/benchmark_cases.jsonl \
  --predictions app/evaluation/predictions.example.jsonl \
  --output app/evaluation/results/smoke.json
```

当前仓库未包含可追溯的专家盲评原始记录、冻结预测全集或 RAGAS 结果文件，因此不声明诊断准确率、零漏报率或忠实度等精确临床指标。正式参赛数据应在病例脱敏、版本冻结和专家复核后放入 `model/app/evaluation/results/`，同时保留运行参数与哈希。

---

## 🚀 快速接入与本地部署

本节按“先跑起来，再做细分配置”的顺序组织。完整 Docker Compose 是推荐路径；只有需要本地调试单个服务时，才建议切换到手动启动。

| 场景 | 推荐方式 | 入口 |
|------|----------|------|
| 第一次体验完整系统 | Docker Compose | `docker compose up --build -d` |
| 日常继续使用 | Docker Compose | `docker compose up -d` |
| 修改前端、后端或模型代码后验证 | Docker Compose 重新构建 | `docker compose up --build -d` |
| 只调试某一个服务 | 手动启动 | 按 Model → Backend → Frontend 顺序启动 |

### 1. 环境依赖要求

| 层级 | 依赖项 | 最低版本 | 说明 |
|------|--------|:--------:|------|
| 全局 | Docker Desktop | 最新 | 完整项目容器化部署（推荐） |
| 后端服务 | JDK | 21+ | Java 运行环境 |
| 后端服务 | Maven | 3.8+ | 项目构建 |
| 前端服务 | Node.js | ≥ 20.19.0（推荐 ^22.12.0） | 前端开发与构建 |
| 模型服务 | Python | 3.11+ | AI 推理引擎 |
| 模型服务 | Anaconda / Miniconda | 推荐 | Python 环境管理 |

> 💡 **提示**：如不使用 Docker，需自行安装 MySQL 8.0+ 与 Redis 7.0+。

### 2. 基础环境配置

#### 🐳 Docker Compose 完整项目启动（推荐）

这是最省心的启动方式，会同时拉起 `frontend`、`backend`、`model`、`mysql` 和 `redis` 五个服务。

启动前建议先确认三件事：

- Docker Desktop 已经启动。
- `model/.env` 已经从 `model/.env.example` 复制，并配置了 `DASHSCOPE_API_KEY` 与 `SECRET_KEY`。
- 本机 `80`、`8080`、`8000`、`3306`、`6379` 端口没有被其他程序占用。

首次启动前，请复制 `model/.env.example` 为 `model/.env`，并至少配置 `DASHSCOPE_API_KEY` 和 `SECRET_KEY`：

```bash
# Linux / macOS
cp model/.env.example model/.env

# Windows PowerShell
Copy-Item model/.env.example model/.env
```

确认 Docker Desktop 已启动后，在项目根目录执行：

```bash
docker compose up --build -d
docker compose ps
```

首次构建需要下载基础镜像和安装依赖，耗时通常会长于后续启动。Compose 会把三个业务镜像打成 `stroke-multi-agent-frontend`、`stroke-multi-agent-backend` 和 `stroke-multi-agent-model`，标签由 `APP_IMAGE_TAG` 控制，默认是 `local`。`docker compose ps` 中建议确认 `frontend`、`backend`、`model`、`mysql` 与 `redis` 均为 `healthy`。所有容器启动后可访问：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost/ | 系统登录与工作台 |
| 后端 | http://localhost:8080 | Spring Boot API（未登录访问受鉴权保护） |
| 模型服务 | http://localhost:8000/docs | FastAPI 接口文档 |
| MySQL | `localhost:3306` | 数据库服务 |
| Redis | `localhost:6379` | 缓存服务 |

Compose 默认从 AWS 公共仓库拉取 Docker 官方基础镜像，并为模型镜像使用清华 Debian/PyPI 软件源，避免部分网络环境无法访问 Docker Hub 鉴权服务或官方软件源。可通过 `APP_IMAGE_TAG`、`DOCKER_BASE_IMAGE_REGISTRY`、`DEBIAN_MIRROR` 和 `PIP_INDEX_URL` 覆盖镜像标签、基础镜像仓库和软件源；若当前网络可直接访问官方服务，可分别设置为 `docker.io/library`、`http://deb.debian.org` 和 `https://pypi.org/simple`。

##### 常用管理命令

以下命令均需在项目根目录执行：

| 使用场景 | 命令 |
|---------|------|
| 日常启动（代码未变化） | `docker compose up -d` |
| 只打包镜像不启动 | `docker compose build` |
| 修改代码后重新构建并启动 | `docker compose up --build -d` |
| 仅重新构建前端 | `docker compose up --build -d frontend` |
| 查看全部服务状态 | `docker compose ps` |
| 持续查看全部日志 | `docker compose logs -f` |
| 持续查看单个服务日志 | `docker compose logs -f model` |
| 重启单个服务 | `docker compose restart frontend` |
| 停止并移除项目容器 | `docker compose down` |

`docker compose down` 会保留 MySQL、模型缓存和向量库等命名卷，下次启动可继续使用原有数据。除非确定要完全重置项目数据，否则不要执行 `docker compose down -v`。

##### 快速排错

如果启动失败，先运行 `docker compose ps` 确认服务状态，再通过 `docker compose logs -f <服务名>` 查看对应日志。常用服务名为 `frontend`、`backend`、`model`、`mysql` 和 `redis`。

| 现象 | 优先检查 |
|------|----------|
| 前端打不开 | `frontend` 是否为 `Up`，本机 80 端口是否被占用 |
| 登录或请求失败 | `backend` 是否为 `Up`，后端日志是否有鉴权或数据库连接错误 |
| AI 分析无响应 | `model` 是否为 `Up`，`model/.env` 是否配置了有效密钥 |
| 数据库连接失败 | `mysql` 是否为 `healthy`，是否误删了命名卷 |
| 缓存或限流异常 | `redis` 是否为 `healthy` |
| AI 分析质量不佳 | 检查 `model/.env` 密钥是否有效，指南 PDF 是否完整放置于 `model/data/documents/` |

> 💡 **提示**：如需将本项目迁移至百度千帆大模型平台（ERNIE 系列模型），请参阅 [百度千帆.md](百度千帆.md) 中的三阶段渐进式集成方案。

#### 🐳 仅启动 MySQL + Redis（可选）

> ⚠️ **注意**：以下命令仅用于不使用完整 Compose 部署、准备手动启动模型层、后端和前端的场景。请勿与上面的完整项目启动命令同时使用，否则会发生容器名和端口冲突。

确保 Docker Desktop 已启动，然后运行以下命令：

```bash
# 拉取并启动 MySQL 8.0
docker run -d --name stroke-mysql \
  -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=medai \
  mysql:8.0

# 拉取并启动 Redis 7
docker run -d --name stroke-redis \
  -p 6379:6379 \
  redis:7-alpine
```

启动后导入数据库 Schema：

```bash
docker exec -i stroke-mysql mysql -uroot medai < backend/stroke-server/sql/medai_schema.sql
```

> ⚠️ **注意**：每次重启 Docker Desktop 后，MySQL 和 Redis 容器会自动恢复运行。如遇连接问题，请确认 Docker Desktop 已完全启动。

#### 🐍 模型层环境配置

```bash
cd model
conda create -n neuro-model python=3.11
conda activate neuro-model
pip install -r requirements.txt
```

在 `model/` 根目录下创建 `.env` 文件（可参考 `.env.example`）：

```env
DASHSCOPE_API_KEY="sk-您的阿里云百炼平台密钥"
SECRET_KEY="自定义防越权的JWT随机字符串"
HF_ENDPOINT="https://hf-mirror.com"          # HuggingFace 镜像（国内推荐）
```

> ⚠️ **注意**：PyTorch 需手动安装 CUDA 版本，请勿写入 `requirements.txt`。参考 [PyTorch 官网](https://pytorch.org/) 选择对应版本。

#### ☕ 后端服务配置

修改 `backend/stroke-server/src/main/resources/application-dev.yml`（开发环境）或 `application-prod.yml`（生产环境），配置数据源与 Redis 连接信息：

```yaml
aiserver:
  datasource:
    host: localhost
    port: 3306
    database: medai
    username: root
    password: ${MYSQL_PASSWORD}            # 从根目录 .env 或系统环境读取
  redis:
    host: 127.0.0.1
    port: 6379
    password: ${REDIS_PASSWORD}
  ai-api:
    url: http://localhost:8000           # Python FastAPI 模型服务地址
    shared-jwt-secret: ${AI_API_SHARED_JWT_SECRET}

app:
  clinical-zone: ${CLINICAL_ZONE:Asia/Shanghai}
```

#### 🎨 前端服务配置

前端通过 Vite 代理转发请求至后端，默认配置已在 `vite.config.js` 中完成，通常无需额外修改。

### 3. 手动启动完整链路

> 以下步骤用于本地开发或单服务调试。若已经使用 Docker Compose 完整启动项目，不需要再执行这一组命令。

#### 第一步：启动模型服务（Model）

将脑卒中相关的医学指南 PDF 文件统一放入 `model/data/documents/` 文件夹，然后启动服务。系统首次运行会自动触发递归分块并进行 **AI Batch QA 衍生**，自动构建高频词 BM25 内存索引和 ChromaDB 向量索引。

```bash
cd model

# Windows
start.bat
# 或直接运行
python -m app.main

# Linux/Mac
bash start.sh
```

服务默认监听 `0.0.0.0:8000`。

#### 第二步：启动后端服务（Backend）

使用 IDE（如 IntelliJ IDEA）运行 `StrokeServerApplication.java`，或者使用 Maven 编译启动：

```bash
cd backend/stroke-server
mvn spring-boot:run
```

服务默认监听 `8080` 端口。

#### 第三步：启动前端服务（Frontend）

```bash
cd frontend
npm install
npm run dev
```

前端默认在 `localhost:5173` 启动，并自动代理请求至后端的响应端口。

### 4. 启动顺序总结

```text
① Docker (MySQL:3306 + Redis:6379)  →  ② Model (FastAPI :8000)  →  ③ Backend (Spring Boot :8080)  →  ④ Frontend (Vite :5173)
```

### 5. 生产环境部署

推荐使用宝塔面板进行生产部署，详细配置请参阅：

- [backend/stroke-server/BAOTA_DEPLOY.md](backend/stroke-server/BAOTA_DEPLOY.md) — 宝塔面板部署指南
- [docs/backend-technical-documentation.md](docs/backend-technical-documentation.md) — 第 12 节：部署架构（含 Nginx 配置）

---

## 📝 核心 API 契约

### 1. 临床决策推理流（SSE 长连接）

- **路径**：`POST /model/get_result`
- **协议**：SSE (Server-Sent Events)
- **说明**：由 Java WebFlux 转发并保持长连接流

**请求体**：

```json
{
  "question": "患者男，65岁，突发左侧肢体无力3小时，NIHSS评分12分，CT排除脑出血。如何处理？",
  "all_info": "既往史：高血压10年，糖尿病5年",
  "patient_id": 42,
  "patient_memory": {
    "short_term": "当前会话摘要",
    "episodic": "历史健康数据与评估事件",
    "semantic": "稳定病史与医生备注"
  },
  "token": "your-jwt-token",
  "report_mode": "emergency",
  "show_thinking": true
}
```

Java 转发接口额外接收可选的 `patientId`。数据库由 Flyway 的 `V2__add_patient_id_to_talk.sql` 为对话增加持久化患者关联；同一对话请求不同患者时，后端会在模型调用和消息写入前返回错误。

**SSE 事件类型**：

| 事件 | 方向 | data 结构 | 说明 |
|------|------|------|------|
| `node_start` | Python → Java | `{"node": "intent", "label": "正在判断问题类型...", "status": "running"}` | 推理节点开始执行 |
| `node_done` | Python → Java | `{"node": "evidence_judge", "summary": "...", "status": "done"}` | 节点完成及可展示摘要 |
| `token` | Python → Java | `{"content": "根据..."}` | LLM 生成的增量文本 |
| `thinking` | Java → Vue | `{"thinking": {"step": "analysis", "title": "病例结构化分析", "content": "..."}}` | Java 将节点事件统一映射为前端思考事件 |
| `done` | Python → Java | `{"name": "...", "request_id": "...", "all_info": "..."}` | 推理完成，含会话名称与上下文摘要 |
| `error` | Python → Java | `{"error_code": "...", "message": "...", "retryable": true}` | 推理异常，retryable 标识是否可重试 |
| SSE comment | 服务间 | `: ping` / `: heartbeat` | 协议层心跳，前端忽略，不作为业务 JSON |

### 2. 报告模式一览

| 模式 Key | 名称 | 适用场景 |
|----------|------|----------|
| `emergency` | 急诊完整报告 | 急诊/急性卒中，9 段式完整输出 |
| `analysis` | 深度分析报告 | 疑难病例分析，6 段式分析输出 |
| `outpatient` | 门诊简洁报告 | 门诊快速参考，5 段式简洁输出 |
| `consultation` | MDT 会诊报告 | 多学科会诊，6 段式系统分析 |
| `fast` | 快速回复 | 简单咨询，3 段式快速输出 |

### 3. 独立风险归纳（非检索极速模式）

- **路径**：`POST /ai/analyze`
- **说明**：快速返回风险分级评估，不触发多智能体深度推理

```json
// 响应示例
{
  "riskLevel": "high",
  "suggestion": "建议立即进行影像学检查",
  "analysisDetails": "..."
}
```

### 4. PubMed 文献检索

- **路径**：`POST /model/pubmed/search`
- **说明**：代理 PubMed 文献检索，辅助循证决策

### 5. 脑卒中医疗工具 (Tool Calling)

系统新增脑卒中领域工具集，既可独立调用（API），也已接入多智能体推理链（`tool_use` 节点）。

**工具清单（7 个）：**

| 类别 | 工具名 | 说明 |
|---|---|---|
| 量表评估 | `nihss_score` | NIHSS 卒中量表评分与分级 |
| 量表评估 | `mrs_score` | mRS 功能结局分级 |
| 量表评估 | `gcs_score` | GCS 意识障碍分级 |
| 溶栓治疗 | `thrombolysis_window_check` | 溶栓时间窗判断（3h/4.5h） |
| 溶栓治疗 | `rtpa_dose_calc` | rt-PA 剂量计算（0.9mg/kg，上限 90mg） |
| 禁忌症检查 | `contraindication_check` | 基于规则引擎的溶栓/抗凝/双抗禁忌症筛查 |
| 诊断分型 | `toast_classify` | TOAST 缺血性卒中病因分型辅助 |

**独立 API：**

- **路径**：`GET /model/tools/list` — 返回全部工具及其参数 schema
- **路径**：`POST /model/tools/call` — 调用指定工具（body：`{"name": "rtpa_dose_calc", "arguments": {"weight_kg": 70}}`）

**推理链集成：** 在病例分析（analysis）之后、检索规划（research_plan）之前插入 `tool_use` 节点，LLM 通过 function calling 自主选择调用工具，结果注入多专家推理上下文。事件流中新增 `tool_use` 节点（「医疗工具调用」）。

> ⚠️ 医疗安全：所有工具均为计算/筛查辅助，输出不替代临床医生判断；工具结果需结合影像、实验室检查综合评估。

### 6. 结构化绿道评估

| 方法与路径 | 说明 |
|---|---|
| `POST /api/stroke-assessments/evaluate` | 执行无副作用的完整性、时间线与关键阈值预检查 |
| `POST /api/stroke-assessments` | 保存一条评估草稿 |
| `GET /api/stroke-assessments?limit=20` | 查询当前医生的最近评估 |
| `PUT /api/stroke-assessments/{id}` | 更新评估并返回风险/完整度变化 |
| `POST /api/stroke-assessments/{id}/reviews` | 采纳、要求修改或驳回；非采纳动作必须填写原因 |
| `GET /api/stroke-assessments/{id}/reviews` | 查询版本化审核记录与快照 |
| `GET /api/stroke-assessments/{id}/fhir` | 导出带原型标记的 FHIR R4 风格 Bundle |

所有持久化接口按当前医生隔离数据；存在关键风险或信息缺失时，后端拒绝“采纳”动作。

> 📖 完整 API 文档请参阅 [docs/backend-technical-documentation.md](docs/backend-technical-documentation.md) 第 7 节：API 接口规范。

---

## 📖 技术文档索引

| 文档 | 说明 |
|------|------|
| [docs/backend-technical-documentation.md](docs/backend-technical-documentation.md) | ★ **后端技术文档（完整版）** — 涵盖架构设计、数据库设计、SSE 通信、安全体系、限流熔断、部署架构等 15 个章节 |
| [docs/tool-calling-design.md](docs/tool-calling-design.md) | ★ 脑卒中医疗工具集（Skill & Tool Calling）设计文档 — 工具清单、LangGraph 集成、API 规范、测试 |
| [docs/模型层重构完成报告.md](docs/模型层重构完成报告.md) | Python 模型层架构重构总结 |
| [docs/Agentic-RAG与协作式多智能体架构.md](docs/Agentic-RAG与协作式多智能体架构.md) | Agentic RAG 检索循环、专家辩论共识与三级患者记忆设计 |
| [docs/模型层改动汇报.md](docs/模型层改动汇报.md) | 模型层改动详情汇报 |
| [docs/全链路流式重构策略.md](docs/全链路流式重构策略.md) | 全链路流式数据管道设计策略 |
| [docs/LangChain版本升级风险分析报告.md](docs/LangChain版本升级风险分析报告.md) | LangChain 版本升级风险评估 |
| [docs/LangChain迁移可行性分析报告.md](docs/LangChain迁移可行性分析报告.md) | LangChain 迁移方案与可行性分析 |
| [backend/stroke-server/BAOTA_DEPLOY.md](backend/stroke-server/BAOTA_DEPLOY.md) | 宝塔面板生产环境部署指南 |
| [百度千帆.md](百度千帆.md) | 百度千帆大模型平台能力集成方案（模型底座、RAG 组件、安全网关） |
| [计设大赛本项目简介.md](计设大赛本项目简介.md) | 计算机设计大赛项目完整简介（功能、架构、创新点详解） |

---

## 🔄 版本更新日志

### v2.3.0 (2026-07-31)

- ✅ **Agentic RAG**：新增检索任务规划、医学查询扩展、HyDE、证据质量评估与最多两轮查询重写循环
- ✅ **多智能体协作**：升级为独立意见、交叉质询、主持人共识三阶段会诊，关键判断引用真实证据编号
- ✅ **患者记忆**：打通前端患者关联、Java 权限校验与三级记忆、Python `MemoryNode` 激活链路
- ✅ **安全修复**：禁忌证规则只匹配患者事实，不再把指南中的通用禁忌证清单误判为患者阳性病情
- ✅ **可观察性**：新增记忆、检索规划、证据评估、查询重写、辩论和共识阶段事件

### v2.2.0 (2026-07-31)

- ✅ **新增**：结构化急诊绿道评估、动态时间窗、DNT、完整性与关键风险预检查
- ✅ **新增**：医生复核、修改差异、审计快照、打印报告与 FHIR 原型导出
- ✅ **优化**：工作区按需加载，拆分 PDF 预览依赖，降低首屏脚本体积
- ✅ **安全**：移除令牌日志、收紧 CORS，数据库/Redis/服务密钥改为环境变量配置
- ✅ **评测**：新增可复现离线评测运行器，清理无原始证据支撑的精确指标声明
- ✅ **兼容**：保持现有大模型推理图、节点算法、提示词和模型路由不变

### v2.1.2 (2026-07-26)

- ✅ **文档**：README 全面修订 — 修正版本号（Redis 7、Spring Boot 3.3.13）、统一指南数量（12 篇）、修正 MySQL 密码示例
- ✅ **文档**：补充千帆集成方案与大赛简介文档链接
- ✅ **文档**：优化快速启动指引（分步说明、密钥获取提示）
- ✅ **文档**：完善 SSE 事件协议表格（补充 data 结构）

### v2.1.1 (2026-07-09)

- ✅ **修复**：dev 环境 MySQL 密码配置（默认值从空改为 `root`，匹配 Docker 容器）
- ✅ **修复**：OSS 服务空密钥容错处理（本地开发环境跳过 OSS 初始化）
- ✅ **修复**：Vite 代理端口配置（确保前端正确代理至后端 8080 端口）
- ✅ **新增**：Docker 一键部署 MySQL + Redis 说明
- ✅ **文档**：README 目录结构与实际项目对齐

### v2.1.0 (2026-07-05)

- ✅ **新增**：完整自动化测试套件（RAG 召回率、API 接口、架构迁移验证）
- ✅ **修复**：AI 同步意见关联 bug
- ✅ **优化**：配置管理支持热更新（无需重启）
- ✅ **文档**：新增完整后端技术文档（15 章节）

### v2.0.0 (2026-05)

- ✅ **重构**：Python 模型层架构重构，引入 LangGraph 状态图编排
- ✅ **新增**：Proposer-Critic-Integrator 三阶段推理流水线
- ✅ **新增**：规则引擎 + LLM 反思双重校验机制（最多 3 次迭代）
- ✅ **新增**：SSE 断线续传协议（Last-Event-ID + 环形缓冲区）
- ✅ **新增**：Resilience4j 熔断器 + Redisson 分布式限流
- ✅ **新增**：5 种报告模式（emergency / analysis / outpatient / consultation / fast）

### v1.0.0 (2026-04)

- ✅ 初始版本：基础多智能体对话、RAG 检索、患者管理功能

---

## 🤝 贡献指南

本项目为竞赛/研究项目，欢迎通过以下方式参与贡献：

1. **Fork 本仓库** 并创建功能分支
2. **提交 PR** 前确保通过现有测试套件
3. **代码风格** 请保持与现有代码风格一致
4. **文档更新** 涉及架构变更请同步更新相关文档

如有问题或建议，请提交 [GitHub Issue](https://github.com/AttentionCasria/stroke-multi-agent-system/issues)。

---

## ⚠️ 免责声明

> **重要提示**：本系统属于临床辅助决策参考系统（CDSS），系统生成的输出结果不代表最终临床诊断，亦不能替代专业医生的独立医学判断。最终诊疗决策必须由执业医师根据患者实际临床体征做出。
>
> 系统内置的医学知识库基于公开的临床指南与文献，可能存在时效性局限。使用者应结合最新的临床证据与患者个体情况进行综合判断。
>
> 本项目仅供学术研究、技术交流与临床教学参考使用，不得直接用于临床诊疗决策。

---

<p align="center">
  <sub>Made with ❤️ for better stroke care | © 2026 MedLLM Team</sub>
</p>
