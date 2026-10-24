package com.it.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.pojo.Talk;
import com.it.service.ClinicalReviewService;
import com.it.service.IContService;
import com.it.service.ITalkService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AIStreamingServiceImplTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private AIStreamingServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new AIStreamingServiceImpl(null, null, null, null, null, null, null, null);
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

    @Test
    void patientScopeConflictShouldStopBeforeModelCall() throws Exception {
        WebClient webClient = mock(WebClient.class);
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> valueOperations = mock(ValueOperations.class);
        ITalkService talkService = mock(ITalkService.class);
        IContService contService = mock(IContService.class);
        PatientMemoryService patientMemoryService = mock(PatientMemoryService.class);

        when(redis.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("ai:circuit")).thenReturn(null);
        when(valueOperations.get("chat:history:3:11")).thenReturn("[]");
        when(talkService.getById(11L)).thenReturn(Talk.builder()
                .id(11L)
                .userId(3L)
                .patientId(8L)
                .title("测试对话")
                .content("")
                .build());
        when(patientMemoryService.build(3L, 7L, 11L, ""))
                .thenThrow(new PatientMemoryService.PatientContextException("当前对话已关联其他患者"));

        AIStreamingServiceImpl streamingService = new AIStreamingServiceImpl(
                webClient,
                redis,
                mock(RedissonClient.class),
                talkService,
                contService,
                mock(ConversationPersistenceService.class),
                patientMemoryService,
                mock(ClinicalReviewService.class)
        );

        List<String> events = streamingService
                .streamChat(3L, 11L, "患者情况", "token", List.of(), 7L, false)
                .collectList()
                .block();

        assertEquals(2, events.size());
        assertEquals("error", objectMapper.readTree(events.get(0)).path("type").asText());
        assertEquals("done", objectMapper.readTree(events.get(1)).path("type").asText());
        verifyNoInteractions(webClient);
    }

    @Test
    void humanReviewShouldCreateTaskAndEmitReviewEvent() throws Exception {
        ClinicalReviewService reviewService = mock(ClinicalReviewService.class);
        com.it.pojo.ClinicalReviewTask task = new com.it.pojo.ClinicalReviewTask();
        task.setId(99L);
        when(reviewService.createOrUpdatePending(
                org.mockito.ArgumentMatchers.eq(1L),
                org.mockito.ArgumentMatchers.eq("thread-1"),
                org.mockito.ArgumentMatchers.any()))
                .thenReturn(java.util.Optional.of(task));

        AIStreamingServiceImpl streamingService = new AIStreamingServiceImpl(
                null, null, null, null, null, null, null, reviewService);
        Flux<String> responseFlux = ReflectionTestUtils.invokeMethod(
                streamingService,
                "parseModelLine",
                "{\"type\":\"human_review\",\"thread_id\":\"thread-1\",\"status\":\"pending\",\"payload\":{\"consensus\":\"待复核共识\"}}",
                1L,
                new String[]{"测试会话"},
                new String[]{""},
                new StringBuilder(),
                new AIStreamingServiceImpl.RoundAccumulator(),
                new java.util.HashMap[]{null});
        List<String> responses = responseFlux.collectList().block();

        assertEquals(1, responses.size());
        JsonNode response = objectMapper.readTree(responses.get(0));
        assertEquals("human_review", response.path("type").asText());
        assertEquals(99L, response.path("taskId").asLong());
        assertEquals("待复核共识", response.path("payload").path("consensus").asText());
    }
    private JsonNode parseOne(String line) throws Exception {
        Flux<String> responseFlux = ReflectionTestUtils.invokeMethod(
                service,
                "parseModelLine",
                line,
                1L,
                new String[]{"测试会话"},
                new String[]{""},
                new StringBuilder(),
                new AIStreamingServiceImpl.RoundAccumulator(),
                new java.util.HashMap[]{null});
        List<String> responses = responseFlux.collectList().block();

        assertEquals(1, responses.size());
        return objectMapper.readTree(responses.get(0));
    }
}
