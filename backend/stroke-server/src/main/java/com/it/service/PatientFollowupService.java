package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.PatientFollowupMapper;
import com.it.mapper.PatientMapper;
import com.it.po.uo.PatientFollowupParam;
import com.it.pojo.Patient;
import com.it.pojo.PatientFollowup;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** 患者随访任务与卒中结局录入。 */
@Service
@RequiredArgsConstructor
@Slf4j
public class PatientFollowupService {

    private final PatientFollowupMapper followupMapper;
    private final PatientMapper patientMapper;

    @Transactional
    public PatientFollowup create(Long doctorId, Long patientId, PatientFollowupParam param) {
        requireOwnedPatient(doctorId, patientId);
        if (param == null || param.getPlannedDate() == null) {
            throw new IllegalArgumentException("plannedDate 不能为空");
        }
        PatientFollowup followup = new PatientFollowup();
        followup.setDoctorId(doctorId);
        followup.setPatientId(patientId);
        followup.setPlannedDate(param.getPlannedDate());
        followup.setFollowupType(normalizeType(param.getFollowupType()));
        followup.setStatus("PENDING");
        followup.setNotes(truncate(param.getNotes(), 4000));
        followup.setCreateTime(LocalDateTime.now());
        followup.setUpdateTime(LocalDateTime.now());
        followupMapper.insert(followup);
        log.info("创建患者随访: doctorId={}, patientId={}, plannedDate={}", doctorId, patientId, param.getPlannedDate());
        return followup;
    }

    public List<PatientFollowup> list(Long doctorId, Long patientId) {
        requireOwnedPatient(doctorId, patientId);
        return followupMapper.selectList(new LambdaQueryWrapper<PatientFollowup>()
                .eq(PatientFollowup::getDoctorId, doctorId)
                .eq(PatientFollowup::getPatientId, patientId)
                .orderByDesc(PatientFollowup::getPlannedDate)
                .orderByDesc(PatientFollowup::getId));
    }

    @Transactional
    public PatientFollowup complete(Long doctorId, Long patientId, Long followupId, PatientFollowupParam param) {
        requireOwnedPatient(doctorId, patientId);
        PatientFollowup followup = followupMapper.selectById(followupId);
        if (followup == null || !doctorId.equals(followup.getDoctorId())
                || !patientId.equals(followup.getPatientId())) {
            throw new IllegalArgumentException("随访任务不存在或无权限");
        }
        if (param == null || param.getMrsScore() == null || param.getMrsScore() < 0 || param.getMrsScore() > 6) {
            throw new IllegalArgumentException("mRS 评分必须为 0-6");
        }
        followup.setStatus("COMPLETED");
        followup.setMrsScore(param.getMrsScore());
        followup.setRecurrence(normalizeChoice(param.getRecurrence(), "UNKNOWN", "YES", "NO", "UNKNOWN"));
        followup.setAdherence(normalizeChoice(param.getAdherence(), "UNKNOWN", "GOOD", "PARTIAL", "POOR", "UNKNOWN"));
        if (StringUtils.hasText(param.getNotes())) {
            followup.setNotes(truncate(param.getNotes(), 4000));
        }
        followup.setCompletedAt(LocalDateTime.now());
        followup.setUpdateTime(LocalDateTime.now());
        followupMapper.updateById(followup);
        log.info("完成患者随访: doctorId={}, patientId={}, followupId={}", doctorId, patientId, followupId);
        return followup;
    }

    public long pendingCount(Long doctorId, Long patientId) {
        requireOwnedPatient(doctorId, patientId);
        Long count = followupMapper.selectCount(new LambdaQueryWrapper<PatientFollowup>()
                .eq(PatientFollowup::getDoctorId, doctorId)
                .eq(PatientFollowup::getPatientId, patientId)
                .eq(PatientFollowup::getStatus, "PENDING")
                .le(PatientFollowup::getPlannedDate, LocalDate.now()));
        return count == null ? 0 : count;
    }

    private void requireOwnedPatient(Long doctorId, Long patientId) {
        Patient patient = patientMapper.selectById(patientId);
        if (patient == null || !doctorId.equals(patient.getDoctorId())) {
            throw new IllegalArgumentException("患者不存在或无权限");
        }
    }

    private String normalizeType(String value) {
        return normalizeChoice(value, "OUTPATIENT", "OUTPATIENT", "PHONE", "WECHAT", "OTHER");
    }

    private String normalizeChoice(String value, String fallback, String... allowed) {
        if (!StringUtils.hasText(value)) return fallback;
        String normalized = value.trim().toUpperCase();
        for (String item : allowed) {
            if (item.equals(normalized)) return normalized;
        }
        return fallback;
    }

    private String truncate(String value, int maxLength) {
        if (!StringUtils.hasText(value)) return null;
        String text = value.trim();
        return text.length() <= maxLength ? text : text.substring(0, maxLength);
    }
}
