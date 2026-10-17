"""Evidence Router Agent 测试(mock LLM)"""
import sys
import asyncio
import json

sys.path.insert(0, ".")

from app.agents.orchestrators.nodes.evidence_router_node import EvidenceRouterNode


class _FakeRouterLLM:
    _content = json.dumps({
        "routes": [
            {"query": "是否静脉溶栓", "evidence_type": "treatment",
             "target_categories": ["指南", "专家共识"], "keywords": ["alteplase", "thrombolysis"]},
            {"query": "左MCA定位", "evidence_type": "anatomy",
             "target_categories": ["教材"], "keywords": ["MCA syndrome", "aphasia"]},
        ]
    })

    async def ainvoke(self, messages):
        return type("R", (), {"content": self._content})

    async def astream(self, messages):
        yield type("R", (), {"content": self._content})


class _EmptyLLM:
    async def ainvoke(self, messages):
        return type("R", (), {"content": "bad json"})

    async def astream(self, messages):
        yield type("R", (), {"content": "bad json"})


async def main():
    # LLM 正常路由
    node = EvidenceRouterNode(llm=_FakeRouterLLM())
    state = {
        "retrieval_queries": ["是否静脉溶栓", "左MCA定位"],
        "clinical_decisions": [],
    }
    r = await node.run(state)
    print("路由证据类型:", r["router_evidence_types"])
    print("路由类别:", r["router_categories"])
    print("路由关键词:", r["router_keywords"])
    assert r["router_evidence_types"] == ["treatment", "anatomy"]
    assert r["router_categories"][0] == ["指南", "专家共识"]
    assert r["router_categories"][1] == ["教材"]
    print("路由 LLM 调用通过")

    # LLM 失败 → 规则兜底
    node2 = EvidenceRouterNode(llm=_EmptyLLM())
    state2 = {
        "retrieval_queries": ["是否溶栓"],
        "clinical_decisions": [{"decision_name": "溶栓", "evidence_type": "treatment", "priority": 10}],
    }
    r2 = await node2.run(state2)
    print("兜底证据类型:", r2["router_evidence_types"])
    assert r2["router_evidence_types"] == ["treatment"]
    assert r2["router_categories"][0] == ["指南", "专家共识", "规范"]
    print("路由兜底路径通过")


if __name__ == "__main__":
    asyncio.run(main())
