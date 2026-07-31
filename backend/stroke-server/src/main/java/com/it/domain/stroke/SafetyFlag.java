package com.it.domain.stroke;

public record SafetyFlag(
        String code,
        String severity,
        String title,
        String detail,
        String requiredAction,
        String evidenceSource
) {
}
