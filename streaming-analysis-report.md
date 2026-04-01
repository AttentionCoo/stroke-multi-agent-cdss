# 流式输出技术原理分析与对比报告

> 基于 claw-code 项目代码精读，结合 Synapse MD 架构场景的技术选型建议
>
> 报告日期：2026-04-01

---

## 目录

1. [claw-code 流式实现全景分析](#1-claw-code-流式实现全景分析)
   - 1.1 生产端：模型调用如何发起流式请求
   - 1.2 传输层：数据如何推送
   - 1.3 消费端：前端如何接收与渲染
   - 1.4 连接管理
   - 1.5 背压与流控
   - 1.6 错误处理与降级
2. [核心设计模式总结](#2-核心设计模式总结)
3. [横向技术方案对比](#3-横向技术方案对比)
4. [结合 Synapse MD 的技术建议](#4-结合-synapse-md-的技术建议)

---

## 1. claw-code 流式实现全景分析

### 1.1 生产端：模型调用如何发起流式请求

**涉及文件**：
- `rust/crates/api/src/client.rs`（第 217–231 行）
- `rust/crates/api/src/client.rs`（第 273–336 行）

claw-code 通过向 Anthropic `/v1/messages` API 发送带有 `"stream": true` 字段的 HTTP POST 请求来开启流式模式。底层使用 Rust 的 **reqwest 0.12 异步 HTTP 客户端**，运行在 **tokio 异步运行时**上。

```rust
// rust/crates/api/src/client.rs 第 217-231 行
pub async fn stream_message(
    &self,
    request: &MessageRequest,
) -> Result<MessageStream, ApiError> {
    let response = self
        .send_with_retry(&request.clone().with_streaming())  // 注入 stream:true
        .await?;
    Ok(MessageStream {
        request_id: request_id_from_headers(response.headers()),
        response,
        parser: SseParser::new(),
        pending: VecDeque::new(),
        done: false,
    })
}
```

**通俗解释**：就像打开了一根持续流水的水管，而不是等水桶装满再端过来。`send_with_retry` 包裹了重试逻辑（详见 1.4），确保网络抖动时不会直接失败。

---

### 1.2 传输层：数据如何从后端推送

**涉及文件**：
- `rust/crates/api/src/sse.rs`（完整文件，约 219 行）
- `rust/crates/api/src/types.rs`（第 157–212 行）

传输层使用**标准 HTTP SSE（Server-Sent Events）协议**，即 `Content-Type: text/event-stream`。服务器持续以 chunked transfer encoding 向客户端推送形如以下格式的帧：

```
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: ping
data: {"type":"ping"}

data: [DONE]
```

claw-code 实现了一个完整的 SSE 帧解析器：

```rust
// rust/crates/api/src/sse.rs 第 40-60 行
// 通过查找 \n\n 或 \r\n\r\n 来定位帧边界
fn next_frame(&mut self) -> Option<String> {
    let separator = self.buffer.windows(2)
        .position(|w| w == b"\n\n")
        .map(|pos| (pos, 2))
        .or_else(|| {
            self.buffer.windows(4)
                .position(|w| w == b"\r\n\r\n")
                .map(|pos| (pos, 4))
        })?;
    // 从缓冲区裁切出一帧
    ...
}
```

**事件类型枚举**（`rust/crates/api/src/types.rs` 第 157–212 行）：

| 事件类型 | 含义 |
|---------|------|
| `MessageStart` | 流式会话开始，携带初始状态 |
| `ContentBlockStart` | 一个新内容块（文字/工具调用）开始 |
| `ContentBlockDelta` | 增量内容（文字 delta 或 JSON 片段） |
| `ContentBlockStop` | 一个内容块结束 |
| `MessageDelta` | token 用量更新 |
| `MessageStop` | 整个响应结束 |

**ping 帧处理**（`sse.rs` 第 85–86 行）：服务端定期发送 `event: ping` 作为保活心跳，解析器直接静默丢弃，防止长时间推理时连接被中间件超时断开。

---

### 1.3 消费端：如何接收与逐步渲染

**涉及文件**：
- `rust/crates/api/src/client.rs`（第 524–563 行）：异步迭代器
- `rust/crates/rusty-claude-cli/src/main.rs`（第 2424–2559 行）：事件处理循环
- `rust/crates/rusty-claude-cli/src/render.rs`（第 600–665 行）：流式 Markdown 渲染

#### 异步拉取迭代器

```rust
// rust/crates/api/src/client.rs 第 524-563 行
pub async fn next_event(&mut self) -> Result<Option<StreamEvent>, ApiError> {
    loop {
        if let Some(event) = self.pending.pop_front() {
            return Ok(Some(event));   // 先消费已解析的事件
        }
        if self.done { ... }
        match self.response.chunk().await? {
            Some(chunk) => {
                self.pending.extend(self.parser.push(&chunk)?);  // 拿到 HTTP chunk → 解析 → 入队
            }
            None => { self.done = true; }
        }
    }
}
```

这是一个**拉取式（pull-based）**设计：消费者调用 `next_event()` 时才去取下一块数据，而不是服务器不断往消费者推（push-based）。这种设计天然避免了消费者来不及处理导致的内存积压。

#### 流式 Markdown 渲染（关键设计）

```rust
// rust/crates/rusty-claude-cli/src/render.rs 第 600-665 行
pub fn push(&mut self, renderer: &TerminalRenderer, delta: &str) -> Option<String> {
    self.pending.push_str(delta);
    let split = find_stream_safe_boundary(&self.pending)?;
    let ready = self.pending[..split].to_string();
    self.pending.drain(..split);
    Some(renderer.markdown_to_ansi(&ready))
}

fn find_stream_safe_boundary(markdown: &str) -> Option<usize> {
    // 逐行扫描，跳过代码块内部（防止代码块被截断）
    // 在空白行处标记安全分割点
    ...
}
```

**渲染策略的通俗解释**：

想象你在看一篇直播输出的文章。如果每收到一个字就重新渲染整段，会闪烁；如果等全部收完再渲染，又失去了"流式"的意义。claw-code 的做法是：
1. 将 token delta 累积到 `pending` 缓冲区
2. 找到"安全的分割点"（空白行，且不在代码块内部）
3. 只渲染到分割点为止的内容，剩余部分留待下次
4. 流结束时 `flush()` 强制输出剩余内容

这样既保证了 Markdown 语法的完整性，又做到了视觉上的流畅逐段渲染。

---

### 1.4 连接管理

**涉及文件**：
- `rust/crates/api/src/client.rs`（第 273–336 行）：重试循环
- `rust/crates/api/src/error.rs`（第 32–48 行）：重试判断

#### 指数退避重试

```rust
// rust/crates/api/src/client.rs 第 325-336 行
fn backoff_for_attempt(&self, attempt: u32) -> Result<Duration, ApiError> {
    let multiplier = 1_u32.checked_shl(attempt.saturating_sub(1))?;
    Ok(self.initial_backoff
        .checked_mul(multiplier)
        .map_or(self.max_backoff, |d| d.min(self.max_backoff)))
}
```

默认配置：
- **最大重试次数**：2 次
- **初始等待**：200ms
- **最大等待**：2000ms
- **退避序列**：200ms → 400ms → 800ms（上限 2s）

#### 可重试的 HTTP 状态码（`client.rs` 第 588–590 行）

```rust
const fn is_retryable_status(status: reqwest::StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 409 | 429 | 500 | 502 | 503 | 504)
}
```

`429`（限流）和 `5xx`（服务端错误）都会触发重试；`401`/`403`（认证失败）不会重试，避免无效消耗。

#### 心跳机制

服务端定期发送 `event: ping` 帧（`sse.rs` 第 85–86 行），解析器静默丢弃。这是标准 SSE keepalive 做法：防止 Nginx、负载均衡器等中间件因"无数据"判断连接空闲而关闭它。

---

### 1.5 背压（Backpressure）与流控

**涉及文件**：
- `rust/crates/api/src/client.rs`（第 524–530 行）：`VecDeque` 事件缓冲

```rust
pub struct MessageStream {
    pending: VecDeque<StreamEvent>,  // 已解析待消费的事件队列
    ...
}
```

claw-code 的流控策略是**拉取式（Pull-based）自然背压**：

- HTTP 层：reqwest 内部管理接收缓冲区（约 8KB），若应用层不读取 `chunk()`，TCP 窗口会自然缩小，服务端会减慢发送速度
- 应用层：`VecDeque<StreamEvent>` 存放已解析未消费事件，消费者调用 `next_event()` 时按需弹出
- 渲染层：`MarkdownStreamState.pending` 缓冲未到安全边界的文本，防止过早输出

**注意**：claw-code 是 CLI 工具，没有多租户并发压力，因此没有实现显式的流速限制（rate limiting）。在多用户服务端场景需要额外设计。

---

### 1.6 错误处理与降级

**涉及文件**：
- `rust/crates/api/src/error.rs`（完整文件）
- `rust/crates/rusty-claude-cli/src/main.rs`（第 2533–2559 行）：降级逻辑

#### 错误分类

```rust
// rust/crates/api/src/error.rs
pub enum ApiError {
    MissingApiKey,          // 不可重试：配置错误
    ExpiredOAuthToken,      // 不可重试：需用户操作
    Http(reqwest::Error),   // 网络错误：部分可重试
    Api { retryable, .. },  // API错误：按状态码判断
    RetriesExhausted { .. },// 重试耗尽
    InvalidSseFrame(..),    // SSE 格式错误：不可重试
}
```

#### 流中断降级（关键设计）

```rust
// rust/crates/rusty-claude-cli/src/main.rs 第 2533-2559 行
if !saw_stop && events.iter().any(/* 已有部分内容 */) {
    events.push(AssistantEvent::MessageStop);  // 补充结束标记
}

if !events.iter().any(|e| matches!(e, AssistantEvent::MessageStop)) {
    // 流式彻底失败 → 回退到非流式请求
    let response = self.client.send_message(&MessageRequest {
        stream: false,
        ..message_request.clone()
    }).await?;
    response_to_events(response, out)
}
```

**通俗解释**：如果流式传输到一半断了，系统不会直接报错，而是悄悄地用普通请求（非流式）重新获取完整响应，保证用户仍然得到答案。这是一种"优雅降级"设计。

---

## 2. 核心设计模式总结

claw-code 的流式架构属于以下模式的**混合**：

| 模式 | 是否采用 | 说明 |
|------|---------|------|
| 原生 HTTP SSE | ✅ 主体 | 标准 `text/event-stream`，服务端推送 |
| WebSocket 双向流 | ❌ | 未使用，因为 Claude API 是单向的（请求→流响应） |
| Chunked Transfer Encoding | ✅ 底层 | HTTP/1.1 分块传输，SSE 的底层实现 |
| 拉取式异步迭代器 | ✅ 应用层 | `next_event()` 拉取，非推送，天然背压 |
| 事件溯源聚合 | ✅ 会话层 | 所有 delta 事件在会话层聚合为完整消息 |
| 降级兜底 | ✅ 容错层 | 流式失败 → 自动切换非流式 |

**架构层级图**：

```
┌─────────────────────────────────────────────────────┐
│  会话层 (conversation.rs)                            │
│  • 多轮对话状态管理                                   │
│  • tool use 循环（stream → execute → stream）         │
└────────────────────┬────────────────────────────────┘
                     │ 调用
┌────────────────────▼────────────────────────────────┐
│  CLI 消费层 (main.rs)                                │
│  • 事件分发循环 (while let Some(event) = stream...)  │
│  • 渐进式 Markdown 渲染                              │
│  • flush / 流中断降级                                │
└────────────────────┬────────────────────────────────┘
                     │ 拉取
┌────────────────────▼────────────────────────────────┐
│  流式客户端层 (client.rs + sse.rs)                   │
│  • MessageStream 异步迭代器                          │
│  • SSE 帧解析器 (SseParser)                          │
│  • 指数退避重试                                      │
└────────────────────┬────────────────────────────────┘
                     │ HTTP SSE
┌────────────────────▼────────────────────────────────┐
│  Anthropic API (外部)                                │
│  POST /v1/messages  stream:true                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. 横向技术方案对比

> 以下对比基于 claw-code 代码实证 + 各方案官方文档知识。

| 对比维度 | **claw-code 方案** | **手动 yield + StreamingResponse** | **LangChain astream / Callbacks** | **LangGraph astream_events** |
|---------|-------------------|-----------------------------------|-----------------------------------|------------------------------|
| **核心原理** | 原生 SSE + 拉取式异步迭代器；Rust reqwest 接收 HTTP chunked stream，SseParser 解帧，VecDeque 缓存事件 | Python generator 函数 `yield chunk`，FastAPI `StreamingResponse` 包装为 HTTP chunked 响应；最底层也是 SSE 或纯 chunked | LangChain 的 `BaseCallbackHandler.on_llm_new_token` 回调在 token 到达时触发；`astream` 是对底层 LLM provider SSE 的高层封装 | LangGraph 在 LangChain 流之上增加了图执行事件层，每个节点（Node）、边（Edge）的进入/退出都发射事件；`astream_events` 返回结构化事件流 |
| **数据粒度** | **Token 级** delta（`TextDelta`）+ **事件级**（`ContentBlockStart/Stop`、`MessageStop`）；工具输入为 JSON 片段流 | 取决于实现：generator 可以 yield 任意粒度（字节/行/token），通常是 token 级或 chunk 级 | **Token 级**：`on_llm_new_token` 每次触发一个 token；`astream` 返回 `AIMessageChunk` | **事件级**（最细）：每个节点状态变化都有事件；内部 token delta 通过 `on_chat_model_stream` 事件携带 |
| **协议层** | HTTP/1.1 SSE（`text/event-stream`）；从 Anthropic API 端到 CLI 端是同一个长连接 | 通常是 HTTP chunked transfer（可包装为 SSE，需手动加 `data:` 前缀）或纯 chunked；FastAPI `StreamingResponse` 默认不加 SSE 格式 | 与底层 LLM provider 一致（OpenAI/Anthropic 均为 SSE）；对外暴露的是 Python async generator，与协议解耦 | 同 LangChain，内部使用 provider SSE；对外是 Python async generator，可包装为 FastAPI SSE 输出 |
| **中间节点可观测性**（能否知道当前在哪个 Agent/Tool）| **部分支持**：有 `ContentBlockStart/Stop` 事件标识 tool use 开始/结束，工具名和 ID 在事件中携带；但没有"当前在哪个子图"的概念（因为 claw-code 不是图结构） | **不支持**：纯 yield 方案需要开发者自己在 generator 中插入标记事件 | **有限支持**：Callbacks 可监听 `on_tool_start/end`、`on_chain_start/end`；但需要自定义 handler，侵入性较高 | **完整支持**：这是 LangGraph 的核心卖点。每个节点进出都有结构化事件，可精确知道"现在在 planner 节点"、"现在在 tool executor"；事件格式统一（`{event, name, data, run_id}`） |
| **背压与流控** | **拉取式自然背压**：消费者调用 `next_event()` 控制速率；TCP 窗口在应用层不消费时自动缩小；无显式限流 | **无内置背压**：FastAPI generator 直接推送；若客户端消费慢，数据积压在 TCP 缓冲区；需开发者自己控制 `asyncio.sleep` 或缓冲 | **无显式背压**：LangChain `astream` 是 push 语义的 async generator；背压依赖 Python asyncio 的内部调度 | 同 LangChain，无显式背压信令；高并发场景需在框架外自行限流 |
| **错误恢复能力** | **三级恢复**：① 单次请求级：指数退避重试（最多 2 次）；② 流级：`saw_stop` 检测不完整流并补充结束标记；③ 会话级：流式彻底失败自动切换非流式请求 | **基本无内置恢复**：generator 抛出异常即结束；需开发者在外层包裹 try/except 重建 generator | **依赖 provider 客户端**：OpenAI/Anthropic SDK 本身有重试；LangChain 层面可通过 `with_retry()` 装饰器包裹，但流中断后无自动恢复 | 同 LangChain + 图检查点（Checkpointing）：LangGraph 支持持久化图状态，节点失败后可从检查点重新执行；这是比 claw-code 更强的恢复能力 |
| **与 Spring WebFlux 的兼容性** | claw-code 是 CLI 工具，无中间件转发；但其 SSE 格式完全兼容；WebFlux 可用 `WebClient` 订阅 `text/event-stream`，映射为 `Flux<ServerSentEvent>` | FastAPI 原生 StreamingResponse 兼容 WebFlux；若包装为标准 SSE 格式（`data:...\n\n`），WebFlux 直接解析；若是纯 chunked，WebFlux 需要自己切分 | 对外 API 通常包装为 FastAPI SSE，WebFlux 兼容性与手动 yield 方案相同 | 同上；注意 `astream_events` 事件结构较复杂，WebFlux 透传时需决定是否解析中间节点事件 |
| **前端渲染友好度** | **逐段安全渲染**：`find_stream_safe_boundary` 确保 Markdown 不被截断；代码块不会出现半截渲染；渲染粒度是"安全段落"而非逐字符 | **最灵活**：开发者完全控制 yield 粒度；若逐 token yield 则前端需处理不完整 Markdown；若按段落 yield 则体验接近 claw-code | 取决于封装方式；token 级流式对前端压力大（每字符刷新）；通常需在前端或中间层做缓冲 | 事件级流式：前端可选择性渲染（如只渲染 `on_chat_model_stream`），也可展示节点进度；渲染复杂度较高，但交互体验最丰富 |
| **代码复杂度与可维护性** | **中等**：SSE 解析、重试、渲染层各自独立，Rust 类型系统保证安全；但 Rust 本身学习曲线高；整体约 2000 行核心代码 | **最简单**：10–50 行即可实现基础流式；无额外依赖；缺点是缺乏标准化，容易变成"手工面条代码" | **中等**：LangChain 抽象层减少样板代码；但 Callback 机制较复杂，文档分散；链式 API 调试困难 | **最复杂**：图定义 + 节点 + 边 + 检查点 + 事件过滤；初始搭建成本高；但大型 multi-agent 项目后期维护成本低 |
| **适用场景** | 单模型流式 CLI 工具；需要优雅降级和重试；需要渐进式 Markdown 渲染 | 简单流式 API；原型验证；对性能要求高的场景（无额外框架开销） | 单链条 LLM 应用；需要 token 级回调监控；快速集成多种 LLM provider | 多智能体协作系统；需要详细的执行过程可观测性；需要节点级错误恢复和断点续跑 |

---

## 4. 结合 Synapse MD 的技术建议

### 4.1 可借鉴的设计

#### 借鉴 1：流式安全渲染边界（Render-Safe Boundary）

**来源**：`render.rs` 第 600–665 行，`find_stream_safe_boundary()` 函数

**借鉴什么**：在 Vue 3 前端建立类似的缓冲逻辑——不是逐 token 触发 DOM 更新，而是累积到"安全的分割点"（段落末尾、代码块结束）再一次性更新。

**应用在哪里**：Vue 3 的 SSE 接收端（`EventSource` 或 `fetch` + `ReadableStream`）。维护一个 `pendingBuffer`，每次接收到 token 后：
1. 追加到 `pendingBuffer`
2. 检测是否到达安全边界（空行、闭合代码块）
3. 是则渲染，否则继续等待

**预期收益**：消除因 Markdown 渲染不完整导致的视觉闪烁；减少 Vue 响应式系统的触发频率（从每 token 一次降低到每段落一次），显著改善渲染性能。

---

#### 借鉴 2：ping 心跳静默处理 + 超时控制

**来源**：`sse.rs` 第 85–86 行

**借鉴什么**：在 Spring WebFlux 中间件层，对 SSE 心跳帧（`event: ping`）进行拦截，不透传给前端；同时在 WebFlux 层设置合理的 `timeout()` 而不是依赖 Nginx 的超时配置。

**应用在哪里**：WebFlux 的 `WebClient` 消费 FastAPI SSE 流时，在 `Flux` 链上加：

```java
webClient.get()
    .uri("/stream")
    .retrieve()
    .bodyToFlux(ServerSentEvent.class)
    .filter(event -> !"ping".equals(event.event()))  // 过滤心跳
    .timeout(Duration.ofSeconds(300))                 // 设置超时
```

**预期收益**：防止心跳帧被 Vue 前端误解析；明确的超时控制比 Nginx 超时更可靠。

---

#### 借鉴 3：三级错误恢复机制

**来源**：`client.rs` 第 273–336 行 + `main.rs` 第 2533–2559 行

**借鉴什么**：在 FastAPI 层实现类似的分级恢复：
- **请求级**：对 429/5xx 实现指数退避重试（tenacity 库）
- **流级**：检测流是否完整结束（是否收到终止标记），不完整时补充错误事件通知前端
- **会话级**：流式失败后提供降级为非流式的选项

**应用在哪里**：FastAPI 的流式生成函数内部 + Vue 前端的 `onerror` 处理。

**预期收益**：减少因网络抖动导致的用户可见错误；提升系统在高负载下的稳定性。

---

### 4.2 技术选型建议

针对 Synapse MD 的三层架构（FastAPI → WebFlux → Vue），推荐以下组合方案：

#### 推荐方案：LangGraph astream_events + 标准 SSE 格式

**理由**：

1. **FastAPI 层**（生产端）：
   - 使用 **LangGraph `astream_events`** 产生结构化事件流
   - 用 FastAPI `StreamingResponse` 或 `EventSourceResponse`（sse-starlette 库）包装为标准 SSE
   - 每个事件包含节点信息，便于 WebFlux 层做路由决策
   - 对比手动 yield：减少样板代码，内置的图执行可观测性更利于未来功能扩展

2. **Spring WebFlux 层**（中间件）：
   - 使用 `WebClient` 消费 FastAPI 的 SSE 流，映射为 `Flux<ServerSentEvent>`
   - 在此层实现：过滤心跳帧、连接超时控制、背压控制（`limitRate()`）
   - 对 Vue 前端重新以 SSE 格式输出（`SseEmitter` 或 WebFlux 原生 SSE 支持）
   - **关键**：在 WebFlux 层做事件类型路由，只转发 `on_chat_model_stream`（token）和必要的节点状态变化事件，降低前端处理复杂度

3. **Vue 3 层**（消费端）：
   - 使用原生 `fetch` + `ReadableStream`（而非 `EventSource`，后者不支持 POST 和自定义 header）
   - 实现 `pendingBuffer` + 安全边界检测（参考 claw-code render.rs 的逻辑）
   - 用 `requestAnimationFrame` 调度渲染更新，而非直接同步更新 DOM

#### 备选方案（简单场景）

如果 Synapse MD 的智能体逻辑较简单（单链条 LLM 调用），可以用**手动 yield + StreamingResponse**，更轻量，维护成本低，运行时开销也最小。

---

### 4.3 现有问题的针对性建议

#### 问题 1：Nginx 代理缓冲导致卡顿

**根因**：Nginx 默认的 `proxy_buffering on` 会将后端响应缓冲到磁盘后再发给客户端，这对流式输出是致命的。

**claw-code 的思路参考**：claw-code 是直连 Anthropic API，没有 Nginx，因此这个问题不存在于其实现中。但其心跳处理机制给了启示——心跳帧的本质就是为了应对中间缓冲层的超时问题。

**针对性解决方案**（三选一，按优先级）：

① **首选：Nginx 配置关闭代理缓冲**
```nginx
location /api/stream {
    proxy_pass http://webflux-backend;
    proxy_buffering off;                    # 关闭代理缓冲
    proxy_cache off;                        # 关闭缓存
    proxy_set_header Connection '';         # 保持长连接
    proxy_http_version 1.1;                 # 必须用 HTTP/1.1
    proxy_set_header X-Accel-Buffering no;  # 明确告知 Nginx 不缓冲
    chunked_transfer_encoding on;
}
```

② **辅助：FastAPI 层定期发送心跳**（参考 claw-code 的 ping 帧处理）
```python
async def stream_with_keepalive():
    async for chunk in llm.astream(prompt):
        yield f"data: {chunk}\n\n"
    # 每 15 秒发一次心跳，防止 Nginx 60s 超时
    yield ": keepalive\n\n"
```

③ **根本方案**：将流式端点从 Nginx 代理链中分离，让 Vue 前端直连 WebFlux（跳过 Nginx）处理流式请求，Nginx 只代理普通 REST 请求。

---

#### 问题 2：前端渲染不够流畅

**根因分析**：通常有两种情况：
- **情况 A**：token 粒度太细，每个 token 触发一次 Vue 响应式更新，导致高频 DOM 重绘
- **情况 B**：Markdown 渲染库在不完整文本上工作，出现闪烁或布局跳动

**claw-code 的参考实现**：`render.rs` 的 `MarkdownStreamState` + `find_stream_safe_boundary`

**Vue 3 对应实现建议**：

```javascript
// composable/useStreamRenderer.js
const pendingBuffer = ref('')
const renderedContent = ref('')

function onTokenReceived(token) {
  pendingBuffer.value += token
  const boundary = findSafeBoundary(pendingBuffer.value)
  if (boundary !== -1) {
    renderedContent.value += renderMarkdown(pendingBuffer.value.slice(0, boundary))
    pendingBuffer.value = pendingBuffer.value.slice(boundary)
  }
}

function findSafeBoundary(text) {
  // 在空白行处分割，且不在代码块内部
  let inFence = false
  let lastBoundary = -1
  const lines = text.split('\n')
  let offset = 0
  for (const line of lines) {
    if (line.startsWith('```') || line.startsWith('~~~')) {
      inFence = !inFence
    }
    if (!inFence && line.trim() === '') {
      lastBoundary = offset + line.length + 1
    }
    offset += line.length + 1
  }
  return lastBoundary
}

// 流结束时 flush 剩余内容
function onStreamEnd() {
  if (pendingBuffer.value.trim()) {
    renderedContent.value += renderMarkdown(pendingBuffer.value)
    pendingBuffer.value = ''
  }
}
```

**额外优化**：使用 `requestAnimationFrame` 批量合并 16ms 内的多次 token 更新为单次 DOM 操作：

```javascript
let rafScheduled = false
function scheduleRender() {
  if (!rafScheduled) {
    rafScheduled = true
    requestAnimationFrame(() => {
      flushPendingTokens()
      rafScheduled = false
    })
  }
}
```

**预期收益**：从每 token 一次 DOM 更新（约 50–100 次/秒）降低到每帧一次（60 次/秒上限），且每次更新的内容是语义完整的段落，消除 Markdown 渲染闪烁。

---

## 附录：关键文件速查

| 文件路径 | 行号范围 | 核心内容 |
|---------|---------|---------|
| `rust/crates/api/src/client.rs` | 217–231 | 流式请求发起（`stream_message`） |
| `rust/crates/api/src/client.rs` | 273–336 | 指数退避重试（`send_with_retry`） |
| `rust/crates/api/src/client.rs` | 524–563 | 异步拉取迭代器（`next_event`） |
| `rust/crates/api/src/sse.rs` | 40–60 | SSE 帧边界检测（`next_frame`） |
| `rust/crates/api/src/sse.rs` | 63–101 | SSE 事件解析（`parse_frame`） |
| `rust/crates/api/src/sse.rs` | 85–86 | 心跳帧过滤（ping 静默丢弃） |
| `rust/crates/api/src/types.rs` | 157–212 | 流式事件类型定义（`StreamEvent` enum） |
| `rust/crates/api/src/error.rs` | 32–48 | 错误重试判断（`is_retryable`） |
| `rust/crates/rusty-claude-cli/src/main.rs` | 2424–2559 | 流式事件处理循环 + 降级逻辑 |
| `rust/crates/rusty-claude-cli/src/render.rs` | 600–665 | 流式 Markdown 安全渲染（`MarkdownStreamState`） |
| `rust/crates/runtime/src/conversation.rs` | 170–283 | 会话层流式管理（`run_turn`） |
| `rust/crates/runtime/src/conversation.rs` | 353–390 | 流式事件聚合（`build_assistant_message`） |

---

*报告基于 claw-code 主分支代码（commit `9ade3a7`），分析时未修改任何代码文件。*
