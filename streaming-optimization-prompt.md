# 任务：优化大模型应用的流式输出体验

> **目标**：让流式输出从"日志刷屏"变成"有人在对面打字"的感觉。参照 Google Gemini Web 端的流式渲染效果，对现有三层架构的流式输出链路进行端到端优化。

---

## 一、当前架构概述

```
┌─────────────────────┐      SSE       ┌──────────────────────┐      SSE       ┌────────────────────┐
│  Python / FastAPI    │ ─────────────► │  Java / Spring       │ ─────────────► │  Vue 3 前端        │
│  (qwen_agent.py)     │   chunk 事件    │  WebFlux 中间层       │   转发 SSE      │  (fetch + stream)  │
│                      │               │  /api/user/ques/     │               │                    │
│  astream → yield     │               │  streamingQues       │               │  ReadableStream    │
│  {type:"chunk",      │               │                      │               │  → 累加字符串       │
│   content:"..."}     │               │                      │               │  → marked() 解析    │
└─────────────────────┘               └──────────────────────┘               │  → v-html 注入      │
                                                                              └────────────────────┘
```

### 三层职责

| 层级 | 技术栈 | 当前行为 |
|------|--------|---------|
| **Model 层** | Python / FastAPI + LangChain `astream` | `qwen_agent.py` yield `{type:"chunk", content:"..."}` 事件，经 `TokenAggregator` 聚合后通过 SSE 推送 |
| **中间层** | Java / Spring WebFlux | 接收 Python 层 SSE，透传/转发给前端，端点 `/api/user/ques/streamingQues` |
| **前端** | Vue 3.5 + marked 17 + DOMPurify 3.3 | `fetch()` + `ReadableStream` 手动解析 SSE，每个 chunk 累加到字符串变量 `a`，然后**对整段文本重新 `marked()` 解析 → DOMPurify → `v-html` 注入** |

### 前端项目配置

```
构建工具：Vite 7.1 + @vitejs/plugin-vue 6
框架版本：Vue 3.5.22 + vue-router 4.5 + Pinia 3
关键依赖：marked 17.0.1 / dompurify 3.3.0 / axios 1.12 / nprogress 0.2
开发代理：vite dev server → proxy /api → http://localhost:8080（Java 中间层）
路径别名：@ → ./src
模块类型：ESM（"type": "module"）
```

---

## 二、当前代码关键片段（已从生产代码提取）

### 2.1 Python 后端 — 流式事件生成

`qwen_agent.py` 的 `_run_clinical_reasoning_core` 方法中，流式输出的核心逻辑：

```python
# 知识问答流式输出（逐 token yield）
async for chunk in self.llm_proposer.astream([HumanMessage(content=knowledge_prompt)]):
    content = chunk.content if hasattr(chunk, "content") else str(chunk)
    if content:
        yield {"type": "chunk", "content": content}

# 报告流式输出（同样逐 token yield）
async for chunk in self.medical_assistant.stream_final_report(...):
    if isinstance(chunk, str) and chunk:
        yield {"type": "chunk", "content": chunk}
```

外层 `run_clinical_reasoning` 包装了 `TokenAggregator`，会将连续的 thinking 事件聚合，但 **chunk 事件是直接透传的**。

### 2.2 `qwen_assistant.py` — 流式报告生成

```python
async def stream_final_report(self, context, proposal, critique, evidence, all_info, report_mode):
    # ...
    async for chunk in self.llm.astream(messages):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content
        elif isinstance(chunk, str) and chunk:
            yield chunk
```

### 2.3 前端 — SSE 消费与渲染（从 Vite 打包后的 JS 中逆向提取）

**SSE 消费逻辑**：
```javascript
// fetch + ReadableStream 手动解析（非 EventSource）
const T = await fetch("/api/user/ques/streamingQues", {
    method: "POST",
    headers: k,
    body: JSON.stringify(A)
});

// 逐行解析 SSE
if (L === "chunk") {
    const H = E.content || "";
    a += H;           // ← 累加到字符串变量
    t && t(H);        // ← 回调通知
    return;
}
```

