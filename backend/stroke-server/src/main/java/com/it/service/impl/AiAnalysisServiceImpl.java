package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.mapper.AiOpinionMapper;
import com.it.mapper.HealthDataMapper;
import com.it.mapper.PatientMapper;
import com.it.po.uo.AiAnalyzeParam;
import com.it.po.uo.AiSyncTalkParam;
import com.it.po.uo.ConversationMessage;
import com.it.po.vo.AiAnalyzeVO;
import com.it.po.vo.AiOpinionVO;
import com.it.po.vo.AiSyncTalkVO;
import com.it.pojo.AiOpinion;
import com.it.pojo.HealthData;
import com.it.pojo.Patient;
import com.it.pojo.Result;
import com.it.service.IAiAnalysisService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RSemaphore;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
public class AiAnalysisServiceImpl implements IAiAnalysisService {

    private final WebClient           webClient;
    private final PatientMapper       patientMapper;
    private final HealthDataMapper    healthDataMapper;
    private final AiOpinionMapper     aiOpinionMapper;
    private final ObjectMapper        objectMapper;
    private final StringRedisTemplate stringRedisTemplate;
    private final RedissonClient      redissonClient;

    // ── 并发控制与容错 ──────────────────────────────────────────────────────────
    /** AI 分析并发信号量 key，与 AIStreamingServiceImpl 共享同一把锁 */
    private static final String SEMAPHORE_KEY  = "ai:concurrent";
    /** 分析请求最长等待获取信号量的时间 */
    private static final long   ACQUIRE_WAIT_S = 10;
    /** syncTalk 调用 /ai/quick-analyze 的单次超时 */
    private static final Duration QUICK_ANALYZE_TIMEOUT = Duration.ofSeconds(60);
    /** analyze 调用 /ai/analyze 的单次超时 */
    private static final Duration ANALYZE_TIMEOUT       = Duration.ofSeconds(60);
    /** 最大重试次数（仅对超时可重试） */
    private static final int    MAX_RETRIES   = 2;

    // ─────────────────────────────────────────────────────────────────────────
    // 熔断与并发控制
    // ─────────────────────────────────────────────────────────────────────────

    /** 检查 AI 服务熔断开关（与 AIStreamingServiceImpl 共享同一个 Redis key） */
    private boolean allowAICircuit() {
        try {
            String state = stringRedisTemplate.opsForValue().get("ai:circuit");
            return !"open".equals(state);
        } catch (Exception e) {
            log.warn("检查熔断开关失败，默认放行: {}", e.getMessage());
            return true; // Redis 不可用时默认放行
        }
    }

    /** 尝试获取并发信号量，超时返回 false */
    private boolean tryAcquireSemaphore() {
        try {
            RSemaphore semaphore = redissonClient.getSemaphore(SEMAPHORE_KEY);
            return semaphore.tryAcquire(ACQUIRE_WAIT_S, TimeUnit.SECONDS);
        } catch (Exception e) {
            log.warn("获取信号量失败，默认放行: {}", e.getMessage());
            return true; // Redis 不可用时默认放行
        }
    }

