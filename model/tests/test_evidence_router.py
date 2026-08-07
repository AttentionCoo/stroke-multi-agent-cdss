"""Evidence Router Agent 测试(mock LLM)"""
import sys
import asyncio
import json

sys.path.insert(0, ".")

from app.agents.orchestrators.nodes.evidence_router_node import EvidenceRouterNode


class _FakeRouterLLM:
    async def ainvoke(self, messages):
        return type("R", (), {"content": json.dumps({
            "routes": [
                {"query": "是否静脉溶栓", "evidence_type": "treatment",
                 "target_categories": ["指南", "专家共识"], "keywords": ["alteplase", "thrombolysis"]},
                {"query": "左MCA定位", "evidence_type": "anatomy",
                 "target_categories": ["教材"], "keywords": ["MCA syndrome", "aphasia"]},
            ]
        })})


class _EmptyLLM:
    async def ainvoke(self, messages):
        return type("R", (), {"content": "bad json"})


async def main():
    # LLM 正常路由
    node = EvidenceRouterNode(llm=_FakeRouterLLM())
    state = {
        "retrieval_queries": ["是否静脉溶栓", "左MCA定位"],
        "clinical_decisions": [],
    }
    r = await node.run(state)
    print("router_evidence_types:", r["router_evidence_types"])
    print("router_categories:", r["router_categories"])
    print("router_keywords:", r["router_keywords"])
    assert r["router_evidence_types"] == ["treatment", "anatomy"]
    assert r["router_categories"][0] == ["指南", "专家共识"]
    assert r["router_categories"][1] == ["教材"]
    print("ROUTER_LLM_OK")

    # LLM 失败 → 规则兜底
    node2 = EvidenceRouterNode(llm=_EmptyLLM())
    state2 = {
        "retrieval_queries": ["是否溶栓"],
        "clinical_decisions": [{"decision_name": "溶栓", "evidence_type": "treatment", "priority": 10}],
    }
    r2 = await node2.run(state2)
    print("fallback evidence_type:", r2["router_evidence_types"])
    assert r2["router_evidence_types"] == ["treatment"]
    assert r2["router_categories"][0] == ["指南", "专家共识", "规范"]
    print("ROUTER_FALLBACK_OK")


if __name__ == "__main__":
    asyncio.run(main())
