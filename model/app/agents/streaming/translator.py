"""LangGraph 流事件 → SSE 思考链事件翻译器(从 qwen_agent.py 拆出, 单一职责)。

职责: 把 astream 三流(updates/messages/custom)的原始 chunk 翻译成
前端思考面板消费的事件(node_start/node_token/node_done/node_stats/token),
并负责节点实时缓冲、全文渲染与摘要生成。
"""

import json
import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

_NODE_DISPLAY: Dict[str, Dict[str, str]] = {
    "intent": {"running": "正在判断问题类型...", "done": "问题类型判断"},
    "reject": {"running": "正在处理回复...", "done": "请求处理"},
    "memory": {"running": "正在激活患者分层记忆...", "done": "患者分层记忆"},
    "analysis": {"running": "正在分析病例结构...", "done": "病例结构化分析"},
    "tool_use": {"running": "正在调用脑卒中医疗工具...", "done": "医疗工具调用"},
    "research_plan": {"running": "正在规划循证检索任务...", "done": "主动检索规划"},
    "evidence_router": {"running": "正在路由证据类型...", "done": "证据路由"},
    "retrieve": {"running": "正在检索循证医学证据...", "done": "循证医学证据检索"},
    "evidence_judge": {"running": "正在评估证据充分性...", "done": "证据质量评估"},
    "query_rewrite": {"running": "正在改写医学检索式...", "done": "医学查询重写"},
    "reason": {"running": "正在生成专家独立意见...", "done": "多专家独立推理"},
    "debate": {"running": "正在进行专家交叉质询...", "done": "多专家交叉质询"},
    "consensus_agent": {"running": "正在形成会诊共识...", "done": "会诊主持人共识"},
    "validate": {"running": "正在进行校验反思...", "done": "安全校验与反思"},
    "compliance": {"running": "正在执行合规审计...", "done": "合规审计"},
    "human_review": {"running": "等待医生复核结论...", "done": "医生复核"},
    "generate_report": {"running": "正在生成临床报告...", "done": "临床报告生成"},
    "knowledge_answer": {"running": "正在回答知识问题...", "done": "医学知识回答"},
}

_INTENT_LABELS: Dict[str, str] = {
    "consultation": "临床问诊",
    "knowledge": "医学知识问答",
    "irrelevant": "非脑卒中医疗问题",
}


