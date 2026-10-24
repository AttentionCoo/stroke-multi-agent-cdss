package com.it.controller;

import com.it.po.uo.ClinicalToolCallParam;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

import java.util.LinkedHashMap;
import java.util.Map;

/** 将模型层 18 个临床工具安全代理给 Web 前端。 */
@RestController
@RequestMapping("/api/tools")
@RequiredArgsConstructor
public class ClinicalToolController {

    private final WebClient webClient;

    @GetMapping("/list")
    public Mono<Object> list() {
        return webClient.get()
                .uri("/model/tools/list")
                .retrieve()
                .bodyToMono(Object.class)
                .onErrorResume(e -> Mono.just(error("模型工具服务暂不可用")));
    }

    @PostMapping("/call")
    public Mono<Object> call(@RequestBody ClinicalToolCallParam param,
                             @RequestHeader(value = "token", required = false) String token,
                             @RequestHeader(value = "Authorization", required = false) String authorization) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", param.getName());
        body.put("arguments", param.getArguments() == null ? Map.of() : param.getArguments());
        body.put("token", resolveToken(token, authorization));
        return webClient.post()
                .uri("/model/tools/call")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(Object.class)
                .onErrorResume(WebClientResponseException.class,
                        e -> Mono.just(error("工具调用失败: " + e.getStatusCode())))
                .onErrorResume(e -> Mono.just(error("模型工具服务暂不可用")));
    }

    private String resolveToken(String token, String authorization) {
        if (token != null && !token.isBlank()) {
            return token.startsWith("Bearer ") ? token.substring(7).trim() : token.trim();
        }
        if (authorization != null && !authorization.isBlank()) {
            return authorization.startsWith("Bearer ")
                    ? authorization.substring(7).trim() : authorization.trim();
        }
        return "";
    }

    private Map<String, Object> error(String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("code", 0);
        result.put("msg", message);
        return result;
    }
}
