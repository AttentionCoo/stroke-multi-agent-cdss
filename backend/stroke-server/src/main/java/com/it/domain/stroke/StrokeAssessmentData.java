package com.it.domain.stroke;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record StrokeAssessmentData(
        Long patientId,
        LocalDateTime lastKnownWellAt,
        LocalDateTime arrivalAt,
        Integer systolicBloodPressure,
        Integer diastolicBloodPressure,
        BigDecimal bloodGlucoseMmolL,
        Integer nihssScore,
        Integer plateletCount,
        BigDecimal inr,
        ClinicalState anticoagulantUse,
        LocalDateTime anticoagulantLastDoseAt,
        ClinicalState ctHemorrhage,
        ClinicalState ctaLargeVesselOcclusion,
        String notes
) {
}
