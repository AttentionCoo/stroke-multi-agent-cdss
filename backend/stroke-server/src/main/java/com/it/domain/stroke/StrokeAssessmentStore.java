package com.it.domain.stroke;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface StrokeAssessmentStore {

    boolean patientBelongsToDoctor(Long patientId, Long doctorId);

    StrokeAssessmentRecord create(Long doctorId, StrokeAssessmentData data, LocalDateTime now);

    Optional<StrokeAssessmentRecord> find(Long doctorId, Long assessmentId);

    List<StrokeAssessmentRecord> list(Long doctorId, int limit);

    StrokeAssessmentRecord update(
            StrokeAssessmentRecord existing,
            StrokeAssessmentData data,
            AssessmentRecordStatus status,
            List<String> changes,
            LocalDateTime now
    );

    StrokeAssessmentRecord review(
            StrokeAssessmentRecord assessment,
            Long doctorId,
            AssessmentReviewData review,
            AssessmentAuditSnapshot snapshot,
            AssessmentRecordStatus status,
            List<String> changes,
            LocalDateTime now
    );

    List<AssessmentReviewRecord> reviews(Long doctorId, Long assessmentId);
}