**Markdown 渲染**：
```html
<!-- Vue 模板 -->
<div class="markdown-body" :innerHTML="parsedMarkdown(messageContent)"></div>
```

渲染方式：每到一个 chunk → 字符串 `a` 追加 → 对**整段累积文本**重新调用 `marked()` 解析 → DOMPurify 消毒 → `v-html` 注入替换整个 DOM 子树。

**CSS 动画现状**：
- 有 `.thinking-dots` 弹跳动画（thinking 阶段）
- `.thinking-indicator` + `.thinking-text`
- **流式输出本身**：没有打字光标、没有淡入动画、没有逐字渲染效果
- 已有 `.fade-enter-active` / `.fade-leave-active` 过渡，但未应用于流式文本

---

## 三、我想要的效果（对标 Gemini，逐项拆解）

请严格按以下 4 个维度改造，每个维度都必须实现：

### ✅ 3.1 逐字/逐词平滑出现（最高优先级）

**现状问题**：chunk 到达后整块文字瞬间出现，看起来一坨一坨地跳。

**期望效果**：
- 收到一个 chunk 后，其中的文字以 **逐字或逐词** 的速度渐进显示到页面上
- 显示速度目标：约 30-60 字符/秒（模拟人类快速打字），可通过一个配置常量调节
- 如果后端发送速度大于前端显示速度，前端应排队等待（缓冲区机制），**不能跳过直接刷屏**
- 如果后端发送速度小于前端显示速度（即前端已消费完缓冲区），新 chunk 到达后立即继续显示，不要有额外延迟
- 流式结束时（收到 `done` 事件），缓冲区内剩余的文字应**一次性全部渲染出来**，不要让用户等

**技术思路提示**（仅供参考，你可以用更好的方案）：
- 在 SSE 回调和 DOM 渲染之间加一个字符级队列（ring buffer / queue）
- 用 `requestAnimationFrame` 或 `setInterval` 按固定频率从队列中取字符追加到已有文本
- done 时 flush 队列

### ✅ 3.2 Markdown 实时渲染（标题/加粗/列表/代码块边流边渲染）

**现状问题**：每个 chunk 到达都触发一次完整的 `marked()` 重解析 + DOM 全量替换，导致：
- 列表、代码块等结构在渲染途中闪烁/回弹
- 已渲染的内容被反复销毁重建，浏览器不断 relayout

**期望效果**：
- 普通文本段落：逐字追加到当前 `<p>` 节点的 `textContent`，不要每次重建 DOM
- `## 标题`：检测到 `## ` 前缀时，立即创建 `<h2>` 元素，后续字符追加到该元素
- `**加粗**`：检测到 `**` 开启时切换到 `<strong>` 内追加，检测到闭合 `**` 时切回普通模式
- `` ``` `` 代码块：检测到开启围栏时创建 `<pre><code>` 块，内容追加到 `<code>` 中，检测到闭合围栏后应用语法高亮
- 列表（`- ` / `1. `）：逐项创建 `<li>` 元素追加

**技术思路提示**：
- **方案 A — 增量 Markdown 渲染器**：写一个简单的流式 Markdown 状态机，识别当前正在生成的块级元素类型，增量操作 DOM，只在段落/块完成时对该块进行一次完整 `marked()` 精修
- **方案 B — 差量 DOM 更新**：保留 `marked()` 全量解析，但用 `morphdom` 或类似库做 DOM diff 而非 innerHTML 全量替换，保留已有节点，减少回弹
- **方案 C — 混合方案**：流式阶段用逐字追加，每攒到一个完整段落（遇到 `\n\n`）时对该段落做一次 `marked()` 精修

选哪个方案由你决定，但必须满足：**用户看不到闪烁、回弹、内容反复重建**。

### ✅ 3.3 闪烁打字光标 + 新文本淡入

**期望效果**：
- 在最新输出位置的末尾显示一个 **闪烁的竖线光标** `▍`（类似终端光标），流式结束后消失
- 新出现的文字带一个轻微的 **淡入效果**（opacity 从 0.3 → 1，约 120ms），让"文字浮现"的感觉更柔和
- 不需要每个字符都独立淡入，可以按 chunk 或按"当前渲染批次"粒度淡入

**CSS 参考**：
```css
/* 闪烁光标 */
.streaming-cursor {
    display: inline;
    animation: blink 1s step-end infinite;
    color: var(--color-primary);
    font-weight: 300;
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}

