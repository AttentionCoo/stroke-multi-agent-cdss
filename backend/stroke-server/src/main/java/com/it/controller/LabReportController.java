package com.it.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.Map;

/**
 * 化验单拍照解析代理: 前端 → Java → Python 视觉模型(qwen-vl-plus)结构化提取,
 * 供绿道评估表单自动回填(血压/血糖/血小板/INR 等)。
 */
@Slf4j
@RestController
@RequestMapping("/api/lab-report")
@RequiredArgsConstructor
public class LabReportController {

    private final WebClient webClient;

    @PostMapping("/extract")
    public Mono<Map<String, Object>> extract(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "token", required = false) String token
    ) {
        if (token != null && !token.isBlank()) {
            body.put("token", token.trim());
        }
        return webClient.post()
                .uri("/model/lab_extract")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(e -> {
                    log.warn("化验单解析调用失败: {}", e.getMessage());
                    return Mono.just(Map.of(
                            "code", 0,
                            "msg", "模型服务暂不可用，请稍后重试",
                            "data", (Object) null
                    ));
                });
    }
}
