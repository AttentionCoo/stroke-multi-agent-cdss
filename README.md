<p align="center">
  <h1 align="center">🧠 MedLLM / Stroke-Multi-Agent-CDSS</h1>
</p>

<p align="center">
  <strong>多智能体深度检索脑卒中临床辅助决策支持系统 (CDSS)</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Java-21-ED8B00?style=flat-square&logo=openjdk&logoColor=white" alt="Java">
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vue.js&logoColor=white" alt="Vue3">
  <img src="https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Spring_Boot-3-6DB33F?style=flat-square&logo=springboot&logoColor=white" alt="Spring Boot">
  <img src="https://img.shields.io/badge/LangGraph-0.2-1C3C3C?style=flat-square&logo=langchain&logoColor=white" alt="LangGraph">
</p>

> 本项目是一套专为脑卒中（Stroke）临床场景打造的智能医疗辅助决策系统。系统以权威医学文献与临床指南为知识底座，融合 **Hybrid RAG（混合检索增强生成）**、**LangGraph 多智能体协同推理**与**全栈响应式高并发全链路流式架构**，实现了从患者病例输入到"证据先行、过程透明、结果合规"的完整决策闭环。

---

## 📑 目录导航

- [🌟 项目核心亮点与创新](#-项目核心亮点与创新)
- [🏗️ 全栈系统架构与技术矩阵](#️-全栈系统架构与技术矩阵)
- [🧠 医学多智能体矩阵协同推理机制](#-医学多智能体矩阵协同推理机制)
- [⚙️ 系统整体功能模块](#️-系统整体功能模块)
- [🛠️ 系统核心协同流程](#️-系统核心协同流程)
- [📂 项目目录结构](#-项目目录结构)
- [📊 权威医学评测与效果验证](#-权威医学评测与效果验证)
- [🚀 快速接入与本地部署](#-快速接入与本地部署)
- [📝 核心 API 契约](#-核心-api-契约)
- [⚠️ 免责声明](#️-免责声明)

---

## 🌟 项目核心亮点与创新

### 🛡️ 1. 医疗安全三角架构（Tri-Layer Architecture）

系统摒弃了传统大模型问答的"单点输出"，构建了三层递进的安全控制架构：

- **外层（流程控制 - LangGraph）**：定义医疗业务状态图，关键决策节点引入人工/规则审批，强制关键节点停等，确保全流程合规可追溯。
- **中层（多专家协同 - Multi-Agent）**：模拟真实临床会诊，由 **全科医生**、**神经专科医生**、**临床药师** 并行推理，交叉把关减少盲点，并支持针对疑难病例的 Tree-of-Thoughts（分支搜索）探索。
- **后层（双重校验 - Reflection & Rules）**：采用"静态禁忌症规则引擎（硬拦截） + 动态 LLM 反思（深层医学逻辑软审查）"双重过滤。校验失败自动拉回上一层触发反思循环。

### 🔎 2. 证据前置的深度定制 Hybrid RAG

- **双路混合检索**：基于 ChromaDB（语义向量）+ BM25（医学术语精准匹配）的双路并发检索引擎，优先召回权威卒中指南与最新文献。
- **高级 QA 自建引擎**：系统精读医疗 PDF 并自动批量衍生提炼高质量 `Q:A` 对（附带原文页码标签），大幅提升急诊场景下的检索召回率。
- **深度重排与溯源**：整合 `gte-rerank` 进行深度语境打分与证据压缩，在最终报告中强制进行**文献名称与精准页码**的明确溯源。

### ⚡ 3. 全栈响应式流式数据管道（Reactive Stream Pipeline）

底座采用 **Java WebFlux 响应式高并发框架** 与 **Python Asyncio 异步队列** 深度流式融合，打通了从底层智能体组装到前端 Vue3 `ReadableStream` 实时渲染的链路，使得 AI 的 **Thinking Step（思考过程）** 完全透明可视化。

---

## 🏗️ 全栈系统架构与技术矩阵

本项目采用典型的"前端交互、后端业务、模型推理"三层解耦架构，各层之间通过高并发、低延迟的响应式流进行数据穿透。

### 🛠️ 全栈技术矩阵

| 架构层级 | 核心技术栈 | 核心设计职责 |
| --- | --- | --- |
| 🎨 **前端交互层** (Frontend) | Vue 3 (Composition API) · Vite 7 · Pinia · SCSS · Fetch / ReadableStream | 以用户体验为核心，持续接收后端流式推送并实时打字机渲染。支持医学文档（PDF）在线预览、图片上传（多模态扩展）以及多 Agent 思考步骤折叠展示。 |
| ☕ **后端服务层** (Backend) | Java 21 · Spring Boot 3 · Spring WebFlux · Redis 6.0 · Redisson · MySQL 8.0 · MyBatis-Plus | 采用响应式编程模型支持高并发吞吐。通过 JWT 实现身份认证与安全控制，利用 Redisson 分布式锁控制并发，通过 WebClient 对底层 Python 模型服务进行流式非阻塞调用与转发。 |
| 🐍 **模型推理层** (Model) | Python 3.11+ · FastAPI · LangGraph · LangChain · Qwen-Max · gte-rerank · ChromaDB | 统一入口加载大语言模型、混合检索引擎与多智能体推理模块。通过异步生成器持续输出标准事件格式（`thinking`, `chunk`, `done`），实现高效流式通信。 |

### 🔄 全链路流式数据管道 (SSE Pipeline)

```text
用户病例输入 ──► Java 鉴权与限流隔离 ──► WebClient 异步非阻塞调用 ──► FastAPI 接收请求
  ──► Python Agent 多状态流式产出 (yield) ──► asyncio.Queue 队列 ──► Java (Flux 持续转发)
  ──► Vue3 (ReadableStream 接收与实时打字机渲染)
```

---

## 🧠 医学多智能体矩阵协同推理机制（Multi-Agent System）

为解决传统单模型医疗决策盲点多、风险高的痛点，系统基于 **LangGraph** 创新设计了"业务专家轴（纵向） × 决策行为轴（横向）"的双轴矩阵多智能体协同架构，高度模拟三甲医院真实临床的"科室多学科会诊（MDT）"与"三级医疗把关"流程。

### 1. 双轴协同拓扑架构图

```text
                     【 决策行为轴 (横向 LangGraph 拓扑演进) 】

                      Proposer 阶段         Critic 阶段        Integrator 阶段
                     (方案生成智能体)     (风险审查智能体)     (整合反思智能体)
                     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  全科医生 (GP) ────► │ 初始病情评估 │ ───►│ 基础高危筛查 │ ───►│              │
                     └──────────────┘     └──────────────┘     │              │
                     ┌──────────────┐     ┌──────────────┐     │ 最终结构化决策│
  神经专家 (NS) ────► │TOAST/时间窗  │ ───►│ 神经禁忌挖掘 │ ───►│              │
                     └──────────────┘     └──────────────┘     │ (合规临床报告)│
                     ┌──────────────┐     ┌──────────────┐     │              │
  临床药师 (CP) ────► │ 药物配伍方案 │ ───►│ 溶栓出血风险 │ ───►│              │
                     └──────────────┘     └──────────────┘     └──────────────┘
                            │                    │                    ▲
                            └────────────────────┴─── [校验失败拦截] ──┘
                                                     (触发异步自愈反思流)
```

### 2. 双轴矩阵核心深度解析

#### 📌 纵向维度：医学专家角色精准定义 (Roles)

系统为各智能体注入了深度定制的系统提示词（System Prompts）与特异性知识库，使其具备垂直领域的专家特质：

- **全科医生 Agent (General Practitioner)**
  - **核心职责**：全盘审视患者整体生命体征，提取主诉、现病史、重要既往史与合并慢性病（如高血压、糖尿病、高脂血症）的整体风险分级。

- **神经专科医生 Agent (Neurologist Specialist)**
  - **核心职责**：系统的"核心决策大脑"。专注于卒中特异性临床表现、责任血管了解与解剖定位、NIHSS 评分计算、TOAST 分型，以及最关键的溶栓/取栓时间窗（Time Window）自适应决策。

- **临床药师 Agent (Clinical Pharmacist)**
  - **核心职责**：侧重全链路用药安全。严密审查抗血小板、抗凝、降压、降脂等药物的绝对/相对禁忌症、药物相互作用（DDI）及配伍高危风险。

#### 📌 横向维度：Proposer-Critic-Integrator 状态机拓扑 (Pipeline)

通过 LangGraph 控制状态流转，横向行为轴被划分为标准的三阶段动态博弈：

1. **Proposer（方案生成阶段）**：三大专家 Agent 并行启动，结合 Hybrid RAG 召回的指南证据，独立产出各自专业领域的初步诊疗子方案。
2. **Critic（独立风险审查阶段）**：各专家角色切换至"审慎黑盒模型"，执行交叉盲审。重点识别时间窗陷阱、症状隐匿性变化、禁忌症硬碰撞等 **6 大类高风险点**，对 Proposer 方案进行推翻、补充或质询。
3. **Integrator（方案整合与反思拦截阶段）**：
   - **动态反思循环机制**：Integrator 负责主导融合专家方案与审查意见。
   - **安全熔断器**：若检测到 Critic 提出的硬性规则（如"患者突发肢体无力已达 6 小时，但 Proposer 仍建议静脉溶栓"或"近期有活动性内出血"）未得到妥善解决，Integrator 将**强行触发拦截机制**，锁定当前状态流，自动拉回上一层专家节点进行重试，直至通过双重校验，实现**异步自愈反思流**。

---

## ⚙️ 系统整体功能模块

本项目围绕真实医疗及临床科研/教学场景，构建了三大核心闭环模块：

### 1. 🤖 智能问诊与 AI 临床辅助分析模块

该模块是系统的核心功能入口。系统接收症状描述后进行结构化拆解：

- **结构化临床输出**：包括最可能诊断及依据、解剖定位分析（如责任血管评估）、病理机制解释、置信度评估及需排除的重要鉴别诊断。
- **安全路径切换**：具备"极速与安全双路径设计"，简单知识问答快速响应，涉及高风险临床诊断自动切入多智能体深度分析。

### 2. 👤 患者电子档案与个体化分析模块 (EHR)

系统引入患者档案管理机制，支持长期随访与动态优化：

- **连续性健康管理**：记录患者基本信息、既往病史、用药史及医生备注。
- **上下文联动**：单次问诊结束后，后台异步模型自动总结当前对话重点并更新至 `all_info` 上下文，后续多轮就诊自动结合历史记录进行个体化风险评估。

### 3. 📚 医学知识学习与文献检索模块

- **本地指南增强**：内置国内多篇权威卒中指南，提供在线阅读与结构化浏览，同时作为 RAG 底座为推理提供强力的证据支撑。
- **在线文献拓扑**：提供外部 PubMed 接口连接支持，可根据临床症状一键抓取最新外文高水平文献列表。

---

## 🛠️ 系统核心协同流程

当用户输入一个脑卒中病例（例如："患者男，65岁，突发左侧肢体无力3小时..."）时，系统内部的状态流转如下：

```text
用户输入病例
    │
    ▼
【外层·流程控制】意图识别 (过滤无关请求 / 分流"知识问答"与"临床问诊")
    │
    ▼
【外层·流程控制】病例结构化分析 (提取主诉、既往史、时间窗、NIHSS评分等关键要素)
    │
    ▼
【外层·流程控制】大混合双重检索 (ChromaDB 向量语义 + BM25 精确匹配联动检索权威指南)
    │
    ▼
【中层·专家协作】多专家协同推理 ◄──────────────────────────┐
    ├─ 全科医生：整体病情与多维度风险分析                  │
    ├─ 神经专科医生：TOAST分型、溶栓/取栓指征决策          │
    └─ 临床药师：用药安全与配伍禁忌审查                    │
    │                                                     │
    ▼                                                     │
【后层·反思拦截】双重校验与反思                            │
    ├─ 规则引擎检查：硬匹配禁忌症规则（如活动性出血拦截）   │
    └─ LLM反思校验：深层医学逻辑与临床指南合规审查         │
    │                                                     │
    ▼                                                     │
  [校验通过？] ─── 否 (触发反思循环，重新修正) ──────———────┘
    │ 是
    ▼
【外层·流程控制】报告生成 (输出含安全警告、文献溯源页码的最终临床报告)
    │
    ▼
【外层·流程控制】上下文总结更新 (后台异步模型总结对话重点，更新 EHR 患者档案)
```

---

## 📂 项目目录结构

```text
neuro-multi-agent-system/
├── frontend/                         # 🎨 前端工程 (Vue 3 + Vite 7)
│   ├── src/
│   │   ├── api/                      # 封装 Fetch 响应式流请求
│   │   ├── components/               # UI 组件 (StreamViewer, ThinkingPanel, PdfPreviewModal 等)
│   │   │   ├── form/                 # 表单组件 (登录、注册、编辑)
│   │   │   ├── svg/                  # SVG 图标组件
│   │   │   └── workspace/            # 工作区组件 (问诊、患者、文献)
│   │   ├── router/                   # Vue Router 路由配置
│   │   ├── stores/                   # Pinia 状态管理 (用户状态、主题)
│   │   ├── styles/                   # SCSS 全局样式与变量
│   │   ├── utils/                    # 工具函数 (请求封装、图片压缩、引用解析)
│   │   └── views/                    # 页面视图 (登录、智能问诊)
│   ├── package.json
│   └── vite.config.js
│
├── backend/                          # ☕ 后端工程 (Spring Boot 3 + WebFlux)
│   └── ai/MyServer/
│       ├── src/main/java/com/it/
│       │   ├── config/               # 配置类 (Security, Redis, Redisson, WebClient, Jackson)
│       │   ├── controller/           # 响应式 Flux 控制层 (SSE 路由, REST API)
│       │   ├── handler/              # 全局异常拦截器
│       │   ├── interceptor/          # JWT 双重拦截器 (Token 校验 + 自动续期)
│       │   ├── mapper/               # MyBatis-Plus Mapper 接口
│       │   ├── po/                   # 参数与视图对象 (DTO, UO, VO)
│       │   ├── pojo/                 # 持久化实体 (患者档案, 对话记录, AI 意见)
│       │   ├── service/              # 业务逻辑层 (流式转发, 异步持久化)
│       │   │   └── impl/             # 核心实现 (AIStreamingServiceImpl 等)
│       │   ├── utils/                # 工具类 (JWT, ThreadLocal, OSS 上传)
│       │   └── MyServerApplication.java  # 启动入口
│       └── src/main/resources/
│           ├── application.yml       # 主配置 (数据源、Redis、AI 服务地址)
│           ├── application-dev.yml   # 开发环境配置
│           └── application-prod.yml  # 生产环境配置
│
├── model/                            # 🐍 模型推理服务层 (Python FastAPI)
│   ├── app/
│   │   ├── agents/                   # 智能体核心模块
│   │   │   ├── core/                 # 状态机模式与 ClinicalState 状态定义
│   │   │   ├── orchestrators/        # LangGraph 推理图构建
│   │   │   │   ├── clinical_graph.py # 临床推理图 (6 节点状态机)
│   │   │   │   └── nodes/            # 核心节点 (Intent, Analysis, Retrieve, Reason, Validate, Report)
│   │   │   ├── pipelines/            # RAG 检索处理管道
│   │   │   ├── services/             # 业务服务 (查询、检索、综合)
│   │   │   ├── bailian/              # 百炼模型集成 (健康风险分析)
│   │   │   ├── infra/                # 基础设施 (Reranker 重排器)
│   │   │   ├── schemas/              # 数据模型定义
│   │   │   └── utils/                # 工具函数 (JSON 解析, LLM 辅助, 重试机制)
│   │   ├── config/                   # 动态配置中心 (YAML)
│   │   │   ├── expert_config.yaml    # 专家角色与提示词配置
│   │   │   ├── rules_config.yaml     # 禁忌症规则与校验参数
│   │   │   ├── limits_config.yaml    # 参数限制与关键词配置
│   │   │   ├── prompts.yaml          # 提示词模板
│   │   │   └── report_templates.yaml # 报告模板
│   │   ├── rag/                      # RAG 模块 (QA 自动生成、混合检索器实现)
│   │   ├── services/                 # 外部服务 (PubMed 文献抓取、Vision 多模态识别)
│   │   ├── evaluation/               # 评估模块 (RAGAS 自动化评测)
│   │   ├── utils/                    # 通用工具 (上下文摘要, 错误码, Token 聚合)
│   │   └── main.py                   # FastAPI 异步服务入口
│   ├── data/
│   │   └── documents/                # 脑卒中临床指南 PDF 文档
│   ├── tests/                        # 自动化测试与 RAG 召回率验证
│   ├── requirements.txt              # Python 依赖清单
│   ├── start.bat                     # Windows 一键启动脚本
│   └── start.sh                      # Linux/Mac 一键启动脚本
│
└── docs/                             # 📄 项目文档
    ├── LangChain版本升级风险分析报告.md
    ├── LangChain迁移可行性分析报告.md
    ├── 全链路流式重构策略.md
    └── 模型层重构完成报告.md
```

---

## 📊 权威医学评测与效果验证 (Evaluation)

系统引入了基于 **RAGAS (RAG Assessment)** 框架的自动化评测，并邀请多位神经内科临床专家针对卒中特异性场景（如 TOAST 分型、溶栓/取栓时间窗、禁忌症筛查）进行了多维度的盲评（Blind Review）：

### 🏅 临床专业评测维度得分

| 评估维度 | 传统通用大模型 | 本系统 (MedLLM) | 临床专家盲评结论 |
| --- | --- | --- | --- |
| **诊断准确性**（诊断符合率） | 71.4% | **94.2%** | 结构化输出贴近真实临床思维，解剖定位准确。 |
| **风险意识**（核心禁忌症遗漏） | 14.3%（存在漏报） | **0%（100%拦截）** | 规则引擎与反思机制表现优异，无溶栓禁忌症遗漏。 |
| **方案实用性**（指南推荐契合度） | 62.5% | **89.5%** | 治疗方案紧扣时间窗决策，具备极高临床参考价值。 |

### 📈 RAGAS 自动化评估表现

| 评估指标 | 得分 | 说明 |
| --- | --- | --- |
| **忠实度 (Faithfulness)** | `0.94` | 方案严格依据检索证据生成，有效杜绝医疗幻觉风险 |
| **上下文精准度 (Context Precision)** | `0.91` | 语义重排效果显著，剔除无关文献干扰 |

---

## 🚀 快速接入与本地部署

### 1. 环境依赖要求

| 层级 | 依赖项 | 最低版本 |
| --- | --- | --- |
| 后端服务 | MySQL | 8.0+ |
| 后端服务 | Redis | 6.0+ |
| 后端服务 | JDK | 21+ |
| 后端服务 | Maven | 3.8+ |
| 前端服务 | Node.js | ≥ 20.19.0（推荐 ^22.12.0） |
| 模型服务 | Python | 3.11+ |
| 模型服务 | Anaconda / Miniconda | 推荐 |

### 2. 基础环境配置

#### 模型层环境配置

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
```

> **注意**：PyTorch 需手动安装 CUDA 版本，请勿写入 `requirements.txt`。参考 [PyTorch 官网](https://pytorch.org/) 选择对应版本。

#### 后端服务配置

修改 `backend/ai/MyServer/src/main/resources/application-dev.yml`（开发环境）或 `application-prod.yml`（生产环境），配置数据源与 Redis 连接信息：

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/medllm?useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&characterEncoding=utf8
    username: your_username
    password: your_password
  data:
    redis:
      host: localhost
      port: 6379
```

同时确保 `ai.api.url` 指向 Python FastAPI 服务地址（默认 `http://localhost:8000`）。

#### 前端服务配置

前端通过 Vite 代理转发请求至后端，默认配置已在 `vite.config.js` 中完成，通常无需额外修改。

### 3. 初始化启动

#### 第一步：启动模型服务 (Model)

将脑卒中相关的医学指南 PDF 文件统一放入 `model/data/documents/` 文件夹，然后启动服务。系统首次运行会自动触发递归分块并进行 **AI Batch QA 衍生**，自动构建高频词 BM25 内存索引和 ChromaDB 向量索引。

```bash
cd model

# Windows
start.bat
# 或直接运行
python app/main.py

# Linux/Mac
bash start.sh
```

服务默认监听 `0.0.0.0:8000`。

#### 第二步：启动后端服务 (Backend)

使用 IDE（如 IntelliJ IDEA）运行 `MyServerApplication.java`，或者使用 Maven 编译启动：

```bash
cd backend/ai/MyServer
mvn spring-boot:run
```

服务默认监听 `8080` 端口。

#### 第三步：启动前端服务 (Frontend)

```bash
cd frontend
npm install
npm run dev
```

前端默认在 `localhost:5173` 启动，并自动代理请求至后端的响应端口。

### 4. 启动顺序总结

```text
① MySQL + Redis  →  ② Model (FastAPI :8000)  →  ③ Backend (Spring Boot :8080)  →  ④ Frontend (Vite :5173)
```

---

## 📝 核心 API 契约

### 1. 临床决策推理流（SSE 长连接）

- **路径**：`/model/get_result`
- **协议**：SSE (Server-Sent Events)
- **请求类型**：`POST`（由 Java WebFlux 转发并保持长连接流）
- **Payload**：

```json
{
  "question": "患者男，65岁，突发左侧肢体无力3小时，NIHSS评分12分，CT排除脑出血。如何处理？",
  "all_info": "既往史：高血压10年，糖尿病5年",
  "token": "your-jwt-token",
  "report_mode": "emergency",
  "show_thinking": true
}
```

- **响应格式**：流式持续输出包含 `thinking` 思考过程节点以及带有权威指南文献明确定位（如：*《中国急性缺血性脑卒中诊治指南》P42*）的结构化报告文本流。

### 2. 独立风险归纳（非检索极速模式）

- **路径**：`/ai/analyze`
- **请求类型**：`POST`
- **Payload**：

```json
{
  "case_text": "患者完整病历描述...",
  "token": "your-jwt-token"
}
```

- **响应格式**：快速返回风险分级评估 JSON：

```json
{
  "riskLevel": "high",
  "suggestion": "建议立即进行影像学检查",
  "analysisDetails": "..."
}
```

### 3. PubMed 文献检索

- **路径**：`/model/pubmed/search`
- **请求类型**：`POST`
- **Payload**：

```json
{
  "query": "acute ischemic stroke thrombolysis",
  "max_results": 10
}
```

- **响应格式**：包含文献标题、作者、摘要、链接等信息。

---

## ⚠️ 免责声明

*本系统属于临床辅助决策参考系统（CDSS），系统生成的输出结果不代表最终临床诊断，亦不能替代专业医生的独立医学判断。最终诊疗决策必须由执业医师根据患者实际临床体征做出。*
