package com.it.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.Map;

/**
 * 知识库管理代理: 前端上传/删除指南 PDF → Python 模型服务热更新向量库。
 */
@Slf4j
@RestController
@RequestMapping("/api/kb")
@RequiredArgsConstructor
public class KbController {

    private final WebClient webClient;

    @PostMapping("/upload")
    public Mono<Map<String, Object>> upload(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "token", required = false) String token
    ) {
        if (token != null && !token.isBlank()) body.put("token", token.trim());
        return webClient.post().uri("/model/kb/upload")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(e -> Mono.just(Map.of("code", 0, "msg", "模型服务暂不可用", "data", (Object) null)));
    }

    @GetMapping("/status")
    public Mono<Map<String, Object>> status(@RequestHeader(value = "token", required = false) String token) {
        return webClient.get().uri("/model/kb/status")
                .header("token", token == null ? "" : token.trim())
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(e -> Mono.just(Map.of("code", 0, "msg", "模型服务暂不可用", "data", (Object) null)));
    }

    @DeleteMapping("/documents/{name}")
    public Mono<Map<String, Object>> delete(
            @PathVariable String name,
            @RequestHeader(value = "token", required = false) String token
    ) {
        return webClient.delete().uri("/model/kb/documents/{name}", name)
                .header("token", token == null ? "" : token.trim())
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(e -> Mono.just(Map.of("code", 0, "msg", "模型服务暂不可用", "data", (Object) null)));
    }

    @PostMapping("/reload")
    public Mono<Map<String, Object>> reload(@RequestHeader(value = "token", required = false) String token) {
        return webClient.post().uri("/model/kb/reload")
                .header("token", token == null ? "" : token.trim())
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {})
                .onErrorResume(e -> Mono.just(Map.of("code", 0, "msg", "模型服务暂不可用", "data", (Object) null)));
    }
}