/* 新文本淡入 — 仅供参考，你需要根据实际 DOM 操作方式调整 */
.text-fade-in {
    animation: fadeIn 120ms ease-out forwards;
}
@keyframes fadeIn {
    from { opacity: 0.3; }
    to { opacity: 1; }
}
```

### ✅ 3.4 智能自动滚动

**现状问题**：当前实现中看不到明确的自动滚动逻辑。

**期望效果**：
- **正常模式**：新内容产生时，聊天容器自动滚动到底部（`.chat-messages` 容器）
- **用户上滑暂停**：用户手动向上滚动后，停止自动滚动（用户在看历史内容，不要打断他）
- **回底恢复**：当用户滚回接近底部时（距底部 < 50px），恢复自动滚动
- 滚动行为使用 `scrollTo({ behavior: 'smooth' })` 而非硬跳

---

## 四、各层改动指引

### 4.1 Python 后端（可能需要的改动）

**核心问题诊断**：LangChain 的 `astream` 已经是逐 token 粒度的 yield，但 `TokenAggregator` 和 SSE 序列化环节可能把多个 token 攒在一起发送。

请检查并确保：
- `TokenAggregator` 对 `chunk` 类型事件**不做聚合**，直接透传（当前代码中已经是这样，请确认）
- SSE 序列化时**每个 chunk 立即 flush**，不要被框架缓冲（检查 `StreamingResponse` 的配置）
- 如果使用了 Nginx 代理，确认已设置 `proxy_buffering off; X-Accel-Buffering: no;`

### 4.2 Java / Spring WebFlux 中间层（关键改动）

Java 中间层作为 SSE 转发代理，最容易引入额外延迟：

请检查并确保：
- WebFlux 的 SSE 响应**逐事件 flush**（使用 `Flux<ServerSentEvent>` 而非聚合后再发）
- 如果使用了 WebClient 消费 Python SSE，确认是流式消费（`exchangeToFlux`），而非缓冲到完整响应
- HTTP 响应头包含 `Cache-Control: no-cache` + `X-Accel-Buffering: no`
- 如果中间层有任何 buffer/batch 逻辑，应去掉或把 batch window 降到 0

### 4.3 Vue 3 前端（主要改动，工作量最大）

这是改造的重点。当前的渲染流程是：

```
chunk 到达 → a += content → marked(a) → DOMPurify → innerHTML 全量替换
```

需要改造为：

```
chunk 到达 → 字符推入队列 → rAF 定时从队列取字符 →
    增量追加到当前 DOM 节点 → 光标跟随 → 触发自动滚动

