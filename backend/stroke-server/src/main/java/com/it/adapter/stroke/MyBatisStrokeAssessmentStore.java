package com.it.adapter.stroke;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.domain.stroke.*;
import com.it.mapper.AssessmentReviewMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.StrokeAssessmentMapper;
import com.it.pojo.AssessmentReviewEntity;
import com.it.pojo.Patient;
import com.it.pojo.StrokeAssessmentEntity;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
@RequiredArgsConstructor
public class MyBatisStrokeAssessmentStore implements StrokeAssessmentStore {

    private final StrokeAssessmentMapper assessmentMapper;
    private final AssessmentReviewMapper reviewMapper;
    private final PatientMapper patientMapper;
    private final ObjectMapper objectMapper;

    @Override
    public boolean patientBelongsToDoctor(Long patientId, Long doctorId) {
        return patientMapper.selectCount(new LambdaQueryWrapper<Patient>()
                .eq(Patient::getId, patientId)
                .eq(Patient::getDoctorId, doctorId)) > 0;
    }

    @Override
    public StrokeAssessmentRecord create(Long doctorId, StrokeAssessmentData data, LocalDateTime now) {
        StrokeAssessmentEntity entity = toEntity(
                null, doctorId, data, 1, AssessmentRecordStatus.DRAFT,
                List.of("创建评估记录"), now, now
        );
        assessmentMapper.insert(entity);
        return toRecord(entity);
    }

    @Override
    public Optional<StrokeAssessmentRecord> find(Long doctorId, Long assessmentId) {
        StrokeAssessmentEntity entity = assessmentMapper.selectOne(
                new LambdaQueryWrapper<StrokeAssessmentEntity>()
                        .eq(StrokeAssessmentEntity::getId, assessmentId)
                        .eq(StrokeAssessmentEntity::getDoctorId, doctorId)
        );
        return Optional.ofNullable(entity).map(this::toRecord);
    }

    @Override
    public List<StrokeAssessmentRecord> list(Long doctorId, int limit) {
        return assessmentMapper.selectList(new LambdaQueryWrapper<StrokeAssessmentEntity>()
                        .eq(StrokeAssessmentEntity::getDoctorId, doctorId)
                        .orderByDesc(StrokeAssessmentEntity::getUpdateTime)
                        .last("LIMIT " + limit))
                .stream()
                .map(this::toRecord)
                .toList();
    }

    @Override
    public StrokeAssessmentRecord update(
            StrokeAssessmentRecord existing,
            StrokeAssessmentData data,
            AssessmentRecordStatus status,
            List<String> changes,
            LocalDateTime now
    ) {
        int nextVersion = existing.version() + 1;
        StrokeAssessmentEntity next = toEntity(
                existing.id(), existing.doctorId(), data, nextVersion, status,
                changes, existing.createdAt(), now
        );
        int affected = assessmentMapper.update(next, new LambdaUpdateWrapper<StrokeAssessmentEntity>()
                .eq(StrokeAssessmentEntity::getId, existing.id())
                .eq(StrokeAssessmentEntity::getDoctorId, existing.doctorId())
                .eq(StrokeAssessmentEntity::getVersion, existing.version()));
        if (affected != 1) throw new AssessmentConflictException();
        return toRecord(next);
    }

    @Override
    @Transactional
    public StrokeAssessmentRecord review(
            StrokeAssessmentRecord assessment,
            Long doctorId,
            AssessmentReviewData review,
            AssessmentAuditSnapshot snapshot,
            AssessmentRecordStatus status,
            List<String> changes,
            LocalDateTime now
    ) {
        insertReview(assessment, doctorId, review, snapshot, now);
        return update(assessment, assessment.data(), status, changes, now);
    }

    private AssessmentReviewRecord insertReview(
            StrokeAssessmentRecord assessment,
            Long doctorId,
            AssessmentReviewData review,
            AssessmentAuditSnapshot snapshot,
            LocalDateTime now
    ) {
        AssessmentReviewEntity entity = new AssessmentReviewEntity();
        entity.setAssessmentId(assessment.id());
        entity.setDoctorId(doctorId);
        entity.setAction(review.action().name());
        entity.setReason(review.reason());
        entity.setAssessmentVersion(assessment.version());
        entity.setAssessmentSnapshot(writeSnapshot(snapshot));
        entity.setCreateTime(now);
        reviewMapper.insert(entity);
        return toReviewRecord(entity);
    }

