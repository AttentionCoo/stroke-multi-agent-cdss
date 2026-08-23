"""阶段3 结构化输出 Schema。

关键节点(intent / evidence_router / research_plan)用 Pydantic 约束 LLM 输出,
配合 llm.with_structured_output() 消除"输出 JSON → 手写解析"的脆弱性。

设计原则:
- 硬路由字段用 Literal 严格校验(intent type), 校验失败自动回退文本解析路径;
- 其余字段保持宽松(evidence_type 等由节点内的 normalize 逻辑统一兜底);
- 所有字段带默认值, 模型漏字段不导致整体失败。
"""

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """意图分类结果: consultation(问诊) / knowledge(知识问答) / irrelevant(无关)。"""

    type: Literal["consultation", "knowledge", "irrelevant"] = Field(
        description="输入意图类型, 必须为三者之一"
    )
    reason: str = Field(default="", description="简要判断原因")


class EvidenceRoute(BaseModel):
    """单个检索查询的证据路由决策。"""

    query: str = Field(description="原检索查询, 必须与输入完全一致")
    evidence_type: str = Field(
        default="treatment",
        description="treatment/diagnosis/anatomy/etiology/prognosis/prevention",
    )
    target_categories: List[str] = Field(
        default_factory=list, description="目标知识类别: 指南/专家共识/规范/教材/其他"
    )
    keywords: List[str] = Field(
        default_factory=list, description="2-4 个医学标准检索关键词"
    )


class EvidenceRoutes(BaseModel):
    """Evidence Router 输出: 每个查询一条路由。"""

    routes: List[EvidenceRoute] = Field(default_factory=list)


class DecisionItem(BaseModel):
    """临床决策节点(Decision Planner 核心输出)。"""

    # 决策唯一标识(如 "AIS_IVT_001")
    decision_id: str = ""
    # 决策名称(如 "是否进行静脉溶栓")
    decision_name: str
    # 决策类型: diagnosis/treatment/anatomy/etiology/prognosis/prevention
    decision_type: str = "treatment"
    # 病例中支持该决策的客观事实(只写真实存在的事实, 不得编造检查结果)
    patient_evidence: List[str] = Field(default_factory=list)
    # 影响该决策、但病例中缺失/不明确的信息
    uncertainty: List[str] = Field(default_factory=list)
    # 支撑该决策所需的指南/证据名称(如 "AHA卒中指南")
    required_evidence: List[str] = Field(default_factory=list)
    # 空串 → 节点 normalize 逻辑回退到 decision_type(保持既有语义)
    evidence_type: str = ""
    # 证据来源(如 AHA/ESO guideline、RCT)
    evidence_source: List[str] = Field(default_factory=list)
    # 优先级 1-10: 时间敏感性×生命危险×治疗获益, 数值越大越紧急(默认 5 为中等)
    priority: int = 5
    # PICO 结构化检索式(Population/Intervention/Comparison/Outcome)
    pico: Dict = Field(default_factory=dict)
    # 可直接检索的英文专业查询(含疾病实体+干预+时间窗/人群)
    search_query: List[str] = Field(default_factory=list)


class RetrievalTask(BaseModel):
    """面向临床决策的检索任务。"""

    # 面向该决策的临床问题
    question: str = ""
    # 由 PICO 生成的英文标准术语检索式
    query: str


class ResearchPlanResult(BaseModel):
    """决策规划输出。"""

    # 是否需要检索(常识性/已明确问题置 False 跳过检索)
    need_retrieve: bool = True
    # 影响决策但病例中缺失的信息
    missing_information: List[str] = Field(default_factory=list)
    # 临床决策节点列表(按优先级从高到低排列)
    clinical_decisions: List[DecisionItem] = Field(default_factory=list)
    # 面向各决策的检索任务
    retrieval_tasks: List[RetrievalTask] = Field(default_factory=list)
    # 同义词/指南术语/疾病实体扩展查询
    expanded_queries: List[str] = Field(default_factory=list)
    # 用于 HyDE 向量检索的假设文档(不得虚构患者事实)
    hypothetical_document: str = ""


class HumanReviewDecision(BaseModel):
    """医生复核决定(HITL resume 载荷)。"""

    approved: bool = Field(description="是否批准会诊结论")
    feedback: str = Field(default="", description="驳回时的修改意见, 会反馈给专家重新会诊")
