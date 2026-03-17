# NeuroAgentSystem 项目上下文

## 项目架构

- **后端:** Java 17 + Spring WebFlux，SSE 流式接口
- **模型层:** Python 3.11 + FastAPI，通过 asyncio.Queue 推送 SSE 事件
- **前端:** Vue 3，使用 fetch + ReadableStream 消费 SSE
- **核心链路:** Python yield → asyncio.Queue → FastAPI SSE → Java WebClient → 前端

## 改进计划

详见 `docs/流式输出架构改进方案.md`（当前文件位于项目根目录 `流式输出架构改进方案.md`），按 Phase 1/2/3 分步实施：

| 阶段 | 主要内容 | 优先级 |
|------|----------|--------|
| **Phase 1** 紧急修复 | 心跳保活机制、结构化错误码、持久化解耦 | P0 |
| **Phase 2** 稳定性提升 | 有界队列+背压、thinking 流压缩、parseModelLine 容错 | P1 |
| **Phase 3** 体验优化 | 断线续传协议、端到端链路追踪 | P2 |

## 代码规范

- Java 遵循现有的 Spring WebFlux 响应式风格
- Python 遵循 PEP 8，使用 async/await
- 新增代码必须包含中文注释说明改动意图
- 所有改动必须向后兼容，不破坏现有 SSE 事件格式
