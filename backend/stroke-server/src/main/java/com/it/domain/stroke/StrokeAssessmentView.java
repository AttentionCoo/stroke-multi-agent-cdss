package com.it.domain.stroke;

import java.time.LocalDateTime;

public record StrokeAssessmentView(
        Long id,
        Long doctorId,
        StrokeAssessmentData data,
        int version,
        AssessmentRecordStatus status,
        AssessmentEvaluation evaluation,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
}