    /** 释放并发信号量 */
    private void releaseSemaphore() {
        try {
            RSemaphore semaphore = redissonClient.getSemaphore(SEMAPHORE_KEY);
            semaphore.release();
        } catch (Exception e) {
            log.warn("释放信号量失败: {}", e.getMessage());
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // POST /api/ai/analyze
    // ─────────────────────────────────────────────────────────────────────────
    @Transactional
    @Override
    public Result analyze(AiAnalyzeParam param, String token) {
        if (param.getPatientId() == null || !StringUtils.hasText(param.getData())) {
            return Result.error("patientId 和 data 不能为空");
        }

        Patient patient = patientMapper.selectById(param.getPatientId());
        if (patient == null) {
            return Result.error("病人不存在");
        }

        // 持久化本次健康数据
        HealthData hd = new HealthData();
        hd.setPatientId(param.getPatientId());
        hd.setDataContent(param.getData());
        healthDataMapper.insert(hd);

        // 熔断检查
        if (!allowAICircuit()) {
            return Result.error("AI 服务当前不可用，请稍后重试");
        }

        // 调用 Python /ai/analyze（独立 HealthRiskAnalyzer，不依赖主推理链）
        Map<String, Object> body = new HashMap<>();
        body.put("patientId", param.getPatientId());
        body.put("data", param.getData());
        body.put("token", token == null ? "" : token);

        JsonNode responseNode = callWithRetry("/ai/analyze", body, ANALYZE_TIMEOUT);
        if (responseNode == null) {
            return Result.error("AI 分析服务异常，请稍后重试");
        }

        // 提取结构化字段
        JsonNode data       = responseNode.path("data");
        String riskLevel    = data.path("riskLevel").asText("中风险");
        String suggestion   = data.path("suggestion").asText("");
        String analysisDetails = data.path("analysisDetails").asText("");

        // 覆盖式更新：先删除该患者所有已有的 AI 意见记录，再写入新的
        LambdaQueryWrapper<AiOpinion> deleteWrapper = new LambdaQueryWrapper<>();
        deleteWrapper.eq(AiOpinion::getPatientId, param.getPatientId());
        int deletedCount = aiOpinionMapper.delete(deleteWrapper);
        if (deletedCount > 0) {
            log.info("覆盖式更新：已删除患者 {} 的 {} 条旧 AI 意见记录", param.getPatientId(), deletedCount);
        }

        AiOpinion opinion = new AiOpinion();
        opinion.setPatientId(param.getPatientId());
        opinion.setRiskLevel(riskLevel);
        opinion.setSuggestions(StringUtils.hasText(suggestion) ? suggestion : analysisDetails);
        opinion.setAnalysisDetails(StringUtils.hasText(analysisDetails) ? analysisDetails : suggestion);
        opinion.setSourceType("health_data");
        opinion.setSourceId(hd.getId());
        aiOpinionMapper.insert(opinion);

        // 清除患者相关 Redis 缓存，确保前端拉取到最新数据
        evictPatientCaches(param.getPatientId());

        AiAnalyzeVO vo = new AiAnalyzeVO();
        vo.setRiskLevel(riskLevel);
        vo.setSuggestion(opinion.getSuggestions());
        vo.setAnalysisDetails(opinion.getAnalysisDetails());
        return Result.success(vo);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // POST /api/ai/sync-talk
    // ─────────────────────────────────────────────────────────────────────────
    @Transactional
    @Override
    public Result syncTalk(AiSyncTalkParam param, String token) {
        if (param.getPatientId() == null || param.getConversation() == null || param.getConversation().isEmpty()) {
            return Result.error("patientId 和 conversation 不能为空");
        }

        // 熔断检查
        if (!allowAICircuit()) {
            return Result.error("AI 服务当前不可用，请稍后重试");
        }

        Patient patient = patientMapper.selectById(param.getPatientId());
        if (patient == null) {
            return Result.error("病人不存在");
        }

        String conversationText = buildConversationText(param.getConversation());

        // 构建分析问题：直接使用 /ai/quick-analyze（轻量 qwen-turbo，秒级返回）
        StringBuilder questionBuilder = new StringBuilder();
        questionBuilder.append("请根据以下医患对话内容");
        if (param.isMergeWithHistory() && StringUtils.hasText(patient.getHistory())) {
            questionBuilder.append("并结合病人既往病史（").append(patient.getHistory()).append("）");
        }
        questionBuilder.append("，对病人进行综合健康风险评估，给出风险等级（低风险/中风险/高风险）、快速专业意见和关键要点。\n\n");
        questionBuilder.append("【对话内容】\n").append(conversationText);

        String question = questionBuilder.toString();

        // 调用 /ai/quick-analyze（轻量非流式，60s 超时 + 指数退避重试）
        Map<String, Object> body = new HashMap<>();
        body.put("question", question);
        body.put("token", token == null ? "" : token);

        JsonNode responseNode = callWithRetry("/ai/quick-analyze", body, QUICK_ANALYZE_TIMEOUT);
        if (responseNode == null) {
            return Result.error("AI 分析服务异常，请稍后重试");
        }

        // 解析 /ai/quick-analyze 响应：{ code, msg, data: { quickOpinion, keyPoints, riskLevel } }
        JsonNode data = responseNode.path("data");
        String riskLevel = data.path("riskLevel").asText("");
        if (!StringUtils.hasText(riskLevel) || riskLevel.contains("风险")) {
            // 已是有效风险等级，直接使用
        } else {
            riskLevel = "中风险"; // 兜底
        }
        // 规范化风险等级
        riskLevel = normalizeRiskLevel(riskLevel);

        String suggestion = data.path("quickOpinion").asText("");
        if (!StringUtils.hasText(suggestion)) {
            suggestion = "建议结合临床实际进一步评估。";
        }

        // keyPoints 数组拼接为分析详情
        StringBuilder analysisBuilder = new StringBuilder();
        JsonNode keyPoints = data.path("keyPoints");
        if (keyPoints.isArray()) {
            for (JsonNode kp : keyPoints) {
                if (analysisBuilder.length() > 0) analysisBuilder.append("；");
                analysisBuilder.append(kp.asText());
            }
        }
        String analysisDetails = analysisBuilder.length() > 0
                ? analysisBuilder.toString()
                : suggestion;

        // 覆盖式更新：先删除该患者所有已有的 AI 意见记录，再写入新的
        LambdaQueryWrapper<AiOpinion> deleteWrapper = new LambdaQueryWrapper<>();
        deleteWrapper.eq(AiOpinion::getPatientId, param.getPatientId());
        int deletedCount = aiOpinionMapper.delete(deleteWrapper);
        if (deletedCount > 0) {
            log.info("覆盖式更新（syncTalk）：已删除患者 {} 的 {} 条旧 AI 意见记录", param.getPatientId(), deletedCount);
        }

        AiOpinion opinion = new AiOpinion();
        opinion.setPatientId(param.getPatientId());
        opinion.setRiskLevel(riskLevel);
        opinion.setSuggestions(suggestion);
        opinion.setAnalysisDetails(analysisDetails);
        opinion.setSourceType("sync_talk");
        opinion.setSourceId(param.getTalkId());
        aiOpinionMapper.insert(opinion);

        // 清除患者相关 Redis 缓存，确保前端拉取到最新数据
        evictPatientCaches(param.getPatientId());

        AiOpinionVO opinionVO = new AiOpinionVO();
        opinionVO.setRiskLevel(riskLevel);
        opinionVO.setSuggestion(suggestion);
        opinionVO.setAnalysisDetails(analysisDetails);
        opinionVO.setLastUpdatedAt(LocalDateTime.now());

        AiSyncTalkVO vo = new AiSyncTalkVO();
        vo.setPatientId(param.getPatientId());
        vo.setUpdated(true);
        vo.setAiOpinion(opinionVO);
        vo.setTalkId(param.getTalkId());
        return Result.success(vo);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 私有辅助方法
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * 带熔断、并发控制、重试的轻量 HTTP 调用。
     * <p>
     * 仅用于 /ai/analyze 和 /ai/quick-analyze 两个非流式端点。
     * 超时异常自动重试（指数退避），非超时异常不重试。
     *
     * @param uri     目标路径
     * @param body    请求体
     * @param timeout 单次调用超时
     * @return 解析后的 JSON 响应节点，失败返回 null
     */
    private JsonNode callWithRetry(String uri, Map<String, Object> body, Duration timeout) {
        boolean acquired = tryAcquireSemaphore();
        if (!acquired) {
            log.warn("AI 并发已满，拒绝请求: uri={}", uri);
            return null;
        }

        try {
            Exception lastError = null;
            for (int attempt = 0; attempt <= MAX_RETRIES; attempt++) {
                try {
                    String raw = webClient.post()
                            .uri(uri)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(body)
                            .retrieve()
                            .bodyToMono(String.class)
                            .timeout(timeout)
                            .block();
                    return objectMapper.readTree(raw);
                } catch (Exception e) {
                    // 检查是否为超时异常（Reactor 的 timeout() 产生 TimeoutException，
                    // 但 block() 可能将其包装为 RuntimeException 的 cause）
                    if (isTimeoutException(e)) {
                        lastError = e;
                        if (attempt < MAX_RETRIES) {
                            long backoffMs = (attempt + 1) * 2000L; // 2s, 4s 指数退避
                            log.warn("调用 {} 超时，{}ms 后重试 ({}/{})", uri, backoffMs, attempt + 1, MAX_RETRIES);
                            try { Thread.sleep(backoffMs); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); break; }
                            continue; // 重试
                        }
                        // 已达最大重试次数，跳出到统一错误日志
                        break;
                    }
                    // HTTP 4xx/5xx 不重试
                    if (e instanceof WebClientResponseException wcre) {
                        log.error("调用 {} 返回 HTTP {}: {}", uri, wcre.getStatusCode().value(), wcre.getResponseBodyAsString());
                    } else {
                        log.error("调用 {} 失败: {}", uri, e.getMessage(), e);
                    }
                    return null;
                }
            }
            if (lastError != null) {
                log.error("调用 {} 重试 {} 次后仍失败: {}", uri, MAX_RETRIES, lastError.getMessage());
            }
            return null;
        } finally {
            releaseSemaphore();
        }
    }

    /** 递归检查异常链中是否包含 TimeoutException */
    private boolean isTimeoutException(Throwable e) {
        Throwable root = e;
        while (root != null) {
            if (root instanceof java.util.concurrent.TimeoutException) return true;
            root = root.getCause();
        }
        return false;
    }

    private String buildConversationText(List<ConversationMessage> messages) {
        StringBuilder sb = new StringBuilder();
        for (ConversationMessage msg : messages) {
            sb.append(msg.getRole()).append(": ").append(msg.getContent()).append("\n");
        }
        return sb.toString();
    }

    /** 规范化 /ai/quick-analyze 返回的风险等级字符串 */
    private String normalizeRiskLevel(String text) {
        if (text == null) return "中风险";
        if (text.contains("高")) return "高风险";
        if (text.contains("中")) return "中风险";
        if (text.contains("低")) return "低风险";
        return "中风险";
    }

    /**
     * 清除指定患者的 Redis 缓存（详情缓存 + 分页缓存模糊匹配），
     * 确保覆盖式更新 AI 意见后前端能立即拉取到最新数据。
     */
    private void evictPatientCaches(Long patientId) {
        try {
            // 清除患者详情缓存
            stringRedisTemplate.delete("patient:detail:" + patientId);
            // 模糊匹配清除该患者所属医生的所有分页缓存
            var pageKeys = stringRedisTemplate.keys("patient:page:*");
            if (pageKeys != null && !pageKeys.isEmpty()) {
                stringRedisTemplate.delete(pageKeys);
            }
            log.debug("已清除患者 {} 的 Redis 缓存", patientId);
        } catch (Exception e) {
            log.warn("清除患者缓存失败: patientId={}, err={}", patientId, e.getMessage());
        }
    }
}
