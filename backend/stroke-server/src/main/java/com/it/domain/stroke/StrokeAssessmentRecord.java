package com.it.domain.stroke;

import java.time.LocalDateTime;

public record StrokeAssessmentRecord(
        Long id,
        Long doctorId,
        StrokeAssessmentData data,
        int version,
        AssessmentRecordStatus status,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
}
