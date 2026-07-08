package com.it.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.cache.SSEEventCache;
import com.it.po.uo.QuesParam;
import com.it.pojo.Result;
import com.it.pojo.Talk;
import com.it.service.AIStreamingService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@CrossOrigin("*")
@RequestMapping("/api/user/ques")
@RequiredArgsConstructor
public class QuesController {

    private final AIStreamingService streamingService;
    private final ObjectMapper objectMapper;
    private final SSEEventCache eventCache;

    @GetMapping("/getQues/{talk_id}")
    public Result getPreContent(@PathVariable("talk_id") String talkIdStr) {
        Long talkId = Long.parseLong(talkIdStr);
        log.info("收到对话内容请求: talkId={}", talkId);  // 添加这行
        if (talkId == null || talkId <= 0) {
            return Result.success(List.of());
        }
        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Result.error("未登录");
        }
        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        return Result.success(streamingService.getPreContent(userId, talkId));
    }

    @PostMapping(value = "/streamingQues", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> streamingQues(
            @RequestBody QuesParam quesParam,
            @RequestHeader(value = "token", required = false) String token,
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId,
            HttpServletResponse response
    ) {
        // 告知 Nginx 对本连接关闭代理缓冲，确保每个 SSE chunk 实时到达浏览器
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
        if (ThreadLocalUtil.getCurrentUser() == null) {
            return Flux.just(sse("error", json("error", mapOf("message", "未登录"))));
        }

        String upstreamToken = resolveToken(token, authorization);

        Long userId = ThreadLocalUtil.getCurrentUser().getId();
        String talkIdStr = quesParam.getTalkId();
        Long talkId = null;

        if (talkIdStr != null && !talkIdStr.isBlank()) {
            try {
                talkId = Long.parseLong(talkIdStr);
                if (talkId != null && talkId <= 0) {
                    talkId = null;
                }
            } catch (NumberFormatException e) {
                talkId = null; // 非法 talkId 当作新对话处理
            }
        }

        boolean needCreate = (talkId == null || talkId <= 0);

        if (!needCreate) {
            Talk dbTalk = streamingService.getTalkById(talkId);
            if (dbTalk == null || !dbTalk.getUserId().equals(userId)) {
                needCreate = true;
            }
        }

        if (needCreate) {
            talkId = streamingService.createNewTalk(userId);
            log.info("创建新对话 talkId = {}", talkId);
        }

        final Long finalTalkId = talkId;
        final boolean finalNeedCreate = needCreate;
        final String finalTalkIdStr = String.valueOf(finalTalkId);

        // ===== 断线续传：有 Last-Event-ID 时走重连路径，不触发新的 AI 推理 =====
        if (lastEventId != null && !lastEventId.isBlank()) {
            int colonIdx = lastEventId.lastIndexOf(':');
            if (colonIdx > 0) {
                String idTalkId = lastEventId.substring(0, colonIdx);
                try {
                    long lastSeq = Long.parseLong(lastEventId.substring(colonIdx + 1));
                    return handleReconnect(idTalkId, lastSeq, finalTalkId, finalTalkIdStr);
                } catch (NumberFormatException e) {
                    log.warn("Last-Event-ID seq 非法，按新请求处理: lastEventId={}", lastEventId);
                    // 格式非法，fall through 走正常流程
                }
            } else {
                log.warn("Last-Event-ID 格式非法（缺少冒号），按新请求处理: lastEventId={}", lastEventId);
                // 格式非法，fall through 走正常流程
            }
        }

        // ===== 统一 JSON 协议 =====

        Flux<String> initFlux = Flux.just(
                json("init", mapOf(
                        "talkId", finalTalkId.toString(),
                        "newTalk", finalNeedCreate
                ))
        );

        Flux<String> resumeFlux = Flux.defer(() -> {
            String resume = streamingService.getResumeContent(userId, finalTalkId);
            if (resume == null || resume.isBlank()) {
                return Flux.empty();
            }
            return Mono.fromCallable(() -> json("resume", mapOf(
                    "talkId", finalTalkId.toString(),
                    "content", resume
            ))).flux();
        });

        // 为本次 talkId 注册 SSE 事件缓存，供断线重连时回放
        eventCache.registerStream(finalTalkIdStr);

        Flux<String> chatFlux = streamingService
                .streamChat(userId, finalTalkId, quesParam.getQuestion(), upstreamToken, quesParam.getImages())
                .map(this::wrapChunkIfNeeded);

        // 心跳终止信号：业务流（正常或异常）结束时 emit，通知心跳流停止
        Sinks.One<Void> doneSink = Sinks.one();

        // init/resume 事件：不参与断线续传缓存，SSE 事件不带 id 字段
        Flux<ServerSentEvent<String>> initResumeSSE = initFlux
                .concatWith(resumeFlux)
                .map(data -> sse(resolveEventName(data), data));

        // chatFlux 事件：缓存到 replay sink + 注入 SSE id（talkId:seq）
        // onErrorResume 将 chatFlux 内部异常转为 error/done 事件，保证流正常终止
        Flux<ServerSentEvent<String>> chatSSE = chatFlux
                .onErrorResume(e -> Flux.just(
                        json("error", mapOf(
                                "talkId", finalTalkIdStr,
                                "message", e.getMessage() == null ? "stream error" : e.getMessage()
                        )),
                        json("done", mapOf(
                                "talkId", finalTalkIdStr,
                                "title", "异常结束"
                        ))
                ))
                .map(data -> {
                    // addEvent 同时将事件写入 replay sink，返回分配的序列号
                    long seq = eventCache.addEvent(finalTalkIdStr, data);
                    return sseWithId(finalTalkIdStr + ":" + seq, resolveEventName(data), data);
                });

        // 业务数据流：init/resume（无 id）串联 chat（有 id），终止时触发心跳停止和缓存完成
        Flux<ServerSentEvent<String>> dataStream = initResumeSSE
                .concatWith(chatSSE)
                .doFinally(signal -> {
                    log.debug("涓氬姟娴佺粓姝紙signal={}锛夛紝鍋滄 SSE 蹇冭烦 comment, talkId={}", signal, finalTalkId);
                    doneSink.tryEmitEmpty();
                    eventCache.completeStream(finalTalkIdStr);
                });

        // 蹇冭烦娴侊细姣?15 绉掑彂送一次 SSE comment（冒号开头，前端 EventSource 会忽略）
        // 使用 takeUntilOther 监听 doneSink，业务流结束后立即终止心跳
        Flux<ServerSentEvent<String>> heartbeatFlux = Flux.interval(Duration.ofSeconds(15))
                .map(i -> {
                    log.debug("发送 SSE 心跳 comment, talkId={}", finalTalkId);
                    return ServerSentEvent.<String>builder().comment("heartbeat").build();
                })
                .takeUntilOther(doneSink.asMono());

        // 优雅关闭 comment：业务流结束后延迟 500ms 发送，避免前端在解析最后一个 chunk 时连接被切断
        Flux<ServerSentEvent<String>> closeFlux = Mono.<ServerSentEvent<String>>just(
                ServerSentEvent.<String>builder().comment("close").build()
        ).delayElement(Duration.ofMillis(500)).flux();

        // 合并业务流与心跳流（并发），末尾串联 close comment
        return Flux.merge(dataStream, heartbeatFlux)
                .concatWith(closeFlux);

    }

    private ServerSentEvent<String> sse(String event, String data) {
        return ServerSentEvent.<String>builder()
                .event(event)
                .data(data)
                .build();
    }

    /**
     * 带 SSE id 字段的事件构造，id 格式为 talkId:seq。
     * 浏览器/fetch 客户端会将 id 记为 Last-Event-ID，断线重连时自动携带。
     */
    private ServerSentEvent<String> sseWithId(String id, String event, String data) {
        return ServerSentEvent.<String>builder()
                .id(id)
                .event(event)
                .data(data)
                .build();
    }

    /**
     * 断线续传处理：从 SSE 事件缓存中回放 seq > lastSeq 的事件。
     * 若原始流仍在推送，回放结束后自动续接实时事件（同一 sink）。
     *
     * @param idTalkId      Last-Event-ID 中解析出的 talkId
     * @param lastSeq       客户端最后收到的事件序列号
     * @param finalTalkId   请求体中解析出的 talkId（Long，用于越权校验）
     * @param finalTalkIdStr finalTalkId 的字符串形式（缓存 key / SSE id 前缀）
     */
    private Flux<ServerSentEvent<String>> handleReconnect(
            String idTalkId, long lastSeq, Long finalTalkId, String finalTalkIdStr) {

        // talkId 校验：防止使用他人的 Last-Event-ID 访问其他对话的缓存
        if (!finalTalkIdStr.equals(idTalkId)) {
            log.warn("Last-Event-ID talkId 与请求 talkId 不匹配，拒绝重连: header={}, req={}",
                    idTalkId, finalTalkIdStr);
            return Flux.just(
                    sse("error", json("error", mapOf("code", "E2004", "message", "talkId 不匹配，无法重连")))
            );
        }

        // 从缓存获取回放流（含历史事件 + 后续实时推送）
        Flux<SSEEventCache.SequencedEvent> replayStream =
                eventCache.getReplayStream(finalTalkIdStr, lastSeq);

        if (replayStream == null) {
            // 缓存已过期或从未存在，无法恢复
            log.info("SSE 缓存已过期，无法重连: talkId={}, lastSeq={}", finalTalkIdStr, lastSeq);
            return Flux.just(
                    sseWithId(finalTalkIdStr + ":0", "error",
                            json("error", mapOf("code", "E2003", "message", "会话缓存已过期，无法恢复"))),
                    sse("done", json("done", mapOf("talkId", finalTalkIdStr, "title", "")))
            );
        }

        log.info("SSE 重连回放开始: talkId={}, lastSeq={}", finalTalkIdStr, lastSeq);

        // 重连专用 doneSink，控制本次重连连接的心跳生命周期
        Sinks.One<Void> doneSink = Sinks.one();

        // 将回放事件（含原始 seq）包装为带 id 的 SSE 事件
        Flux<ServerSentEvent<String>> replaySSE = replayStream
                .map(se -> sseWithId(finalTalkIdStr + ":" + se.seq(),
                        resolveEventName(se.data()), se.data()))
                .doFinally(signal -> {
                    log.debug("回放流终止 (signal={})，停止心跳", signal);
                    doneSink.tryEmitEmpty();
                });

        // 重连连接复用相同的心跳和优雅关闭逻辑
        Flux<ServerSentEvent<String>> heartbeatFlux = Flux.interval(Duration.ofSeconds(15))
                .map(i -> {
                    log.debug("发送 SSE 心跳 comment（重连）, talkId={}", finalTalkIdStr);
                    return ServerSentEvent.<String>builder().comment("heartbeat").build();
                })
                .takeUntilOther(doneSink.asMono());

        Flux<ServerSentEvent<String>> closeFlux = Mono.<ServerSentEvent<String>>just(
                ServerSentEvent.<String>builder().comment("close").build()
        ).delayElement(Duration.ofMillis(500)).flux();

        return Flux.merge(replaySSE, heartbeatFlux).concatWith(closeFlux);
    }

    private String resolveEventName(String data) {
        if (data == null || data.isBlank()) {
            return "message";
        }
        try {
            return objectMapper.readTree(data).path("type").asText("message");
        } catch (Exception e) {
            return "message";
        }
    }

    private String wrapChunkIfNeeded(String data) {
        if (data == null) {
            return json("chunk", mapOf("content", ""));
        }
        String trimmed = data.trim();
        if (!trimmed.isEmpty() && trimmed.startsWith("{") && trimmed.endsWith("}")) {
            return data;
        }
        return json("chunk", mapOf("content", data));
    }

    private String resolveToken(String token, String authorization) {
        if (token != null && !token.isBlank()) {
            return token.trim();
        }
        if (authorization != null && !authorization.isBlank()) {
            String value = authorization.trim();
            return value.startsWith("Bearer ") ? value.substring(7).trim() : value;
        }
        return null;
    }

    private String json(String type, Map<String, Object> payload) {
        try {
            Map<String, Object> root = new HashMap<>();
            root.put("type", type);
            if (payload != null && !payload.isEmpty()) {
                root.putAll(payload);
            }
            return objectMapper.writeValueAsString(root);
        } catch (Exception e) {
            return "{\"type\":\"error\",\"message\":\"json serialize error\"}";
        }
    }

    private Map<String, Object> mapOf(Object k1, Object v1) {
        Map<String, Object> m = new HashMap<>();
        m.put(String.valueOf(k1), v1);
        return m;
    }

    private Map<String, Object> mapOf(Object k1, Object v1, Object k2, Object v2) {
        Map<String, Object> m = new HashMap<>();
        m.put(String.valueOf(k1), v1);
        m.put(String.valueOf(k2), v2);
        return m;
    }
}
