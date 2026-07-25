package com.it.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import reactor.core.publisher.Flux;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AIStreamingServiceImplTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private AIStreamingServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new AIStreamingServiceImpl(null, null, null, null, null, null);
    }

    @Test
    void nodeStartShouldBecomeRunningThinkingEvent() throws Exception {
        JsonNode response = parseOne("""
                {"type":"node_start","node":"vision","label":"正在分析影像...","content":"共 2 张图片","status":"running"}
                """);

        assertEquals("thinking", response.path("type").asText());
        assertEquals("vision", response.path("thinking").path("step").asText());
        assertEquals("共 2 张图片", response.path("thinking").path("content").asText());
        assertEquals("running", response.path("thinking").path("status").asText());
    }

    @Test
    void nodeDoneShouldExposeSummaryAsThinkingContent() throws Exception {
        JsonNode response = parseOne("""
                {"type":"node_done","node":"analysis","label":"病例结构化分析","summary":"{\\"复杂度\\":\\"critical\\"}","status":"done"}
                """);

        assertEquals("thinking", response.path("type").asText());
        assertEquals("analysis", response.path("thinking").path("step").asText());
        assertEquals("病例结构化分析", response.path("thinking").path("title").asText());
        assertEquals("{\"复杂度\":\"critical\"}", response.path("thinking").path("content").asText());
        assertEquals("done", response.path("thinking").path("status").asText());
    }

    private JsonNode parseOne(String line) throws Exception {
        Flux<String> responseFlux = ReflectionTestUtils.invokeMethod(
                service,
                "parseModelLine",
                line,
                1L,
                new String[]{"测试会话"},
                new String[]{""},
                new StringBuilder());
        List<String> responses = responseFlux.collectList().block();

        assertEquals(1, responses.size());
        return objectMapper.readTree(responses.get(0));
    }
}
