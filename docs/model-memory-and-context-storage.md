# 模型记忆力机制与上下文存储

## 一、总体架构

本系统采用 **Java 后端 + Python 模型层** 双层架构，记忆力机制横跨两层协同工作：

```
┌─────────────────────────────────────────────────────────────┐
│                      Java 后端 (Spring Boot)                 │
│                                                              │
│  PatientMemoryService ──构建──▶ 三级患者记忆 Map              │
│  ConversationPersistenceService ──持久化──▶ 对话消息 (cont表)  │
│  AIStreamingServiceImpl ──组装请求──▶ 发往 Python 模型层       │
│  Redis 缓存 ──暂存──▶ 流式响应内容 / 对话历史                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP SSE
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python 模型层 (FastAPI + LangGraph)        │
│                                                              │
│  MemoryNode ──激活──▶ 分层记忆 → active_memory               │
│  AnalysisNode ──融合──▶ active_memory + case_text → 结构化   │
│  ConversationSummaryService ──滑动窗口摘要──▶ all_info 更新   │
│  LangGraph MemorySaver ──检查点──▶ 状态持久化 / 断点续传      │
│  ClinicalState ──流转──▶ 全局状态字典                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、三级患者记忆体系

### 2.1 记忆分层定义

系统采用认知科学中的 **短期记忆 / 情景记忆 / 语义记忆** 三级分层模型，在 Java 端由 `PatientMemoryService` 构建，在 Python 端由 `MemoryNode` 激活。

| 记忆层级 | 含义 | 数据来源 | 字符上限 |
|---------|------|---------|---------|
| **short_term** (短期记忆) | 当前对话的近期上下文 | 当前对话历史文本 (`recentConversation`) | 4,000 |
| **episodic** (情景记忆) | 患者历史事件片段 | 最近5条健康数据 + 最近5条AI评估 | 3,000 |
| **semantic** (语义记忆) | 患者稳定的背景知识 | 患者病史 (`history`) + 医生备注 (`notes`) | 2,000 |

### 2.2 Java 端构建流程

**核心类**: [PatientMemoryService.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/service/impl/PatientMemoryService.java)

```
build(doctorId, patientId, talkId, recentConversation)
  │
  ├── 权限校验：患者必须属于当前医生
  │
  ├── short_term = resolveShortTermMemory(...)
  │     ├── 校验 talk 归属（talk.patientId 必须匹配请求的 patientId）
  │     ├── 首次对话自动绑定 patientId 到 talk 记录
  │     └── 取 recentConversation 末尾 4000 字符（tail 截断）
  │
  ├── episodic = buildEpisodicMemory(patientId)
  │     ├── 查询 health_data 表最近 5 条 → "历史健康数据：..."
  │     ├── 查询 ai_opinion 表最近 5 条 → "历史AI评估（风险等级）：..."
  │     └── 拼接后截断至 3000 字符
  │
  └── semantic = buildSemanticMemory(patient)
        ├── patient.history → "稳定病史：..."
        ├── patient.notes → "医生备注：..."
        └── 拼接后截断至 2000 字符
```

**安全约束**:
- 同一对话不允许切换患者（`talk.patientId` 一旦绑定不可更改）
- 旧对话无 `patientId` 且已有内容时，拒绝绑定，要求新建对话
- 所有权限异常抛出 `PatientContextException`，前端展示明确提示

### 2.3 Python 端激活流程

**核心类**: [memory_node.py](file:///D:/CompetitionProject/stroke-multi-agent-system/model/app/agents/orchestrators/nodes/memory_node.py)

`MemoryNode` 接收 Java 传入的 `patient_memory` 字典，执行以下处理：

1. **归一化**: 将三级记忆的空值统一为空字符串
2. **兜底逻辑**: 若短期记忆为空且无分层记忆，则用 `all_info`（历史对话摘要）填充短期记忆
3. **截断压缩**: 对每级记忆分别截断（短期 2600 / 情景 2200 / 语义 1600），使用中间省略式截断
4. **格式化输出**: 生成 `active_memory` 字符串，格式为：
   ```
   【短期记忆】
   ...内容...

   【情景记忆】
   ...内容...

   【语义记忆】
   ...内容...
   ```
5. 若所有层级均为空，输出 `"无患者历史记忆"`

`active_memory` 随后被 `AnalysisNode` 消费，融入病例结构化分析的上下文。

---

## 三、对话上下文摘要（滑动窗口机制）

### 3.1 核心类

[context_summary.py](file:///D:/CompetitionProject/stroke-multi-agent-system/model/app/utils/context_summary.py) — `ConversationSummaryService`

### 3.2 工作机制

系统维护一个 `all_info` 字符串，代表跨轮对话的累积上下文摘要。每轮对话结束后，通过 **滑动窗口** 策略决定是直接拼接还是触发 LLM 摘要归纳：

```
update_all_info(previous_all_info, question, answer, threshold=2000)
  │
  ├── 计算累计长度 = len(previous_all_info) + len(question) + len(answer)
  │
  ├── 累计长度 ≤ 2000 → 直接拼接（append_only）
  │     updated = previous_all_info + "\n\n" + "问：...\n答：..."
  │
  └── 累计长度 > 2000 → 触发滑动窗口摘要（sliding_window_trigger）
        │
        └── summarize_context(previous_all_info, question, answer)
              │
              └── 调用 LLM (qwen-turbo) 合并旧摘要与本轮问答
                  要求：只保留对后续问诊有帮助的信息
                       优先保留：主诉、症状演变、检查结果、重要病史、
                                  危险因素、处理建议、随访建议
                       输出 3-6 条中文要点
