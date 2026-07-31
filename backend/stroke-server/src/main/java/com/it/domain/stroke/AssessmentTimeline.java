package com.it.domain.stroke;

public record AssessmentTimeline(
        Long onsetMinutes,
        Long doorMinutes,
        TimeWindowStatus thrombolysisWindow,
        TimeWindowStatus thrombectomyWindow,
        boolean dntOverTarget
) {
}