class StreamEventTranslator:
    """把 LangGraph 三流 chunk 翻译为前端思考链事件。

    纯函数式设计: 除 _live_buffers(节点实时缓冲)外不持有跨请求状态,
    每次推理前由调用方重置 _live_buffers。
    """

    _STREAMING_NODES = {"knowledge_answer", "generate_report"}

    def __init__(self):
        # 各节点实时生成缓冲: {node: {expert_or_node: 累计文本}}, 供思考链实时打印
        self._live_buffers: dict = {}

    @staticmethod
    def _node_stats_event(node: str, output: dict) -> Dict | None:
        """检索质量看板: 为 retrieve/evidence_judge 生成结构化指标事件。"""
        if not isinstance(output, dict):
            return None
        if node == "retrieve":
            evidence = str(output.get("evidence", "") or "")
            items = re.findall(r"【证据\s+([^】]+)】", evidence)
            sources = {}
            categories = {}
            for head in items:
                m_src = re.search(r"来源:\s*([^\]\s]+?)(?:\.pdf|\.PDF)?\s*(?:p\.?\d*)?", head)
                m_cat = re.search(r"类别:\s*(\S+)", head)
                if m_src:
                    src = m_src.group(1).strip().rstrip(".")
                    sources[src] = sources.get(src, 0) + 1
                if m_cat:
                    cat = m_cat.group(1).strip()
                    categories[cat] = categories.get(cat, 0) + 1
            stats = {
                "round": int(output.get("retrieval_round", 0) or 0),
                "evidence_count": len(items),
                "unique_sources": len(sources),
                "source_distribution": sources,
                "category_distribution": categories,
            }
            return {"type": "node_stats", "node": node, "stats": stats}
        if node == "evidence_judge":
            missing = output.get("missing_information", [])
            stats = {
                "quality": round(float(output.get("evidence_quality", 0.0) or 0.0), 2),
                "need_retrieve": bool(output.get("need_retrieve", False)),
                "missing_count": len(missing) if isinstance(missing, list) else 0,
            }
            return {"type": "node_stats", "node": node, "stats": stats}
        return None

    def _render_live(self, node: str, buf: dict) -> str:
        """把实时缓冲区渲染为当前节点生成中的快照文本。"""
        parts = []
        for key, text in buf.items():
            if key == "__node__":
                parts.append(text)
            else:
                parts.append(f"▶ 【{key}】(实时生成中)\n{text}")
        return "\n\n".join(parts)

    def _on_custom_event(
        self,
        chunk,
        show_thinking: bool,
        started_nodes: set,
    ) -> list[Dict]:
        """处理各节点经 stream_writer 写入的实时生成过程(custom 流)。

        payload = {"node": 节点名, "chunk": 增量文本, "expert": 可选专家标签}
        → 累加进实时缓冲, 输出 node_token 快照事件(前端对运行中步骤做增量替换显示)。
        """
        payload = chunk
        if isinstance(chunk, tuple) and len(chunk) == 2 and isinstance(chunk[0], dict):
            payload = chunk[0]  # langgraph 某些版本以 (payload, metadata) 形式产出
        if not isinstance(payload, dict) or not payload.get("chunk"):
            return []
        node = str(payload.get("node", "") or "")
        if node not in _NODE_DISPLAY:
            return []
        text = str(payload["chunk"])
        expert = payload.get("expert")
        buf = self._live_buffers.setdefault(node, {})
        key = str(expert) if expert else "__node__"
        buf[key] = buf.get(key, "") + text
        snapshot = self._render_live(node, buf)

        translated = []
        if show_thinking and node not in started_nodes:
            started_nodes.add(node)
            translated.append({
                "type": "node_start",
                "node": node,
                "label": _NODE_DISPLAY[node]["running"],
                "status": "running",
            })
        translated.append({
            "type": "node_token",
            "node": node,
            "label": _NODE_DISPLAY[node]["running"],
            "content": snapshot,
            "status": "running",
        })
        return translated

    def _on_message_chunk(
        self,
        chunk,
        show_thinking: bool,
        started_nodes: set,
        streamed_nodes: set,
    ) -> list[Dict]:
        """处理 LLM token 流(对应旧版 on_chat_model_stream)。

        chunk = (message_chunk, metadata); metadata.langgraph_node 标识来源节点。
        """
        message_chunk, metadata = chunk
        langgraph_node = metadata.get("langgraph_node", "")
        if langgraph_node not in self._STREAMING_NODES:
            return []

        content = getattr(message_chunk, "content", "") or ""
        if isinstance(content, list):
            # OpenAI 兼容协议返回 content block 列表时拼接文本
            content = "".join(str(getattr(b, "text", "") or "") for b in content)
        if not content:
            return []

        translated = []
        if show_thinking and langgraph_node not in started_nodes:
            started_nodes.add(langgraph_node)
            translated.append({
                "type": "node_start",
                "node": langgraph_node,
                "label": _NODE_DISPLAY[langgraph_node]["running"],
                "status": "running",
            })
        streamed_nodes.add(langgraph_node)
        translated.append({"type": "token", "content": content})
        return translated

    def _on_node_updates(
        self,
        updates: dict,
        show_thinking: bool,
        started_nodes: set,
        streamed_nodes: set,
    ) -> list[Dict]:
        """处理节点完成事件(对应旧版 on_chain_end)。updates = {node_name: node_output}。"""
        translated: list[Dict] = []
        for name, output in updates.items():
            if name not in _NODE_DISPLAY:
                continue

            # 人工复核节点仅在真实发生复核(有 review_decision)时进入思考链,
            # 未开启 HITL 的直通执行不产生多余步骤
            if name == "human_review" and not (isinstance(output, dict) and output.get("review_decision")):
                continue

            logger.info(f"[event] 节点完成: {name}, 输出类型: {type(output)}")
            if isinstance(output, dict) and "report" in output:
                logger.info(f"[event] 节点 {name} 报告长度: {len(output['report'])}")

            # updates 模式没有节点开始事件, 节点首次完成时补发 node_start
            if show_thinking and name not in started_nodes:
                started_nodes.add(name)
                translated.append({
                    "type": "node_start",
                    "node": name,
                    "label": _NODE_DISPLAY[name]["running"],
                    "status": "running",
                })

            translated.append(self._node_done_event(name, output))

            # 节点完成后清空其实时缓冲(反思回环再次执行时重新实时积累)
            self._live_buffers.pop(name, None)

            # ── 检索质量看板: retrieve/evidence_judge 输出结构化指标 ──
            stats_event = self._node_stats_event(name, output)
            if stats_event:
                translated.append(stats_event)

            # tool_use 节点:将每次工具调用展开为独立步骤事件,前端可逐条展示
            if name == "tool_use" and isinstance(output, dict):
                tool_calls = output.get("tool_calls", []) or []
                for i, call in enumerate(tool_calls[:10]):  # 防止刷屏,最多展示 10 次
                    if not isinstance(call, dict):
                        continue
                    tool_name = call.get("tool", "未知工具")
                    args = call.get("arguments", {}) or {}
                    result = call.get("result", {}) or {}
                    translated.append({
                        "type": "node_done",
                        "node": f"tool_call_{i}",
                        "label": f"工具调用: {tool_name}",
                        "summary": (
                            f"参数: {self._short_text(json.dumps(args, ensure_ascii=False), 200)}\n"
                            f"结果: {self._short_text(json.dumps(result, ensure_ascii=False), 300)}"
                        ),
                        "status": "done",
                    })

            needs_fallback_token = name == "reject" or (
                name in self._STREAMING_NODES and name not in streamed_nodes
            )
            report_text = output.get("report", "") if isinstance(output, dict) else ""
            if needs_fallback_token and report_text:
                logger.info(f"[event] 节点 {name} 输出报告内容，长度: {len(report_text)}")
                streamed_nodes.add(name)
                translated.append({"type": "token", "content": report_text})
        return translated

    def _node_done_event(self, node: str, output: dict) -> Dict:
        """构造节点完成事件(含完整输出, 供思考链全文展示)。"""
        return {
            "type": "node_done",
            "node": node,
            "label": _NODE_DISPLAY[node]["done"],
            "summary": self._node_summary(node, output),
            "content": self._node_full_content(node, output),
            "status": "done",
        }

    @staticmethod
    def _format_output(value, indent: int = 0) -> str:
        """递归把节点输出渲染为可读多行文本(不截断), 供思考链全量打印。"""
        pad = "  " * indent
        if isinstance(value, dict):
            lines = []
            for k, v in value.items():
                key = str(k)
                if isinstance(v, (dict, list)) and v:
                    lines.append(f"{pad}■ {key}:")
                    lines.append(StreamEventTranslator._format_output(v, indent + 1))
                else:
                    lines.append(f"{pad}■ {key}: {v}")
            return "\n".join(lines)
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(StreamEventTranslator._format_output(item, indent))
                else:
                    lines.append(f"{pad}- {item}")
            return "\n".join(lines)
        return f"{pad}{value}"

    def _node_full_content(self, node: str, output: dict) -> str:
        """节点完整输出(思考链全文, 不截断), 供前端"全部打印"。"""
        if not isinstance(output, dict):
            return str(output)[:50000]

        if node == "retrieve":
            parts = [f"检索轮次: {output.get('retrieval_round', 0)}"]
            evidence = str(output.get("evidence", "") or "").strip()
            if evidence:
                parts.append("【检索证据全文】\n" + evidence)
            return "\n\n".join(parts)

        if node == "reason":
            parts = []
            # 每位专家的独立意见全文(不截断), 供前端思考链"全部打印"
            opinions = output.get("expert_opinions", {}) or {}
            for role, advice in opinions.items():
                if not advice:
                    continue
                parts.append(f"▶ 【{role}】独立意见全文:\n{advice}")
            # 兼容旧字段(未进入 expert_opinions 时兜底)
            legacy_map = {
                "generalist_advice": "全科医生",
                "specialist_advice": "神经专科医生",
                "pharmacist_advice": "临床药师",
            }
            for key, label in legacy_map.items():
                val = output.get(key, "")
                if val and not opinions.get(label):
                    parts.append(f"▶ 【{label}】独立意见全文:\n{val}")
            for key, label in (("proposal", "综合方案"), ("critique", "风险审查")):
                val = output.get(key, "")
                if val:
                    parts.append(f"▶ {label}:\n{val}")
            if parts:
                return "\n\n".join(str(p) for p in parts)

        if node == "debate":
            transcript = str(output.get("debate_transcript", "") or "").strip()
            if transcript:
                return "【交叉质询全文】\n" + transcript

        if node == "consensus_agent":
            parts = []
            for key, label in (("consensus", "会诊共识"), ("proposal", "综合方案"), ("critique", "风险审查")):
                val = str(output.get(key, "") or "").strip()
                if val:
                    parts.append(f"▶ {label}:\n{val}")
            if parts:
                return "\n\n".join(parts)

        if node == "tool_use":
            calls = output.get("tool_calls", []) or []
            if isinstance(calls, list) and calls:
                parts = []
                for i, call in enumerate(calls, 1):
                    if isinstance(call, dict):
                        parts.append(
                            f"▶ 工具调用 {i}: {call.get('tool', '未知')}\n"
                            f"  参数: {json.dumps(call.get('arguments', {}), ensure_ascii=False)}\n"
                            f"  结果: {json.dumps(call.get('result', {}), ensure_ascii=False)}"
                        )
                if parts:
                    return "\n\n".join(parts)

        if node == "generate_report" or node == "knowledge_answer":
            report = str(output.get("report", "") or "").strip()
            if report:
                return report

        if node == "reject":
            report = str(output.get("report", "") or "").strip()
            if report:
                return "【回复全文】\n" + report

        # 其余全部节点(intent/memory/analysis/research_plan/evidence_router/
        # evidence_judge/query_rewrite/validate 等): 递归渲染完整输出, 全部打印
        return "【节点完整输出】\n" + self._format_output(output)

    def _node_summary(self, node: str, output: dict) -> str:
        """生成适合通过 SSE 展示的节点结果摘要。"""
        if not isinstance(output, dict):
            output = {}

        summary = {}
        if node == "intent":
            intent_type = str(output.get("intent_type", ""))
            summary = {"判断结果": _INTENT_LABELS.get(intent_type, intent_type or "未知类型")}
        elif node == "memory":
            memory = output.get("patient_memory", {})
            summary = {
                "已激活记忆层": [
                    key for key, value in memory.items() if value
                ],
                "有效上下文": self._short_text(output.get("active_memory", ""), 320),
            }
        elif node == "analysis":
            summary = {
                "病例复杂度": output.get("complexity", "未知"),
                "关键风险": self._short_list(output.get("key_risks", []), 4, 100),
                "检索子问题": self._short_list(output.get("clinical_questions", []), 5, 120),
            }
        elif node == "tool_use":
            calls = output.get("tool_calls", [])
            summary = {
                "工具调用次数": len(calls) if isinstance(calls, list) else 0,
                "工具列表": self._short_list(
                    [f"{c.get('tool', '')}: {json.dumps(c.get('result', {}), ensure_ascii=False)[:120]}" for c in calls if isinstance(c, dict)],
                    5,
                    160,
                ) or "未调用工具",
            }
        elif node == "research_plan":
            decisions = output.get("clinical_decisions", [])
            summary = {
                "需要检索": bool(output.get("need_retrieve", False)),
                "临床决策节点(按优先级)": self._short_list(
                    [
                        f"[{d.get('priority', '?')}] {d.get('decision_name', '')}"
                        for d in decisions
                        if isinstance(d, dict) and d.get("decision_name")
                    ],
                    6,
                    80,
                ) or "未生成决策节点",
                "检索任务": self._short_list(
                    [task.get("question", "") for task in output.get("retrieval_tasks", []) if isinstance(task, dict)],
                    5,
                    100,
                ),
                "扩展查询": self._short_list(output.get("retrieval_queries", []), 6, 120),
                "信息缺口": self._short_list(output.get("missing_information", []), 5, 100),
            }
        elif node == "retrieve":
            ev = output.get("evidence", "")
            count = ev.count("【证据 ") if str(ev).strip() else 0
            summary = {
                "检索轮次": output.get("retrieval_round", 0),
                "证据条数": count,
                "证据摘要": self._short_text(ev, 420) or "未检索到相关证据",
            }
        elif node == "evidence_judge":
            summary = {
                "证据质量": output.get("evidence_quality", 0.0),
                "是否继续检索": bool(output.get("need_retrieve", False)),
                "评估结论": self._short_text(output.get("evidence_assessment", ""), 280),
                "剩余缺口": self._short_list(output.get("missing_information", []), 5, 100),
            }
        elif node == "query_rewrite":
            summary = {
                "重写后查询": self._short_list(output.get("retrieval_queries", []), 6, 120),
                "继续检索": bool(output.get("need_retrieve", False)),
            }
        elif node == "reason":
            expert_summaries = {
                role: self._short_text(advice, 180)
                for role, advice in list(output.get("expert_opinions", {}).items())[:4]
            }
            if not expert_summaries:
                for key, value in output.items():
                    if key.endswith("_advice") and value and len(expert_summaries) < 4:
                        expert_summaries[key.removesuffix("_advice")] = self._short_text(value, 180)
            summary = {
                "专家意见摘要": expert_summaries,
            }
            if output.get("proposal") or output.get("critique"):
                summary.update({
                    "综合方案摘要": self._short_text(output.get("proposal", ""), 360),
                    "风险审查摘要": self._short_text(output.get("critique", ""), 260),
                })
        elif node == "debate":
            summary = {
                "交叉质询摘要": self._short_text(output.get("debate_transcript", ""), 620),
            }
        elif node == "consensus_agent":
            summary = {
                "会诊共识": self._short_text(output.get("consensus", ""), 260),
                "综合方案摘要": self._short_text(output.get("proposal", ""), 360),
                "风险审查摘要": self._short_text(output.get("critique", ""), 260),
            }
        elif node == "validate":
            passed = bool(output.get("validation_passed", False))
            summary = {
                "校验结果": "通过" if passed else "需要反思修正",
                "反思次数": output.get("reflection_count", 0),
                "校验反馈": self._short_text(output.get("validation_feedback", ""), 360)
                or "规则引擎与医学逻辑审查均未发现严重冲突",
            }
        elif node == "compliance":
            issues = output.get("compliance_issues", []) or []
            warnings = output.get("compliance_warnings", []) or []
            summary = {
                "审计结果": "通过" if output.get("compliance_passed", False) else "发现风险",
                "风险项": self._short_list(issues, 5, 120) or "无",
                "提示项": self._short_list(warnings, 3, 120) or "无",
            }
        elif node == "human_review":
            summary = {
                "复核结果": "通过" if output.get("review_approved") else "驳回重新会诊",
                "医生意见": self._short_text(output.get("review_feedback", ""), 200) or "无",
            }
        elif node == "generate_report":
            report = output.get("report", "")
            summary = {"报告状态": "已生成", "报告长度": f"{len(str(report))} 字符"}
        elif node == "knowledge_answer":
            report = output.get("report", "")
            summary = {"回答状态": "已生成", "回答长度": f"{len(str(report))} 字符"}
        elif node == "reject":
            summary = {"处理结果": self._short_text(output.get("report", ""), 240)}

        if not summary:
            summary = {"执行结果": "步骤已完成"}
        return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _short_text(value, limit: int) -> str:
        """压缩空白并限制单项摘要长度。"""
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[:limit - 3].rstrip() + "..."

    @classmethod
    def _short_list(cls, values, max_items: int, item_limit: int) -> list:
        """限制列表项数量和每项长度，防止思考事件过大。"""
        if not isinstance(values, list):
            return []
        return [cls._short_text(value, item_limit) for value in values[:max_items] if value]
