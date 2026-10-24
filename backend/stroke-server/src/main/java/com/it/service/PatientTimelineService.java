package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.AiOpinionMapper;
import com.it.mapper.HealthDataMapper;
import com.it.mapper.PatientFollowupMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.StrokeAssessmentMapper;
import com.it.pojo.AiOpinion;
import com.it.pojo.HealthData;
import com.it.pojo.Patient;
import com.it.pojo.PatientFollowup;
import com.it.pojo.StrokeAssessmentEntity;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 聚合患者档案、AI 意见、绿道评估、健康数据与随访，形成纵向时间线。 */
@Service
@RequiredArgsConstructor
public class PatientTimelineService {

    private final PatientMapper patientMapper;
    private final StrokeAssessmentMapper assessmentMapper;
    private final AiOpinionMapper aiOpinionMapper;
    private final HealthDataMapper healthDataMapper;
    private final PatientFollowupMapper followupMapper;

    public List<Map<String, Object>> timeline(Long doctorId, Long patientId) {
        Patient patient = patientMapper.selectById(patientId);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            throw new IllegalArgumentException("患者不存在或无权限");
        }

        List<TimelineEvent> events = new ArrayList<>();
        events.add(new TimelineEvent(patient.getCreateTime(), event(
                "patient", "患者建档", "患者 " + safe(patient.getName()) + " 建立电子档案", "ACTIVE", patientId)));
        if (patient.getUpdateTime() != null && patient.getCreateTime() != null
                && patient.getUpdateTime().isAfter(patient.getCreateTime().plusSeconds(1))) {
            events.add(new TimelineEvent(patient.getUpdateTime(), event(
                    "patient_update", "患者档案更新", safe(patient.getHistory()), "UPDATED", patientId)));
        }

        List<StrokeAssessmentEntity> assessments = assessmentMapper.selectList(
                new LambdaQueryWrapper<StrokeAssessmentEntity>()
                        .eq(StrokeAssessmentEntity::getDoctorId, doctorId)
                        .eq(StrokeAssessmentEntity::getPatientId, patientId)
                        .orderByDesc(StrokeAssessmentEntity::getUpdateTime)
                        .last("LIMIT 50"));
        for (StrokeAssessmentEntity item : assessments) {
            String summary = "NIHSS " + (item.getNihssScore() == null ? "未填" : item.getNihssScore())
                    + " · 血压 " + (item.getSystolicBloodPressure() == null ? "未填" : item.getSystolicBloodPressure())
                    + "/" + (item.getDiastolicBloodPressure() == null ? "未填" : item.getDiastolicBloodPressure())
                    + " · 版本 v" + (item.getVersion() == null ? 1 : item.getVersion());
            events.add(new TimelineEvent(item.getUpdateTime(), event(
                    "stroke_assessment", "急诊绿道评估", summary, item.getStatus(), item.getId())));
        }

        List<AiOpinion> opinions = aiOpinionMapper.selectList(new LambdaQueryWrapper<AiOpinion>()
                .eq(AiOpinion::getPatientId, patientId)
                .orderByDesc(AiOpinion::getCreateTime)
                .last("LIMIT 50"));
        for (AiOpinion item : opinions) {
            String summary = safe(item.getRiskLevel()) + " · " + safe(item.getSuggestions());
            events.add(new TimelineEvent(item.getCreateTime(), event(
                    "ai_opinion", "AI 风险分析", summary, safe(item.getRiskLevel()), item.getId())));
        }

        List<HealthData> healthRows = healthDataMapper.selectList(new LambdaQueryWrapper<HealthData>()
                .eq(HealthData::getPatientId, patientId)
                .orderByDesc(HealthData::getCreateTime)
                .last("LIMIT 50"));
        for (HealthData item : healthRows) {
            events.add(new TimelineEvent(item.getCreateTime(), event(
                    "health_data", "健康数据更新", truncate(item.getDataContent(), 300), "RECORDED", item.getId())));
        }

        List<PatientFollowup> followups = followupMapper.selectList(new LambdaQueryWrapper<PatientFollowup>()
                .eq(PatientFollowup::getDoctorId, doctorId)
                .eq(PatientFollowup::getPatientId, patientId)
                .orderByDesc(PatientFollowup::getPlannedDate)
                .last("LIMIT 50"));
        for (PatientFollowup item : followups) {
            LocalDateTime time = item.getCompletedAt() != null ? item.getCompletedAt() : item.getCreateTime();
            String title = "COMPLETED".equals(item.getStatus()) ? "随访完成" : "随访计划";
            String summary = "计划 " + item.getPlannedDate()
                    + (item.getMrsScore() == null ? "" : " · mRS " + item.getMrsScore())
                    + (StringUtils.hasText(item.getNotes()) ? " · " + truncate(item.getNotes(), 160) : "");
            events.add(new TimelineEvent(time, event(
                    "followup", title, summary, item.getStatus(), item.getId())));
        }

        return events.stream()
                .filter(e -> e.time() != null)
                .sorted(Comparator.comparing(TimelineEvent::time).reversed())
                .limit(100)
                .map(item -> {
                    Map<String, Object> payload = item.payload();
                    payload.put("time", item.time());
                    return payload;
                })
                .toList();
    }

    private Map<String, Object> event(String type, String title, String summary, String status, Long sourceId) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("type", type);
        item.put("title", title);
        item.put("summary", summary);
        item.put("status", status);
        item.put("sourceId", sourceId);
        return item;
    }

    private String safe(String value) {
        return StringUtils.hasText(value) ? value.trim() : "未记录";
    }

    private String truncate(String value, int limit) {
        if (!StringUtils.hasText(value)) return "未记录";
        String text = value.trim();
        return text.length() <= limit ? text : text.substring(0, limit) + "…";
    }

    private record TimelineEvent(LocalDateTime time, Map<String, Object> payload) {
    }
}
