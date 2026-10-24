package com.it.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.pojo.ClinicalReviewTask;
import com.it.service.impl.ConversationPersistenceService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 将医生复核决定续跑到 Python 推理图，并把最终报告落库。 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ClinicalReviewResumeService {

    private final WebClient webClient;
    private final ObjectMapper objectMapper;
    private final ClinicalReviewService clinicalReviewService;
    private final ConversationPersistenceService conversationPersistenceService;
    private final StringRedisTemplate stringRedisTemplate;

    private static final Duration CHUNK_TIMEOUT = Duration.ofSeconds(300);

    public Flux<ServerSentEvent<String>> resume(Long doctorId, Long taskId, String upstreamToken,
                                                boolean approved, String feedback) {
        ClinicalReviewTask task;
        try {
            task = clinicalReviewService.getOwned(doctorId, taskId);
        } catch (Exception e) {
            return Flux.just(sse("error", errorJson(e.getMessage())));
        }
        if (!"PENDING".equals(task.getStatus())) {
            return Flux.just(sse("error", errorJson("该复核任务已完成或已失效")));
        }

        clinicalReviewService.markDecision(taskId, approved, feedback);
        ReviewStreamState state = new ReviewStreamState(task, approved);
        Map<String, Object> request = new HashMap<>();
        request.put("token", upstreamToken);
        request.put("thread_id", task.getThreadId());
        request.put("approved", approved);
        request.put("feedback", feedback == null ? "" : feedback);

        return webClient.post()
                .uri("/model/resume")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue(request)
                .retrieve()
                .bodyToFlux(String.class)
                .timeout(CHUNK_TIMEOUT)
                .filter(StringUtils::hasText)
                .map(String::trim)
                .filter(line -> !line.startsWith(":"))
                .map(line -> line.startsWith("data:") ? line.substring(5).trim() : line)
                .filter(StringUtils::hasText)
                .concatMap(line -> handleModelEvent(taskId, state, line))
                .concatWith(Mono.fromCallable(() -> finalizeStream(taskId, state)))
                .onErrorResume(WebClientResponseException.class, e -> {
                    log.error("HITL 续跑调用失败: status={}, body={}", e.getStatusCode(), e.getResponseBodyAsString());
                    clinicalReviewService.markFailed(taskId, "AI 服务调用失败");
                    return Flux.just(sse("error", errorJson("AI 服务暂时不可用，请稍后重试")),
                            sse("done", doneJson(state, "failed", "AI 服务调用失败")));
                })
                .onErrorResume(e -> {
                    log.error("HITL 续跑异常: taskId={}", taskId, e);
                    clinicalReviewService.markFailed(taskId, "AI 续跑异常");
                    return Flux.just(sse("error", errorJson("AI 复核续跑异常，请稍后重试")),
                            sse("done", doneJson(state, "failed", "AI 复核续跑异常")));
                });
    }

    private Flux<ServerSentEvent<String>> handleModelEvent(Long taskId, ReviewStreamState state, String line) {
        try {
            JsonNode json = objectMapper.readTree(line);
            String type = json.path("type").asText("");
            switch (type) {
                case "token" -> {
                    String content = json.path("content").asText("");
                    state.answer.append(content);
                    return Flux.just(sse("chunk", json(Map.of(
                            "type", "chunk",
                            "talkId", state.task.getTalkId().toString(),
                            "content", content))));
                }
                case "node_start", "node_done", "node_token" -> {
                    String step = json.path("node").asText("");
                    String label = json.path("label").asText("");
                    String content = json.path("content").asText("");
                    if (content.isBlank() && "node_done".equals(type)) {
                        content = json.path("summary").asText("");
                    }
                    String status = json.path("status").asText(
                            "node_done".equals(type) ? "done" : "running");
                    if (!"node_token".equals(type)) {
                        rememberStep(state, step, label, content, status);
                    }
                    Map<String, Object> thinking = new LinkedHashMap<>();
                    thinking.put("step", step);
                    thinking.put("title", label);
                    thinking.put("content", content);
                    thinking.put("status", status);
                    Map<String, Object> payload = new LinkedHashMap<>();
                    payload.put("type", "thinking");
                    payload.put("thinking", thinking);
                    return Flux.just(sse("thinking", json(payload)));
                }
                case "human_review" -> {
                    state.reviewAgain = true;
                    JsonNode reviewPayload = json.path("payload");
                    clinicalReviewService.markPendingAgain(taskId, reviewPayload);
                    Map<String, Object> payload = new LinkedHashMap<>();
                    payload.put("type", "human_review");
                    payload.put("taskId", taskId);
                    payload.put("talkId", state.task.getTalkId().toString());
                    payload.put("threadId", state.task.getThreadId());
                    payload.put("status", "PENDING");
                    payload.put("payload", objectMapper.convertValue(reviewPayload,
                            new TypeReference<Map<String, Object>>() {}));
                    return Flux.just(sse("human_review", json(payload)));
                }
                case "done" -> {
                    state.doneFromPython = true;
                    if (!json.path("usage").isMissingNode()) {
                        state.usage = objectMapper.convertValue(json.path("usage"),
                                new TypeReference<Map<String, Object>>() {});
                    }
                    return Flux.empty();
                }
                case "error" -> {
                    state.error = true;
                    String message = json.path("error").path("message").asText(
                            json.path("content").asText("AI 复核失败"));
                    clinicalReviewService.markFailed(taskId, message);
                    Map<String, Object> error = new LinkedHashMap<>();
                    error.put("type", "error");
                    error.put("message", message);
                    error.put("error", objectMapper.convertValue(json.path("error"),
                            new TypeReference<Map<String, Object>>() {}));
                    return Flux.just(sse("error", json(error)));
                }
                default -> {
                    return Flux.empty();
                }
            }
        } catch (Exception e) {
            log.warn("解析 HITL 续跑事件失败: taskId={}, err={}", taskId, e.getMessage());
            return Flux.empty();
        }
    }

    private ServerSentEvent<String> finalizeStream(Long taskId, ReviewStreamState state) {
        if (state.error) {
            return sse("done", doneJson(state, "failed", "复核续跑失败"));
        }
        if (state.reviewAgain) {
            return sse("done", doneJson(state, "human_review_pending", null));
        }

        String answer = state.answer.toString().trim();
        if (answer.isBlank()) {
            clinicalReviewService.markFailed(taskId, "复核续跑未生成报告");
            return sse("done", doneJson(state, "failed", "复核续跑未生成报告"));
        }

        try {
            Map<String, Object> round = new LinkedHashMap<>();
            round.put("events", state.events);
            round.put("usage", state.usage);
            round.put("elapsedSeconds", Math.max(1,
                    Duration.between(state.startedAt, LocalDateTime.now()).getSeconds()));
            round.put("humanReview", Map.of(
                    "taskId", taskId,
                    "status", "COMPLETED",
                    "decision", state.approved ? "APPROVED" : "REJECTED"
            ));
            conversationPersistenceService.appendAssistantMessage(
                    state.task.getDoctorId(), state.task.getTalkId(), answer,
                    objectMapper.writeValueAsString(round));
            stringRedisTemplate.delete("chat:history:" + state.task.getDoctorId() + ":" + state.task.getTalkId());
            clinicalReviewService.markCompleted(taskId, answer);
            log.info("HITL 续跑完成并落库: taskId={}, talkId={}, answerLen={}",
                    taskId, state.task.getTalkId(), answer.length());
            return sse("done", doneJson(state, "completed", null));
        } catch (Exception e) {
            log.error("HITL 续跑报告落库失败: taskId={}", taskId, e);
            clinicalReviewService.markFailed(taskId, "报告落库失败");
            return sse("done", doneJson(state, "failed", "报告落库失败"));
        }
    }

    private void rememberStep(ReviewStreamState state, String step, String label,
                              String content, String status) {
        if (!StringUtils.hasText(step)) return;
        for (int i = state.events.size() - 1; i >= 0; i--) {
            Map<String, Object> item = state.events.get(i);
            if (step.equals(item.get("step"))) {
                item.put("title", label);
                item.put("content", content);
                item.put("status", status);
                return;
            }
        }
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("step", step);
        item.put("title", label);
        item.put("content", content);
        item.put("status", status);
        item.put("startedAt", System.currentTimeMillis());
        state.events.add(item);
    }

    private String doneJson(ReviewStreamState state, String status, String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "done");
        payload.put("talkId", state.task.getTalkId().toString());
        payload.put("status", status);
        payload.put("threadId", "human_review_pending".equals(status) ? state.task.getThreadId() : null);
        payload.put("usage", state.usage);
        if (message != null) payload.put("message", message);
        return json(payload);
    }

    private String errorJson(String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "error");
        payload.put("message", message);
        return json(payload);
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            return "{\"type\":\"error\",\"message\":\"事件序列化失败\"}";
        }
    }

    private ServerSentEvent<String> sse(String type, String data) {
        return ServerSentEvent.<String>builder().event(type).data(data).build();
    }

    private static final class ReviewStreamState {
        private final ClinicalReviewTask task;
        private final StringBuilder answer = new StringBuilder();
        private final List<Map<String, Object>> events = new ArrayList<>();
        private final LocalDateTime startedAt = LocalDateTime.now();
        private final boolean approved;
        private Map<String, Object> usage;
        private boolean reviewAgain;
        private boolean doneFromPython;
        private boolean error;

        private ReviewStreamState(ClinicalReviewTask task, boolean approved) {
            this.task = task;
            this.approved = approved;
        }
    }
}
