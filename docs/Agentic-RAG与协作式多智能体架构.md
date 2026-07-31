# Agentic RAG 与协作式多智能体架构

## 一、升级目标

本次升级解决四个问题：检索查询过于直接、证据充分性不可判断、专家只并行输出而不协作、患者历史上下文随对话增长。主管线保持原有 `POST /model/get_result` 与 SSE 契约兼容，新增字段均为可选字段。

## 二、临床问诊状态图

```text
Intent
  ├─ irrelevant ─────────────────────────────────────────► Reject
  ├─ knowledge ──────────────────────────────────────────► KnowledgeAnswer
  └─ consultation
        │
        ▼
      Memory ─► Analysis ─► ResearchPlan ─► Retrieve ─► EvidenceJudge
                                                     ▲          │
                                                     │          ├─ 不足且未达上限
                                                     └─ Rewrite ┘
                                                                │
                                                                ▼
                  Report ◄─ Validate ◄─ Consensus ◄─ Debate ◄─ Reason
                              │                       ▲
                              └─ retry ───────────────┘
```

状态图包含两个有界循环：

1. 检索循环：证据不足时改写查询并再次检索，默认最多两轮。
2. 会诊反思循环：规则或 LLM 质控未通过时，携带反馈重新生成专家意见并再次辩论。

## 三、Agentic RAG

`ResearchPlanNode` 根据病例、结构化信息、临床问题和患者记忆生成：

- `retrieval_tasks`：临床任务与检索式的一一映射；
- `retrieval_queries`：中英文指南术语、疾病实体、检查名和禁忌证扩展查询；
- `hypothetical_document`：不虚构患者事实的 HyDE 医学描述，并固定保留一个检索槽位；
- `missing_information`：影响决策但病例尚未提供的信息。

检索结果使用 `R{轮次}-Q{查询序号}-E{证据序号}` 编号。`EvidenceJudgeNode` 从相关性、来源可信度、时效性和问题覆盖度评估 `evidence_quality`。低于阈值时，`QueryRewriteNode` 根据证据缺口生成未检索过的新查询；没有新查询时立即停止，避免空转。

## 四、协作式多智能体

多专家会诊分为三个阶段：

| 阶段 | 节点 | 行为 |
|---|---|---|
| 独立意见 | `ReasonNode` | 全科、神经专科和临床药师并行形成独立立场，区分患者事实、证据与不确定性 |
| 交叉质询 | `DebateNode` | 每位专家阅读全部同伴意见，指出同意点、冲突点、修正结论和人工确认项 |
| 主持人共识 | `ConsensusNode` | 中立主持人裁决分歧，生成 `CONSENSUS`、`PROPOSAL`、`CRITIQUE` |

专家和主持人只能引用实际检索结果中的证据编号。证据未覆盖的判断进入 `CRITIQUE`，不能被写成确定事实。

## 五、三级患者记忆

前端在医生选择关联患者后，将 `patientId` 随问诊请求发送给 Java 后端。`PatientMemoryService` 校验患者所属医生后构建：

| 记忆层 | 数据来源 | 默认上限 |
|---|---|---:|
| 短期记忆 `short_term` | 当前对话最近内容 | 4000 字符 |
| 情景记忆 `episodic` | 最近健康数据与历史 AI 评估事件 | 3000 字符 |
| 语义记忆 `semantic` | 稳定病史与医生备注 | 2000 字符 |

Python `MemoryNode` 再次按层限制长度，生成本轮 `active_memory`。未选择患者时后端传入空记忆；显式选择的患者不存在、不属于当前医生，或对话归属无法确认时，后端在调用模型前拒绝请求，不向模型泄露患者数据，也不写入本轮消息。

AI 评估按事件追加保存，患者详情仍读取最新一条；历史记录不会再被新评估覆盖。短期记忆只在空对话首次关联患者时建立作用域，并通过 `talk.patient_id` 持久化。关联写入使用“仅当未绑定时更新”的原子条件；同一对话改选其他患者会在模型调用和消息持久化前被拒绝，用户需新建对话。Flyway 迁移 `V2__add_patient_id_to_talk.sql` 负责为既有数据库增加该字段和索引。

## 六、新增状态字段

```python
patient_memory: dict[str, str]
active_memory: str
retrieval_tasks: list[dict]
retrieval_queries: list[str]
retrieved_queries: list[str]
hypothetical_document: str
need_retrieve: bool
evidence_quality: float
evidence_assessment: str
missing_information: list[str]
retrieval_round: int
expert_opinions: dict[str, str]
debate_transcript: str
consensus: str
```

## 七、安全边界

- 禁忌证规则只匹配病例、结构化上下文和患者记忆中的患者事实，不扫描指南证据中的通用禁忌证清单。
- `未见`、`未发现`、`无`、`否认`、`排除`等明确否定表达不会触发对应阳性禁忌证规则。
- 患者记忆加载受医生归属校验约束。
- 检索循环与反思循环均有次数上限。
- 系统输出仍是临床辅助信息，不能替代医生判断。

## 八、可观察事件

新增阶段会沿原 SSE 链路显示：`memory`、`research_plan`、`evidence_judge`、`query_rewrite`、`debate`、`consensus_agent`。Java 继续把 Python 的 `node_start` / `node_done` 映射为前端 `thinking` 事件，因此前端无需解析模型内部状态。
