package com.it.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.po.uo.ReviewResumeParam;
import com.it.pojo.ClinicalReviewTask;
import com.it.pojo.Result;
import com.it.service.ClinicalReviewResumeService;
import com.it.service.ClinicalReviewService;
import com.it.utils.ThreadLocalUtil;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@RestController
@RequestMapping("/api/clinical-reviews")
@RequiredArgsConstructor
public class ClinicalReviewController {

    private final ClinicalReviewService clinicalReviewService;
    private final ClinicalReviewResumeService resumeService;
    private final ObjectMapper objectMapper;

    @GetMapping("/pending")
    public Result pending(@RequestParam(defaultValue = "20") int limit) {
        List<Map<String, Object>> data = clinicalReviewService
                .listPending(currentDoctorId(), limit)
                .stream()
                .map(clinicalReviewService::toView)
                .toList();
        return Result.success(data);
    }

    @GetMapping("/by-talk/{talkId}")
    public Result byTalk(@PathVariable Long talkId) {
        Optional<ClinicalReviewTask> task = clinicalReviewService.findPendingByTalk(currentDoctorId(), talkId);
        return Result.success(task.map(clinicalReviewService::toView).orElse(null));
    }

    @PostMapping(value = "/{taskId}/resume", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> resume(
            @PathVariable Long taskId,
            @RequestBody ReviewResumeParam param,
            @RequestHeader(value = "token", required = false) String token,
            @RequestHeader(value = "Authorization", required = false) String authorization,
            HttpServletResponse response) {
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
        String upstreamToken = resolveToken(token, authorization);
        if (upstreamToken == null || upstreamToken.isBlank()) {
            return Flux.just(errorEvent("缺少登录令牌"));
        }
        if (param == null || param.getApproved() == null) {
            return Flux.just(errorEvent("approved 不能为空"));
        }
        if (!Boolean.TRUE.equals(param.getApproved())
                && (param.getFeedback() == null || param.getFeedback().isBlank())) {
            return Flux.just(errorEvent("驳回会诊时必须填写修改意见"));
        }
        try {
            return resumeService.resume(
                    currentDoctorId(),
                    taskId,
                    upstreamToken,
                    param.getApproved(),
                    param.getFeedback() == null ? "" : param.getFeedback()
            );
        } catch (Exception e) {
            return Flux.just(errorEvent(e.getMessage()));
        }
    }

    private ServerSentEvent<String> errorEvent(String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "error");
        payload.put("message", message);
        try {
            return ServerSentEvent.<String>builder()
                    .event("error")
                    .data(objectMapper.writeValueAsString(payload))
                    .build();
        } catch (Exception e) {
            return ServerSentEvent.<String>builder()
                    .event("error")
                    .data("{\"type\":\"error\",\"message\":\"复核请求失败\"}")
                    .build();
        }
    }

    private String resolveToken(String token, String authorization) {
        if (token != null && !token.isBlank()) {
            return token.startsWith("Bearer ") ? token.substring(7).trim() : token.trim();
        }
        if (authorization != null && !authorization.isBlank()) {
            return authorization.startsWith("Bearer ")
                    ? authorization.substring(7).trim()
                    : authorization.trim();
        }
        return null;
    }

    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
