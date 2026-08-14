# 脑卒中医疗工具 (Skill & Tool Calling) 设计文档

## 1. 概述

系统新增脑卒中领域工具集,为多智能体 CDSS 提供可复用的医疗计算能力。
两种使用方式:

1. **独立工具 API** — 后端/前端可直接调用(`/model/tools/list`、`/model/tools/call`)
2. **接入 LangGraph 推理链** — 多智能体在病例分析后通过 LLM function calling 自主选择工具,结果参与专家推理

## 2. 工具清单

| 类别 | 工具名 | 输入 | 输出 |
|---|---|---|---|
| 量表评估 | `nihss_score` | NIHSS 各分项得分 | 总分、严重程度分级、关键警示 |
| 量表评估 | `mrs_score` | mRS 分级 0-6 | 分级描述、预后提示 |
| 量表评估 | `gcs_score` | E/V/M 三部分 | 总分、意识障碍分级 |
| 溶栓治疗 | `thrombolysis_window_check` | 发病-就诊时间(分钟或 ISO 时间点) | 3h/4.5h 窗内判定与建议 |
| 溶栓治疗 | `rtpa_dose_calc` | 体重(kg) | 总剂量、10% 首剂推注、90% 静滴 |
| 禁忌症检查 | `contraindication_check` | 治疗方式 + 患者病史文本 | 命中禁忌症列表、通过结论 |
| 诊断分型 | `toast_classify` | 血管/心脏/影像证据线索 | TOAST 建议分型与理由 |
| 大血管闭塞筛查 | `lvo_screening` | NIHSS 总分 + 神经体征(失语/偏瘫/皮层体征/凝视偏移/忽视) | LVO 概率分层与 CTA 建议 |

## 3. 代码结构

```
model/app/agents/tools/
├── __init__.py              # 包导出
├── adapters.py              # langchain StructuredTool 适配器(adapt_model_func)
├── scales.py                # NIHSS / mRS / GCS
├── thrombolysis.py          # 时间窗 / rt-PA 剂量
├── contraindications.py     # 禁忌症检查(复用 rules_config.yaml 规则 + 同义词/数值匹配)
├── subtype.py               # TOAST 分型
├── lvo_screening.py         # 大血管闭塞(LVO)筛查
└── registry.py              # TOOLS / TOOL_MAP / TOOL_GROUPS / call_tool / get_tool_schemas
```

关键设计:

- 每个工具 = `StructuredTool.from_function` + pydantic `args_schema`,天然兼容
  `llm.bind_tools()` 与 `ToolNode`
- `adapt_model_func()` 适配器解决 langchain 以字段 kwargs 调用 func 的约定
- 禁忌症工具复用 `get_validation_manager().get_contraindication_rules()`,
  内置同义词表(如「脑出血史」「血小板90」)提高命中率
- 所有工具纯函数实现、无外部 IO(除配置加载),便于单元测试

## 4. LangGraph 集成

推理链新增 `tool_use` 节点:

```
intent → memory → analysis → [tool_use] → research_plan → retrieve → ...
                                    │
                                    └─ LLM bind_tools 自主选择工具
                                       └─ 结果写入 state["tool_results"] / ["tool_calls"]
                                          └─ reason 节点注入「工具调用结果」上下文
```

实现:`model/app/agents/orchestrators/nodes/tool_use_node.py`

- 最多 `max_rounds=2` 轮工具调用,防失控
- 工具调度失败不阻塞主流程(降级为空结果)
- `ClinicalState` 新增 `tool_results: str` 与 `tool_calls: List[Dict]`
- 图构建向后兼容:不传 `tool_use_node` 时保持原拓扑
- 事件流新增 `tool_use` 节点展示(「医疗工具调用」),含调用次数与结果摘要

## 5. API 规范

### GET /model/tools/list

返回全部工具及参数 schema:

```json
{
  "code": 1, "msg": "success",
  "data": { "tools": [...], "groups": {...}, "count": 8 }
}
```

### POST /model/tools/call

```json
// 请求
{ "name": "rtpa_dose_calc", "arguments": { "weight_kg": 70 } }
// 响应
{ "code": 1, "msg": "success", "data": { "total_dose_mg": 63.0, "bolus_mg": 6.3, "infusion_mg": 56.7, ... } }
```

未知工具或参数校验失败返回 HTTP 400 + 错误详情。

## 6. 测试

- `tests/test_tools.py` — 24 个工具单元测试(评分、窗口、剂量、禁忌(含血压数值/治疗别名)、分型、注册表)
- `tests/test_tool_use_integration.py` — 26 个集成测试(mock LLM 驱动 ToolUseNode、图编译含/不含 tool_use、规则兜底、临床一致性校验等)
- `tests/test_tools_api.py` — 5 个 API 端点测试(工具清单、token 校验、错误脱敏)

运行:

```bash
cd model
python -m pytest tests/test_tools.py tests/test_tool_use_integration.py tests/test_tools_api.py -v
```

## 7. 医疗安全声明

所有工具输出均为**计算/筛查辅助**,不替代临床医生判断:

- 量表工具基于结构化输入计算,输入偏差会导致输出偏差
- 禁忌症为关键词+数值匹配筛查,阴性结果不能排除禁忌症
- 剂量计算仅为指南标准方案参考,实际用药须复核体重、核对禁忌症并知情同意
- 时间窗判断仅考虑时间因素,是否溶栓需结合影像与实验室结果

## 8. 安全与隐私

- `patient_info` 等敏感字段在日志中截断记录(≤60 字符),避免完整病史写入日志
- 参数校验错误对外只返回字段与约束类型(`weight_kg: greater_than`),不暴露输入值与堆栈
- `/model/tools/call` 支持 JWT token 校验(与 `/model/get_result` 一致);未传 token 时保持与 `/model/pubmed/search` 一致的向后兼容行为
