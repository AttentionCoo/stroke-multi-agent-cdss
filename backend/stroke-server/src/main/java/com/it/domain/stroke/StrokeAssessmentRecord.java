package com.it.domain.stroke;

import java.time.LocalDateTime;
import java.util.List;

public record StrokeAssessmentRecord(
        Long id,
        Long doctorId,
        StrokeAssessmentData data,
        int version,
        AssessmentRecordStatus status,
        List<String> changes,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
}
