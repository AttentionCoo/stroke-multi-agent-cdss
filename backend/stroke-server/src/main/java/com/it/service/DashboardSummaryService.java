package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.PatientFollowupMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.StrokeAssessmentMapper;
import com.it.pojo.ClinicalReviewTask;
import com.it.pojo.Patient;
import com.it.pojo.PatientFollowup;
import com.it.pojo.StrokeAssessmentEntity;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Web 工作台首页聚合：待办、患者、绿道、随访、反馈和报告签署状态。 */
@Service
@RequiredArgsConstructor
public class DashboardSummaryService {

    private final PatientMapper patientMapper;
    private final StrokeAssessmentMapper assessmentMapper;
    private final PatientFollowupMapper followupMapper;
    private final DoctorFeedbackService feedbackService;
    private final ClinicalReviewService reviewService;
    private final ClinicalReportService reportService;

    public Map<String, Object> summary(Long doctorId) {
        Long patientCount = patientMapper.selectCount(new LambdaQueryWrapper<Patient>()
                .eq(Patient::getDoctorId, doctorId));
        Long assessmentCount = assessmentMapper.selectCount(new LambdaQueryWrapper<StrokeAssessmentEntity>()
                .eq(StrokeAssessmentEntity::getDoctorId, doctorId));

        List<ClinicalReviewTask> pendingTasks = reviewService.listPending(doctorId, 6);
        List<Map<String, Object>> pendingReviews = pendingTasks.stream()
                .map(reviewService::toView)
                .toList();

        LocalDate today = LocalDate.now();
        List<PatientFollowup> dueRows = followupMapper.selectList(new LambdaQueryWrapper<PatientFollowup>()
                .eq(PatientFollowup::getDoctorId, doctorId)
                .eq(PatientFollowup::getStatus, "PENDING")
                .le(PatientFollowup::getPlannedDate, today)
                .orderByAsc(PatientFollowup::getPlannedDate)
                .last("LIMIT 10"));

        Long dueFollowupTotal = followupMapper.selectCount(new LambdaQueryWrapper<PatientFollowup>()
                .eq(PatientFollowup::getDoctorId, doctorId)
                .eq(PatientFollowup::getStatus, "PENDING")
                .le(PatientFollowup::getPlannedDate, today));

        List<Patient> recentPatients = patientMapper.selectList(new LambdaQueryWrapper<Patient>()
                .eq(Patient::getDoctorId, doctorId)
                .orderByDesc(Patient::getUpdateTime)
                .last("LIMIT 6"));

        List<StrokeAssessmentEntity> recentAssessments = assessmentMapper.selectList(
                new LambdaQueryWrapper<StrokeAssessmentEntity>()
                        .eq(StrokeAssessmentEntity::getDoctorId, doctorId)
                        .orderByDesc(StrokeAssessmentEntity::getUpdateTime)
                        .last("LIMIT 6"));

        Map<Long, Patient> patientIndex = loadPatientIndex(dueRows.stream()
                .map(PatientFollowup::getPatientId)
                .collect(Collectors.toList()));
        patientIndex.putAll(loadPatientIndex(recentAssessments.stream()
                .map(StrokeAssessmentEntity::getPatientId)
                .collect(Collectors.toList())));

        List<Map<String, Object>> dueFollowups = dueRows.stream().map(item -> {
            Map<String, Object> row = new LinkedHashMap<>();
            Patient patient = patientIndex.get(item.getPatientId());
            row.put("id", item.getId());
            row.put("patientId", item.getPatientId());
            row.put("patientName", patient == null ? "未知患者" : patient.getName());
            row.put("plannedDate", item.getPlannedDate());
            row.put("followupType", item.getFollowupType());
            row.put("notes", item.getNotes());
            return row;
        }).toList();

        List<Map<String, Object>> assessments = recentAssessments.stream().map(item -> {
            Map<String, Object> row = new LinkedHashMap<>();
            Patient patient = patientIndex.get(item.getPatientId());
            row.put("id", item.getId());
            row.put("patientId", item.getPatientId());
            row.put("patientName", patient == null ? "未关联患者" : patient.getName());
            row.put("status", item.getStatus());
            row.put("version", item.getVersion());
            row.put("nihssScore", item.getNihssScore());
            row.put("systolicBloodPressure", item.getSystolicBloodPressure());
            row.put("updatedAt", item.getUpdateTime());
            return row;
        }).toList();

        List<Map<String, Object>> patientRows = recentPatients.stream().map(item -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", item.getId());
            row.put("name", item.getName());
            row.put("history", truncate(item.getHistory(), 120));
            row.put("notes", truncate(item.getNotes(), 120));
            row.put("updatedAt", item.getUpdateTime());
            return row;
        }).toList();

