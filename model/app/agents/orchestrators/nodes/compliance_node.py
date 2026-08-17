"""合规审计节点(Compliance Audit)。

在安全校验(validate)之后、报告生成之前执行, 纯规则、不调用 LLM:
- PHI 检测: 对会诊草稿(共识/方案/风险审查)做 HIPAA 18 类 PHI 扫描;
- 绝对化断言检测: 100%/绝对/必定/保证 等易引发医疗风险的口径;
- 具体剂量检测(警告级): 草稿中出现剂量单位时提示(系统口径要求禁止具体剂量);
- 审计留痕: 校验结论/问题清单/时间戳写入 state.compliance_audit, 并输出服务端审计日志;
- 免责声明: 附到审计记录, 供报告生成环节引用。

非阻塞设计: 审计发现问题不阻断流程, 结论随思考链展示并落审计日志,
由医生复核(HITL)与人工判断兜底。
"""

import logging
import re
import time
from typing import Dict, List

from app.agents.core.schema import ClinicalState
from app.agents.orchestrators.nodes.base import BaseNode
from app.utils.security import detect_phi

logger = logging.getLogger(__name__)

# 免责声明(随审计记录写入 state, 报告生成可引用)
DISCLAIMER = (
    "本结果为 AI 辅助决策参考, 不构成诊断或处方; 请结合患者实际情况, "
    "由具备资质的临床医生做最终判断。"
)

# 绝对化断言(编译后的正则, 排除"绝对禁忌证/绝对适应证"等合法临床术语)
_CERTAINTY_PATTERNS = [
    re.compile(r"100\s*%"),
    re.compile(r"绝对(?!禁忌|适应)"),
    re.compile(r"必定"),
    re.compile(r"保证治愈|包治|必死"),
]

# 剂量模式(警告级: 命中即提示, 不判失败)
_DOSE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg/kg|mg|g|IU|U)\s*(?:每|/)?(?:日|天|次)?")


class ComplianceNode(BaseNode):
    """输出合规审计: PHI / 绝对化断言 / 剂量提示 + 审计留痕。"""

    async def run(self, state: ClinicalState) -> Dict:
        draft_parts = [
            str(state.get("consensus", "") or ""),
            str(state.get("proposal", "") or ""),
            str(state.get("critique", "") or ""),
        ]
        draft = "\n".join(part for part in draft_parts if part.strip())

        issues: List[str] = []
        warnings: List[str] = []

        # 1) PHI 检测(HIPAA 18 类)
        phi = detect_phi(draft)
        if phi:
            issues.append("检测到 PHI: " + "、".join(phi))

        # 2) 绝对化断言(排除"绝对禁忌/绝对适应"等合法术语)
        certainty_hits = [p.pattern for p in _CERTAINTY_PATTERNS if p.search(draft)]
        if certainty_hits:
            issues.append("绝对化断言: " + "、".join(certainty_hits))

        # 3) 具体剂量(警告级)
        if _DOSE_RE.search(draft):
            warnings.append("草稿包含具体剂量表述, 请复核是否符合'禁止具体剂量'口径")

        passed = not issues
        audit = {
            "checked_at": time.time(),
            "passed": passed,
            "phi": phi,
            "certainty_hits": certainty_hits,
            "dose_warning": bool(warnings),
            "issues": issues,
            "warnings": warnings,
            "disclaimer": DISCLAIMER,
        }

        # 服务端审计日志(脱敏, 不含病例原文)
        logger.info(
            "[compliance] passed=%s issues=%d phi=%s certainty=%s dose=%s",
            passed, len(issues), ",".join(phi) or "-",
            ",".join(certainty_hits) or "-", bool(warnings),
        )

        return {
            "compliance_passed": passed,
            "compliance_issues": issues,
            "compliance_warnings": warnings,
            "compliance_audit": audit,
        }
