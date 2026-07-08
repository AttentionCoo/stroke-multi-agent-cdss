package com.it.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.pojo.Result;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * PubMed 文献检索接口（医生学习 - 学习资料板块使用）。
 * 通过 WebClient 代理调用 Python 模型层的 /model/pubmed/search，
 * 与 AI 问答 SSE 管线完全解耦，返回普通 JSON。
 */
@RestController
@CrossOrigin("*")
@RequestMapping("/api/pubmed")
@Slf4j
@RequiredArgsConstructor
public class PubMedController {

    private final WebClient webClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * POST /api/pubmed/search
     * 请求体：{ "query": "acute ischemic stroke", "maxResults": 5 }
     * 响应：{ "code": 1, "msg": "success", "data": { "papers": [...] } }
     */
    @PostMapping("/search")
    public Result search(@RequestBody Map<String, Object> body) {
        String query = String.valueOf(body.getOrDefault("query", "")).trim();
        int maxResults = 5;
        Object maxObj = body.get("maxResults");
        if (maxObj instanceof Number) {
            maxResults = ((Number) maxObj).intValue();
        }

        if (query.isEmpty()) {
            return Result.success(Map.of("papers", List.of()));
        }

        // 获取 JWT token 并透传给 Python（Python 端 pubmed/search 不校验 token，但保持一致）
        Map<String, Object> pyBody = new HashMap<>();
        pyBody.put("query", query);
        pyBody.put("max_results", maxResults);

        try {
            String responseStr = webClient.post()
                    .uri("/model/pubmed/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(pyBody)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            JsonNode root = objectMapper.readTree(responseStr);
            JsonNode data = root.path("data");
            return Result.success(objectMapper.convertValue(data, Object.class));
        } catch (Exception e) {
            log.error("PubMed 检索代理失败: query={}, err={}", query, e.getMessage(), e);
            return Result.success(Map.of("papers", List.of()));
        }
    }
}