        Map<String, Object> feedback = feedbackService.summary(doctorId);
        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("patientCount", patientCount == null ? 0 : patientCount);
        stats.put("assessmentCount", assessmentCount == null ? 0 : assessmentCount);
        stats.put("pendingReviewCount", reviewService.countPending(doctorId));
        stats.put("dueFollowupCount", dueFollowupTotal == null ? 0 : dueFollowupTotal);
        stats.put("feedbackTotal", feedback.get("total"));
        stats.put("feedbackPositiveRate", feedback.get("positiveRate"));
        stats.put("signedReportCount", reportService.signedCount(doctorId));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("stats", stats);
        data.put("pendingReviews", pendingReviews);
        data.put("dueFollowups", dueFollowups);
        data.put("recentAssessments", assessments);
        data.put("recentPatients", patientRows);
        data.put("notifications", buildNotifications(pendingTasks, dueRows, patientIndex));
        return data;
    }

    private Map<Long, Patient> loadPatientIndex(List<Long> patientIds) {
        List<Long> ids = patientIds.stream()
                .filter(id -> id != null)
                .distinct()
                .toList();
        if (ids.isEmpty()) return new HashMap<>();
        return patientMapper.selectBatchIds(ids).stream()
                .collect(Collectors.toMap(Patient::getId, Function.identity(), (a, b) -> a));
    }

    private List<Map<String, Object>> buildNotifications(List<ClinicalReviewTask> tasks,
                                                         List<PatientFollowup> followups,
                                                         Map<Long, Patient> patientIndex) {
        List<Map<String, Object>> notifications = new ArrayList<>();
        for (ClinicalReviewTask task : tasks) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("type", "review");
            row.put("severity", "warning");
            row.put("title", "AI 会诊待医生复核");
            row.put("message", "任务 #" + task.getId() + " 等待批准或驳回");
            row.put("talkId", task.getTalkId());
            row.put("taskId", task.getId());
            row.put("time", task.getUpdateTime());
            notifications.add(row);
        }
        for (PatientFollowup item : followups) {
            Map<String, Object> row = new LinkedHashMap<>();
            Patient patient = patientIndex.get(item.getPatientId());
            row.put("type", "followup");
            row.put("severity", item.getPlannedDate() != null && item.getPlannedDate().isBefore(LocalDate.now())
                    ? "danger" : "info");
            row.put("title", "患者随访待完成");
            row.put("message", (patient == null ? "患者" : patient.getName())
                    + " · 计划日期 " + item.getPlannedDate());
            row.put("patientId", item.getPatientId());
            row.put("followupId", item.getId());
            row.put("time", item.getPlannedDate() == null ? null : item.getPlannedDate().atStartOfDay());
            notifications.add(row);
        }
        return notifications.stream()
                .sorted(Comparator.comparing(
                        row -> row.get("time") == null ? LocalDateTime.MIN : (LocalDateTime) row.get("time"),
                        Comparator.reverseOrder()))
                .limit(12)
                .toList();
    }

    private String truncate(String value, int limit) {
        if (!StringUtils.hasText(value)) return "";
        String text = value.trim();
        return text.length() <= limit ? text : text.substring(0, limit) + "…";
    }
}