    @Override
    public List<AssessmentReviewRecord> reviews(Long doctorId, Long assessmentId) {
        return reviewMapper.selectList(new LambdaQueryWrapper<AssessmentReviewEntity>()
                        .eq(AssessmentReviewEntity::getDoctorId, doctorId)
                        .eq(AssessmentReviewEntity::getAssessmentId, assessmentId)
                        .orderByDesc(AssessmentReviewEntity::getCreateTime))
                .stream()
                .map(this::toReviewRecord)
                .toList();
    }

    private StrokeAssessmentEntity toEntity(
            Long id,
            Long doctorId,
            StrokeAssessmentData data,
            int version,
            AssessmentRecordStatus status,
            List<String> changes,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
        StrokeAssessmentEntity entity = new StrokeAssessmentEntity();
        entity.setId(id);
        entity.setDoctorId(doctorId);
        entity.setPatientId(data.patientId());
        entity.setLastKnownWellAt(data.lastKnownWellAt());
        entity.setArrivalAt(data.arrivalAt());
        entity.setSystolicBloodPressure(data.systolicBloodPressure());
        entity.setDiastolicBloodPressure(data.diastolicBloodPressure());
        entity.setBloodGlucoseMmolL(data.bloodGlucoseMmolL());
        entity.setNihssScore(data.nihssScore());
        entity.setPlateletCount(data.plateletCount());
        entity.setInr(data.inr());
        entity.setAnticoagulantUse(stateName(data.anticoagulantUse()));
        entity.setAnticoagulantLastDoseAt(data.anticoagulantLastDoseAt());
        entity.setCtHemorrhage(stateName(data.ctHemorrhage()));
        entity.setCtaLargeVesselOcclusion(stateName(data.ctaLargeVesselOcclusion()));
        entity.setNotes(data.notes());
        entity.setVersion(version);
        entity.setStatus(status.name());
        entity.setChangeSummary(writeChanges(changes));
        entity.setCreateTime(createdAt);
        entity.setUpdateTime(updatedAt);
        return entity;
    }

    private StrokeAssessmentRecord toRecord(StrokeAssessmentEntity entity) {
        StrokeAssessmentData data = new StrokeAssessmentData(
                entity.getPatientId(), entity.getLastKnownWellAt(), entity.getArrivalAt(),
                entity.getSystolicBloodPressure(), entity.getDiastolicBloodPressure(),
                entity.getBloodGlucoseMmolL(), entity.getNihssScore(), entity.getPlateletCount(),
                entity.getInr(), parseState(entity.getAnticoagulantUse()), entity.getAnticoagulantLastDoseAt(),
                parseState(entity.getCtHemorrhage()), parseState(entity.getCtaLargeVesselOcclusion()), entity.getNotes()
        );
        return new StrokeAssessmentRecord(
                entity.getId(), entity.getDoctorId(), data, entity.getVersion(),
                AssessmentRecordStatus.valueOf(entity.getStatus()),
                readChanges(entity.getChangeSummary()), entity.getCreateTime(), entity.getUpdateTime()
        );
    }

    private AssessmentReviewRecord toReviewRecord(AssessmentReviewEntity entity) {
        return new AssessmentReviewRecord(
                entity.getId(), entity.getAssessmentId(), entity.getDoctorId(),
                AssessmentReviewAction.valueOf(entity.getAction()), entity.getReason(),
                entity.getAssessmentVersion(), readSnapshot(entity.getAssessmentSnapshot()), entity.getCreateTime()
        );
    }

    private String writeSnapshot(AssessmentAuditSnapshot snapshot) {
        try {
            return objectMapper.writeValueAsString(snapshot);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("无法保存评估审核快照", e);
        }
    }

    private AssessmentAuditSnapshot readSnapshot(String value) {
        try {
            return objectMapper.readValue(value, AssessmentAuditSnapshot.class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("无法读取评估审核快照", e);
        }
    }

    private String writeChanges(List<String> changes) {
        try {
            return objectMapper.writeValueAsString(changes == null ? List.of() : changes);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("无法保存评估版本差异", e);
        }
    }

    private List<String> readChanges(String value) {
        if (value == null || value.isBlank()) return List.of();
        try {
            return objectMapper.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("无法读取评估版本差异", e);
        }
    }

    private String stateName(ClinicalState state) {
        return state == null ? ClinicalState.UNKNOWN.name() : state.name();
    }

    private ClinicalState parseState(String state) {
        return state == null ? ClinicalState.UNKNOWN : ClinicalState.valueOf(state);
    }
}
