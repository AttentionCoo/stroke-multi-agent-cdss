package com.it.domain.stroke;

public record AssessmentAuditSnapshot(
        StrokeAssessmentData data,
        AssessmentEvaluation evaluation,
        AssessmentRecordStatus status,
        int version,
        String ruleVersion
) {
}
