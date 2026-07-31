package com.it.domain.stroke;

import java.time.LocalDateTime;

public record AssessmentReviewRecord(
        Long id,
        Long assessmentId,
        Long doctorId,
        AssessmentReviewAction action,
        String reason,
        int assessmentVersion,
        AssessmentAuditSnapshot assessmentSnapshot,
        LocalDateTime createdAt
) {
}
