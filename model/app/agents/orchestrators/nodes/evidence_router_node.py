"""Evidence Router Agent — 临床决策 → 证据检索路由。

在 Decision Planner 与 Retriever 之间,用 LLM 判断每个检索查询:
- evidence_type: 证据类型(treatment/diagnosis/anatomy/etiology/prognosis/prevention)
- target_categories: 目标知识类别(指南/专家共识/规范/教材/其他)
- keywords: 应注入的检索关键词(医学标准术语)

比规则映射更智能:LLM 能理解查询的临床意图并选择正确的证据源。
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.utils.json_utils import parse_json_output

logger = logging.getLogger(__name__)

# 证据类型 → 允许的类别(规则兜底)
EVIDENCE_TYPE_CATEGORIES = {
    "treatment": ["指南", "专家共识", "规范"],
    "diagnosis": ["指南", "专家共识", "规范"],
    "etiology": ["指南", "专家共识"],
    "anatomy": ["教材"],
    "prognosis": ["指南", "专家共识"],
    "prevention": ["指南", "专家共识", "规范"],
}

# 全部可用类别
ALL_CATEGORIES = ["指南", "专家共识", "规范", "教材", "其他"]


class EvidenceRouterNode(BaseNode):
    """判断每个检索查询应路由到哪类证据源。"""

    def __init__(self, llm):
        self.llm = llm

    async def run(self, state: ClinicalState) -> Dict:
        queries = [str(q).strip() for q in state.get("retrieval_queries", []) if str(q).strip()]
        if not queries:
            return {"router_evidence_types": [], "router_categories": [], "router_keywords": [], "router_routes": []}

        decisions = state.get("clinical_decisions", [])
        decisions_text = "\n".join(
            f"- [{d.get('priority', '?')}] {d.get('decision_name', '')} ({d.get('decision_type', '')})"
            for d in decisions[:5] if isinstance(d, dict)
        ) or "无"

        prompt = f"""你是医学证据路由专家。判断每个检索查询应该检索哪类医学证据源。

【临床决策节点】
{decisions_text}

【检索查询】
{json.dumps(queries, ensure_ascii=False)}

可用知识类别: {ALL_CATEGORIES}
证据类型: treatment / diagnosis / anatomy / etiology / prognosis / prevention

对每个查询,判断:
- evidence_type: 该查询属于哪类临床决策
- target_categories: 应从哪些知识类别检索(治疗/诊断/病因→指南共识规范; 解剖定位→教材; 未知→全部)
- keywords: 应附加的2-4个医学标准检索关键词(如 alteplase、mechanical thrombectomy、TOAST classification)

只输出 JSON:
{{
  "routes": [
    {{"query": "原查询", "evidence_type": "treatment", "target_categories": ["指南"], "keywords": ["alteplase", "thrombolysis"]}}
  ]
}}
query 必须与输入完全一致。"""

        data = None
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是严谨的医学证据路由专家,只根据查询的临床意图路由,不编造。"),
                HumanMessage(content=prompt),
            ])
            data = parse_json_output(getattr(response, "content", ""), None)
        except Exception as exc:
            logger.warning("Evidence Router 调用失败,使用规则兜底: %s", exc)

        routes = self._normalize_routes(data, queries, decisions)
        return {
            "router_evidence_types": [r["evidence_type"] for r in routes],
            "router_categories": [r["target_categories"] for r in routes],
            "router_keywords": [r["keywords"] for r in routes],
            "router_routes": routes,
        }

    def _normalize_routes(self, data, queries: List[str], decisions: List[Dict]) -> List[Dict]:
        """规范化路由结果;LLM 失败时用规则兜底(决策 evidence_type → 类别)。"""
        routes = []
        # 决策 → 默认 evidence_type 映射(按查询顺序)
        decision_types = [str(d.get("evidence_type", "")).strip() for d in decisions if isinstance(d, dict)]

        if isinstance(data, dict) and isinstance(data.get("routes"), list):
            seen = set()
            for i, item in enumerate(data["routes"]):
                if not isinstance(item, dict):
                    continue
                q = str(item.get("query", "") or "").strip()
                # 匹配输入查询
                if i < len(queries):
                    q = queries[i]
                elif q not in queries:
                    continue
                if q in seen:
                    continue
                seen.add(q)
                ev_type = str(item.get("evidence_type", "") or "").strip().lower()
                cats = item.get("target_categories")
                if not isinstance(cats, list) or not cats:
                    cats = EVIDENCE_TYPE_CATEGORIES.get(ev_type, ALL_CATEGORIES)
                cats = [c for c in cats if c in ALL_CATEGORIES] or EVIDENCE_TYPE_CATEGORIES.get(ev_type, ALL_CATEGORIES)
                kws = item.get("keywords")
                if not isinstance(kws, list):
                    kws = []
                routes.append({
                    "query": q,
                    "evidence_type": ev_type if ev_type in EVIDENCE_TYPE_CATEGORIES else "treatment",
                    "target_categories": cats,
                    "keywords": [str(k) for k in kws if str(k).strip()][:4],
                })

        # 补齐缺失查询(LLM 未覆盖的)
        routed_queries = {r["query"] for r in routes}
        for i, q in enumerate(queries):
            if q in routed_queries:
                continue
            ev_type = decision_types[i] if i < len(decision_types) else "treatment"
            if ev_type not in EVIDENCE_TYPE_CATEGORIES:
                ev_type = "treatment"
            routes.append({
                "query": q,
                "evidence_type": ev_type,
                "target_categories": EVIDENCE_TYPE_CATEGORIES[ev_type],
                "keywords": [],
            })
        return routes