```

### 3.3 对话价值评分（历史功能，当前已简化）

原始设计中包含 `score_turn_value()` 方法，通过 LLM 或启发式规则评估每轮问答的医学价值（0.0-1.0 分），仅高价值轮次才触发摘要合并。当前版本已简化为基于长度阈值的滑动窗口策略，不再逐轮评分。

### 3.4 数据流

```
Java AIStreamingServiceImpl.streamChat()
  │
  ├── 构建 historyText = buildHistoryContext(userId, talkId)  // 从 cont 表读取
  │
  ├── 请求体: { all_info: historyText, patient_memory: {...}, ... }
  │
  └── 发送至 Python /model/get_result
        │
        ├── Python 推理完成后返回 done 事件，携带 updated_all_info
        │
        └── Java 收到 done 事件后，将 updated_all_info 返回前端
            前端在下一轮对话时将此值作为 all_info 传回
```

**关键**: `all_info` 不在后端持久化存储，而是由前端在每轮对话结束后保存，并在下一轮请求时带回。这实现了无状态的上下文传递。

---

## 四、对话持久化存储

### 4.1 核心类

[ConversationPersistenceService.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/service/impl/ConversationPersistenceService.java)

### 4.2 存储模型

| 数据库表 | 实体类 | 用途 |
|---------|--------|------|
| `cont` | [Cont.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/po/uo/Cont.java) | 存储每条对话消息（用户问题 / AI回答） |
| `talk` | [Talk.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/pojo/Talk.java) | 对话会话元数据（标题、最新摘要、关联患者） |
| `patient` | [Patient.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/pojo/Patient.java) | 患者基本信息（病史、备注 → 语义记忆来源） |
| `health_data` | [HealthData.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/pojo/HealthData.java) | 患者健康数据（→ 情景记忆来源） |
| `ai_opinion` | [AiOpinion.java](file:///D:/CompetitionProject/stroke-multi-agent-system/backend/stroke-server/src/main/java/com/it/pojo/AiOpinion.java) | AI历史评估记录（→ 情景记忆来源） |

### 4.3 持久化流程

```
persistConversation(userId, talkId, question, answer, summary, title, images)
  │
  ├── 保存用户消息 (cont 表, role="user", 附带 images JSON)
  ├── 保存 AI 回答 (cont 表, role="assistant", images=null)
  │
  └── 更新 Talk 记录
        ├── 标题为"新对话"时 → 更新为生成的标题
        └── content 字段 → 存储摘要（summary）或回答（answer）
