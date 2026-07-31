package com.it.domain.stroke;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

class InMemoryStrokeAssessmentStore implements StrokeAssessmentStore {

    private final AtomicLong assessmentIds = new AtomicLong();
    private final AtomicLong reviewIds = new AtomicLong();
    private final Map<Long, StrokeAssessmentRecord> assessments = new LinkedHashMap<>();
    private final List<AssessmentReviewRecord> reviewRecords = new ArrayList<>();

    @Override
    public boolean patientBelongsToDoctor(Long patientId, Long doctorId) {
        return patientId == 1L;
    }

    @Override
    public StrokeAssessmentRecord create(Long doctorId, StrokeAssessmentData data, LocalDateTime now) {
        long id = assessmentIds.incrementAndGet();
        StrokeAssessmentRecord record = new StrokeAssessmentRecord(
                id, doctorId, data, 1, AssessmentRecordStatus.DRAFT, now, now
        );
        assessments.put(id, record);
        return record;
    }

    @Override
    public Optional<StrokeAssessmentRecord> find(Long doctorId, Long assessmentId) {
        return Optional.ofNullable(assessments.get(assessmentId))
                .filter(record -> record.doctorId().equals(doctorId));
    }

    @Override
    public List<StrokeAssessmentRecord> list(Long doctorId, int limit) {
        return assessments.values().stream()
                .filter(record -> record.doctorId().equals(doctorId))
                .limit(limit)
                .toList();
    }

    @Override
    public StrokeAssessmentRecord update(
            StrokeAssessmentRecord existing,
            StrokeAssessmentData data,
            AssessmentRecordStatus status,
            LocalDateTime now
    ) {
        StrokeAssessmentRecord updated = new StrokeAssessmentRecord(
                existing.id(), existing.doctorId(), data, existing.version() + 1,
                status, existing.createdAt(), now
        );
        assessments.put(updated.id(), updated);
        return updated;
    }

    @Override
    public StrokeAssessmentRecord review(
            StrokeAssessmentRecord assessment,
            Long doctorId,
            AssessmentReviewData review,
            AssessmentRecordStatus status,
            LocalDateTime now
    ) {
        AssessmentReviewRecord record = new AssessmentReviewRecord(
                reviewIds.incrementAndGet(), assessment.id(), doctorId, review.action(),
                review.reason(), assessment.version(), assessment.data(), now
        );
        reviewRecords.add(record);
        return update(assessment, assessment.data(), status, now);
    }

    @Override
    public List<AssessmentReviewRecord> reviews(Long doctorId, Long assessmentId) {
        return reviewRecords.stream()
                .filter(review -> review.doctorId().equals(doctorId) && review.assessmentId().equals(assessmentId))
                .toList();
    }
}
