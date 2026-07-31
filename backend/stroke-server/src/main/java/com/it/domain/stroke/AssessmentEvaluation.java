package com.it.domain.stroke;

import java.time.LocalDateTime;
import java.util.List;

public record AssessmentEvaluation(
        int completenessPercent,
        List<String> missingFields,
        AssessmentDecisionStatus decisionStatus,
        AssessmentTriageLevel triageLevel,
        AssessmentTimeline timeline,
        List<SafetyFlag> riskFlags,
        List<String> changes,
        LocalDateTime evaluatedAt
) {
}
