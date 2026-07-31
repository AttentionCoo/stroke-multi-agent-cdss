package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.it.mapper.AiOpinionMapper;
import com.it.mapper.HealthDataMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.TalkMapper;
import com.it.pojo.AiOpinion;
import com.it.pojo.HealthData;
import com.it.pojo.Patient;
import com.it.pojo.Talk;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class PatientMemoryService {

    private static final int SHORT_MEMORY_LIMIT = 4_000;
    private static final int EPISODIC_MEMORY_LIMIT = 3_000;
    private static final int SEMANTIC_MEMORY_LIMIT = 2_000;

    private final PatientMapper patientMapper;
    private final HealthDataMapper healthDataMapper;
    private final AiOpinionMapper aiOpinionMapper;
    private final TalkMapper talkMapper;

    /**
     * 为一次问诊构建三级记忆。患者不存在或不属于当前医生时不返回任何数据。
     */
    public Map<String, String> build(
            Long doctorId,
            Long patientId,
            Long talkId,
            String recentConversation
    ) {
        if (doctorId == null || patientId == null) {
            return Map.of();
        }

        Patient patient = patientMapper.selectById(patientId);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            log.warn("拒绝加载患者记忆: doctorId={}, patientId={}", doctorId, patientId);
            throw new PatientContextException("无法访问所选患者，请刷新患者列表后重试");
        }

        Map<String, String> memory = new LinkedHashMap<>();
        memory.put("short_term", resolveShortTermMemory(doctorId, talkId, patientId, recentConversation));
        memory.put("episodic", truncate(buildEpisodicMemory(patientId), EPISODIC_MEMORY_LIMIT));
        memory.put("semantic", truncate(buildSemanticMemory(patient), SEMANTIC_MEMORY_LIMIT));
        return memory;
    }

    private String resolveShortTermMemory(
            Long doctorId,
            Long talkId,
            Long patientId,
            String recentConversation
    ) {
        if (talkId == null) {
            return "";
        }

        try {
            Talk talk = talkMapper.selectById(talkId);
            if (talk == null || !doctorId.equals(talk.getUserId())) {
                log.warn("拒绝为无权访问的对话加载短期记忆: doctorId={}, talkId={}", doctorId, talkId);
                throw new PatientContextException("无法确认当前对话的患者关联，请新建对话后重试");
            }

            Long scopedPatientId = talk.getPatientId();
            if (scopedPatientId == null) {
                // 已有内容的旧对话无法确认其患者归属，必须新建对话后再绑定。
                if (StringUtils.hasText(recentConversation)) {
                    throw new PatientContextException("当前对话已有未归属内容，请新建对话后关联患者");
                }
                int updated = talkMapper.update(
                        null,
                        new UpdateWrapper<Talk>()
                                .eq("id", talkId)
                                .eq("user_id", doctorId)
                                .isNull("patient_id")
                                .set("patient_id", patientId)
                );
                if (updated != 1) {
                    Talk latest = talkMapper.selectById(talkId);
                    if (latest == null || !patientId.equals(latest.getPatientId())) {
                        throw new PatientContextException("当前对话已关联其他患者，请新建对话后重试");
                    }
                }
                scopedPatientId = patientId;
            }

            if (!patientId.equals(scopedPatientId)) {
                log.warn("拒绝在同一对话切换患者: talkId={}, scopedPatientId={}, requestedPatientId={}",
                        talkId, scopedPatientId, patientId);
                throw new PatientContextException("当前对话已关联其他患者，请新建对话后重试");
            }

            return tail(recentConversation, SHORT_MEMORY_LIMIT);
        } catch (PatientContextException e) {
            throw e;
        } catch (Exception e) {
            log.warn("患者短期记忆作用域校验失败，已拒绝继续问诊: talkId={}, err={}",
                    talkId, e.getMessage());
            throw new PatientContextException("暂时无法确认患者对话关联，请稍后重试");
        }
    }

    public static class PatientContextException extends RuntimeException {
        public PatientContextException(String message) {
            super(message);
        }
    }

    private String buildEpisodicMemory(Long patientId) {
        List<HealthData> healthRecords = healthDataMapper.selectList(
                new LambdaQueryWrapper<HealthData>()
                        .eq(HealthData::getPatientId, patientId)
                        .orderByDesc(HealthData::getCreateTime)
                        .last("LIMIT 5")
        );
        List<AiOpinion> opinions = aiOpinionMapper.selectList(
                new LambdaQueryWrapper<AiOpinion>()
                        .eq(AiOpinion::getPatientId, patientId)
                        .orderByDesc(AiOpinion::getUpdateTime)
                        .last("LIMIT 5")
        );

        StringBuilder content = new StringBuilder();
        for (HealthData record : healthRecords == null ? List.<HealthData>of() : healthRecords) {
            appendLine(content, "历史健康数据", record.getDataContent());
        }
        for (AiOpinion opinion : opinions == null ? List.<AiOpinion>of() : opinions) {
            String detail = StringUtils.hasText(opinion.getAnalysisDetails())
                    ? opinion.getAnalysisDetails()
                    : opinion.getSuggestions();
            String prefix = StringUtils.hasText(opinion.getRiskLevel())
                    ? "历史AI评估（" + opinion.getRiskLevel() + "）"
                    : "历史AI评估";
            appendLine(content, prefix, detail);
        }
        return content.toString().trim();
    }

    private String buildSemanticMemory(Patient patient) {
        StringBuilder content = new StringBuilder();
        appendLine(content, "稳定病史", patient.getHistory());
        appendLine(content, "医生备注", patient.getNotes());
        return content.toString().trim();
    }

    private void appendLine(StringBuilder target, String label, String value) {
        if (!StringUtils.hasText(value)) {
            return;
        }
        if (!target.isEmpty()) {
            target.append('\n');
        }
        target.append(label).append("：").append(value.trim());
    }

    private String truncate(String value, int limit) {
        String text = value == null ? "" : value.trim();
        return text.length() <= limit ? text : text.substring(0, limit) + "...";
    }

    private String tail(String value, int limit) {
        String text = value == null ? "" : value.trim();
        return text.length() <= limit ? text : "..." + text.substring(text.length() - limit);
    }
}