```

### 4.4 异步持久化与重试

在 `AIStreamingServiceImpl` 中，持久化操作被解耦为异步执行：

1. SSE 流完成后发出 `done` 事件
2. `doOnNext` 中检测到 `done` 事件后，在 `boundedElastic` 线程池异步执行持久化
3. 持久化失败时，将任务加入 Redis 重试队列 (`persist:retry:queue`)
4. 最多重试 3 次，超过后永久丢弃

### 4.5 历史上下文构建

```java
// AIStreamingServiceImpl.buildHistoryContext()
// 从 cont 表读取当前对话的所有历史消息，拼接为文本
// 限制最大 8000 字符 (MAX_HISTORY_CHARS)
```

历史上下文用于两个目的：
- 作为 `all_info` 传入 Python 模型层
- 作为 `recentConversation` 传入 `PatientMemoryService.build()` 构建短期记忆

---

## 五、LangGraph 状态管理与检查点

### 5.1 ClinicalState 全局状态

[ClinicalState](file:///D:/CompetitionProject/stroke-multi-agent-system/model/app/agents/core/schema.py) 是 LangGraph 图中所有节点共享的 TypedDict 状态，包含以下与记忆/上下文相关的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `case_text` | str | 用户当前输入 |
| `all_info` | str | 跨轮对话累积摘要 |
| `patient_memory` | Dict[str, str] | 三级患者记忆原始数据 |
| `active_memory` | str | 激活后的格式化记忆文本 |
| `context` | Dict | 病例结构化上下文 |
| `evidence` | str | 检索到的循证医学证据 |
| `proposal` | str | 综合方案 |
| `critique` | str | 风险审查 |
| `report` | str | 最终报告 |

### 5.2 MemorySaver 检查点

[ClinicalGraphBuilder](file:///D:/CompetitionProject/stroke-multi-agent-system/model/app/agents/orchestrators/clinical_graph.py) 使用 LangGraph 内置的 `MemorySaver` 作为检查点存储：

```python
self.checkpointer = MemorySaver()
# 编译图时注入
graph.compile(checkpointer=self.checkpointer)
```

- 每次请求生成唯一的 `thread_id`（UUID），确保请求间状态隔离
- 支持断点续传：图执行中断后可从最近检查点恢复
- 当前使用内存存储（`MemorySaver`），服务重启后状态丢失

### 5.3 节点流转中的记忆消费

```
intent → memory → analysis → research_plan → retrieve → evidence_judge
  │         │          │
  │         │          └── 消费 active_memory + all_info 融入病例分析
  │         └── 激活三级记忆，生成 active_memory
  └── 判断意图类型，路由到 memory（问诊）或 knowledge_answer（知识问答）
```

---

## 六、完整数据流时序

```
用户发送消息
    │
    ▼
Java AIStreamingServiceImpl.streamChat()
    │
    ├── 1. buildHistoryContext() → 从 cont 表读取对话历史 → historyText
    ├── 2. PatientMemoryService.build() → 构建 {short_term, episodic, semantic}
    ├── 3. 组装请求: {question, all_info, patient_memory, ...}
    └── 4. HTTP POST → Python /model/get_result
          │
          ▼
Python FastAPI get_model_result()
    │
    ├── 5. QwenAgent.run_clinical_reasoning()
    │     ├── IntentNode: 判断意图
    │     ├── MemoryNode: 激活记忆 → active_memory
    │     ├── AnalysisNode: 融合 active_memory + case_text → 结构化上下文
    │     ├── ResearchPlanNode → RetrieveNode → EvidenceJudgeNode (Agentic RAG 循环)
    │     ├── ReasonNode → DebateNode → ConsensusNode (多专家会诊)
    │     ├── ValidateNode (双层校验 + 反思循环)
    │     └── ReportNode: 生成最终报告
    │
    ├── 6. ConversationSummaryService.update_all_info() → 滑动窗口摘要
    │
    └── 7. 返回 SSE 事件流 (token + node_done + done)
          │
          ▼
Java AIStreamingServiceImpl
    │
    ├── 8. 解析 SSE 事件，转发给前端
    ├── 9. done 事件触发异步持久化
    │     ├── persistConversation() → cont 表 + talk 表
    │     └── 失败时入 Redis 重试队列
    │
    └── 10. 前端保存 updated_all_info，下轮对话带回
```

---

## 七、关键设计决策总结

| 设计点 | 决策 | 原因 |
|--------|------|------|
| 记忆分层 | 短期/情景/语义三级 | 模拟人类认知过程，区分临时对话、历史事件、稳定知识 |
| all_info 存储 | 前端持有，不后端持久化 | 简化后端状态管理，避免额外存储表 |
| 摘要触发策略 | 长度阈值（2000字）滑动窗口 | 比逐轮评分更高效，减少 LLM 调用次数 |
| 对话-患者绑定 | talk.patientId 不可切换 | 防止记忆串患者，确保医疗安全 |
| 检查点存储 | 内存 MemorySaver | 当前单实例部署足够，后续可切换为持久化后端 |
| 持久化方式 | 异步 + Redis 重试队列 | 不阻塞 SSE 流关闭，保证用户体验 |
| 截断策略 | 中间省略式（保留首尾） | 在有限上下文窗口内保留最关键的首尾信息 |