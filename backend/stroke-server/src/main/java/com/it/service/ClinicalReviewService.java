package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.mapper.ClinicalReviewTaskMapper;
import com.it.mapper.TalkMapper;
import com.it.pojo.ClinicalReviewTask;
import com.it.pojo.Talk;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** AI 会诊医生复核任务的持久化与权限校验。 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ClinicalReviewService {

    private final ClinicalReviewTaskMapper reviewTaskMapper;
    private final TalkMapper talkMapper;
    private final ObjectMapper objectMapper;

    /** Python 端发出 human_review 事件时创建/刷新待复核任务。 */
    @Transactional
    public Optional<ClinicalReviewTask> createOrUpdatePending(Long talkId, String threadId, JsonNode payload) {
        if (talkId == null || !StringUtils.hasText(threadId)) {
            return Optional.empty();
        }
        Talk talk = talkMapper.selectById(talkId);
        if (talk == null || talk.getUserId() == null) {
            log.warn("无法创建复核任务: talk 不存在, talkId={}", talkId);
            return Optional.empty();
        }

        ClinicalReviewTask task = reviewTaskMapper.selectOne(
                new LambdaQueryWrapper<ClinicalReviewTask>()
                        .eq(ClinicalReviewTask::getTalkId, talkId)
                        .eq(ClinicalReviewTask::getThreadId, threadId)
                        .last("LIMIT 1")
        );
        LocalDateTime now = LocalDateTime.now();
        if (task == null) {
            task = new ClinicalReviewTask();
            task.setDoctorId(talk.getUserId());
            task.setTalkId(talkId);
            task.setThreadId(threadId);
            task.setStatus("PENDING");
            task.setPayloadJson(payload == null ? "{}" : payload.toString());
            task.setCreateTime(now);
            task.setUpdateTime(now);
            reviewTaskMapper.insert(task);
            log.info("创建医生复核任务: taskId={}, talkId={}, threadId={}", task.getId(), talkId, threadId);
        } else {
            task.setStatus("PENDING");
            task.setPayloadJson(payload == null ? "{}" : payload.toString());
            task.setUpdateTime(now);
            reviewTaskMapper.updateById(task);
            log.info("刷新医生复核任务: taskId={}, talkId={}", task.getId(), talkId);
        }
        return Optional.of(task);
    }

    public long countPending(Long doctorId) {
        Long count = reviewTaskMapper.selectCount(new LambdaQueryWrapper<ClinicalReviewTask>()
                .eq(ClinicalReviewTask::getDoctorId, doctorId)
                .eq(ClinicalReviewTask::getStatus, "PENDING"));
        return count == null ? 0 : count;
    }

    public List<ClinicalReviewTask> listPending(Long doctorId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return reviewTaskMapper.selectList(new LambdaQueryWrapper<ClinicalReviewTask>()
                .eq(ClinicalReviewTask::getDoctorId, doctorId)
                .eq(ClinicalReviewTask::getStatus, "PENDING")
                .orderByDesc(ClinicalReviewTask::getUpdateTime)
                .last("LIMIT " + safeLimit));
    }

    /** 只允许对话所属医生读取复核任务。 */
    public Optional<ClinicalReviewTask> findPendingByTalk(Long doctorId, Long talkId) {
        Talk talk = talkMapper.selectById(talkId);
        if (talk == null || !doctorId.equals(talk.getUserId())) {
            return Optional.empty();
        }
        return Optional.ofNullable(reviewTaskMapper.selectOne(
                new LambdaQueryWrapper<ClinicalReviewTask>()
                        .eq(ClinicalReviewTask::getDoctorId, doctorId)
                        .eq(ClinicalReviewTask::getTalkId, talkId)
                        .eq(ClinicalReviewTask::getStatus, "PENDING")
                        .orderByDesc(ClinicalReviewTask::getUpdateTime)
                        .last("LIMIT 1")
        ));
    }

    public ClinicalReviewTask getOwned(Long doctorId, Long taskId) {
        ClinicalReviewTask task = reviewTaskMapper.selectById(taskId);
        if (task == null || !doctorId.equals(task.getDoctorId())) {
            throw new IllegalArgumentException("复核任务不存在或无权限");
        }
        return task;
    }

    @Transactional
    public void markDecision(Long taskId, boolean approved, String feedback) {
        ClinicalReviewTask task = reviewTaskMapper.selectById(taskId);
        if (task == null) return;
        task.setDecision(approved ? "APPROVED" : "REJECTED");
        task.setFeedback(feedback);
        task.setUpdateTime(LocalDateTime.now());
        reviewTaskMapper.updateById(task);
    }

    @Transactional
    public void markCompleted(Long taskId, String answer) {
        ClinicalReviewTask task = reviewTaskMapper.selectById(taskId);
        if (task == null) return;
        task.setStatus("COMPLETED");
        task.setAnswer(answer);
        task.setUpdateTime(LocalDateTime.now());
        reviewTaskMapper.updateById(task);
    }

    @Transactional
    public void markPendingAgain(Long taskId, JsonNode payload) {
        ClinicalReviewTask task = reviewTaskMapper.selectById(taskId);
        if (task == null) return;
        task.setStatus("PENDING");
        task.setPayloadJson(payload == null ? "{}" : payload.toString());
        task.setUpdateTime(LocalDateTime.now());
        reviewTaskMapper.updateById(task);
    }

    @Transactional
    public void markFailed(Long taskId, String reason) {
        ClinicalReviewTask task = reviewTaskMapper.selectById(taskId);
        if (task == null) return;
        task.setStatus("FAILED");
        task.setFeedback(reason);
        task.setUpdateTime(LocalDateTime.now());
        reviewTaskMapper.updateById(task);
    }

    public Map<String, Object> toView(ClinicalReviewTask task) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("taskId", task.getId());
        view.put("talkId", task.getTalkId());
        view.put("threadId", task.getThreadId());
        view.put("status", task.getStatus());
        view.put("decision", task.getDecision());
        view.put("feedback", task.getFeedback());
        view.put("payload", parsePayload(task.getPayloadJson()));
        view.put("createdAt", task.getCreateTime());
        view.put("updatedAt", task.getUpdateTime());
        return view;
    }

    private Map<String, Object> parsePayload(String json) {
        if (!StringUtils.hasText(json)) return Map.of();
        try {
            JsonNode node = objectMapper.readTree(json);
            return objectMapper.convertValue(node, new com.fasterxml.jackson.core.type.TypeReference<>() {});
        } catch (Exception e) {
            log.warn("复核任务 payload 解析失败: {}", e.getMessage());
            return Map.of("raw", json);
        }
    }
}