段落/块完成 → 对该块做一次 marked() 精修 → morphdom 差量更新
```

---

## 五、验收标准（请逐项自查）

| # | 验收项 | 通过条件 |
|---|--------|---------|
| 1 | 逐字显示 | 肉眼可见文字是一个一个出现的，不是一坨一坨跳的 |
| 2 | 显示速度可控 | 存在一个常量（如 `CHARS_PER_SECOND = 50`）可以调节速度 |
| 3 | 缓冲区机制 | 后端发送快于前端显示时，文字不会跳过，而是排队等候 |
| 4 | done 时 flush | 流结束后缓冲区剩余内容立即全部渲染 |
| 5 | Markdown 实时渲染 | `## 标题` 和 `**加粗**` 在流式过程中就以格式化形式出现 |
| 6 | 无闪烁回弹 | 已渲染的内容不会因新 chunk 到达而闪烁或跳动 |
| 7 | 代码块处理 | `` ``` `` 围栏内的内容用等宽字体显示，闭合后高亮 |
| 8 | 打字光标 | 流式过程中末尾有闪烁竖线光标，结束后消失 |
| 9 | 新文本淡入 | 新出现的文字有轻微淡入效果（非硬切换） |
| 10 | 自动滚动 | 新内容自动滚到底部 |
| 11 | 上滑暂停 | 用户手动上滚后不再自动滚动 |
| 12 | 回底恢复 | 用户滚回底部附近后恢复自动滚动 |
| 13 | thinking 阶段 | thinking 事件的弹跳小球动画保持不变，不受改造影响 |

---

## 六、约束与注意事项

1. **不改变 SSE 事件协议**：`{type, content}` 的 JSON 格式不动，前端只改渲染逻辑
2. **不破坏现有功能**：thinking 指示器、停止按钮、复制按钮、历史消息渲染等全部保留
3. **历史消息不需要逐字效果**：只有**正在流式生成的消息**才使用逐字渲染 + 光标，历史消息仍然直接 `marked()` → `v-html` 一次性渲染
4. **深色模式兼容**：当前 CSS 使用了 CSS 变量（`--color-primary` 等），新增的样式也必须使用 CSS 变量
5. **移动端适配**：当前有 `@media(max-width:960px)` 的响应式布局，新逻辑不能在移动端出 bug
6. **性能红线**：逐字渲染不能导致 CPU 飙升，特别是长文本（3000+ 字的报告），需要在 rAF 中做节流
7. **依赖管理**：项目使用 ESM（`"type": "module"`），新增依赖需兼容 ESM import。如果需要引入新库（如 `morphdom`），请明确给出 `npm install` 命令和 import 方式
8. **marked 版本注意**：项目使用 `marked@17`（最新大版本），API 可能与旧版不同，使用 `marked.parse()` 而非已废弃的 `marked()`

---

## 七、给出改动方案的格式要求

请按以下顺序输出：

1. **问题诊断**：分析当前各层导致"一坨坨跳"的根因（是后端 chunk 粒度问题，还是前端渲染问题，还是两者都有）
2. **方案概述**：用一段话描述整体改造思路
3. **代码实现**：
   - 如果需要改 Python 后端 → 给出具体文件和 diff
   - 如果需要改 Java 中间层 → 给出关键配置或代码变更
   - 前端 Vue 组件改造 → 给出完整的新组件代码或关键函数实现
   - 新增/修改的 CSS → 完整给出
4. **集成说明**：如何将新代码嵌入到现有项目中，哪些文件需要改动
5. **测试建议**：如何验证改造效果

---

## 八、随本提示词一并提供的文件清单

> **使用本提示词时，请将以下文件作为上下文一起提供给 Claude Code：**

### 必须提供（已有）

| 文件 | 作用 |
|------|------|
| `qwen_agent.py` | Python 后端核心推理管线，包含 SSE 事件生成逻辑 |
| `qwen_assistant.py` | `stream_final_report` / `stream_fast_response` 流式报告生成 |
| `medical_agent.py` | 医学检索 Agent，影响证据检索耗时 |
| `package.json` | 前端项目依赖版本信息 |
| `vite.config.js` | Vite 构建与开发代理配置 |

### 强烈建议补充提供

| 文件 | 作用 | 为什么需要 |
|------|------|-----------|
| **Vue 聊天组件源码**（如 `ChatView.vue` 或 `ChatWorkspace.vue`） | 前端聊天界面的 `.vue` 源文件 | 这是改造的核心文件，Claude Code 需要看到原始模板/脚本/样式才能直接给出可用的 diff |
| **SSE 工具函数**（如 `useSSE.js` / `api/stream.js`） | 前端封装的 SSE 消费函数 | 包含 `fetch` + `ReadableStream` 解析、chunk 回调、重连逻辑等 |
| **Java SSE Controller**（如 `StreamController.java`） | Spring WebFlux 中间层转发 SSE 的代码 | 确认是否有缓冲/batch 导致 chunk 粒度变大 |
| **Nginx 配置**（如有） | 反向代理配置 | 确认 `proxy_buffering` 设置是否正确 |

> ⚠️ 当前只有 Vite 打包后的 `index-DRoo6eOF.js`（已压缩混淆），改造需要 **开发源码**（`.vue` 文件）。
