package com.it.domain.stroke;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StrokeAssessmentEvaluatorTest {

    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-07-31T02:00:00Z"), ZONE);

    @Test
    void completeAssessmentIsReadyForClinicianReview() {
        StrokeAssessmentData data = new StrokeAssessmentData(
                1L,
                LocalDateTime.of(2026, 7, 31, 8, 30),
                LocalDateTime.of(2026, 7, 31, 9, 10),
                165,
                95,
                new BigDecimal("6.2"),
                8,
                180,
                new BigDecimal("1.1"),
                ClinicalState.NO,
                null,
                ClinicalState.NO,
                ClinicalState.UNKNOWN,
                ""
        );

        AssessmentEvaluation result = new StrokeAssessmentEvaluator(CLOCK).evaluate(data);

        assertEquals(100, result.completenessPercent());
        assertTrue(result.missingFields().isEmpty());
        assertEquals(AssessmentDecisionStatus.READY_FOR_REVIEW, result.decisionStatus());
        assertEquals(AssessmentTriageLevel.URGENT, result.triageLevel());
        assertEquals(90, result.timeline().onsetMinutes());
        assertEquals(50, result.timeline().doorMinutes());
        assertEquals(TimeWindowStatus.OPEN, result.timeline().thrombolysisWindow());
    }

    @Test
    void missingCriticalFactsRequireReviewWithoutGuessingValues() {
        StrokeAssessmentData data = new StrokeAssessmentData(
                1L, null, null, null, null, null, null, null, null,
                ClinicalState.UNKNOWN, null, ClinicalState.UNKNOWN, ClinicalState.UNKNOWN, ""
        );

        AssessmentEvaluation result = new StrokeAssessmentEvaluator(CLOCK).evaluate(data);

        assertEquals(0, result.completenessPercent());
        assertEquals(AssessmentDecisionStatus.REQUIRES_REVIEW, result.decisionStatus());
        assertEquals(AssessmentTriageLevel.INCOMPLETE, result.triageLevel());
        assertTrue(result.missingFields().contains("最后正常时间"));
        assertTrue(result.missingFields().contains("头颅CT出血结论"));
        assertEquals(TimeWindowStatus.UNKNOWN, result.timeline().thrombolysisWindow());
    }

    @Test
    void deterministicRedFlagsBlockAutomaticDecision() {
        StrokeAssessmentData data = new StrokeAssessmentData(
                1L,
                LocalDateTime.of(2026, 7, 31, 8, 30),
                LocalDateTime.of(2026, 7, 31, 9, 10),
                190,
                115,
                new BigDecimal("6.2"),
                12,
                85,
                new BigDecimal("2.0"),
                ClinicalState.YES,
                LocalDateTime.of(2026, 7, 31, 6, 0),
                ClinicalState.YES,
                ClinicalState.YES,
                ""
        );

        AssessmentEvaluation result = new StrokeAssessmentEvaluator(CLOCK).evaluate(data);

        assertEquals(AssessmentDecisionStatus.BLOCKED, result.decisionStatus());
        assertEquals(AssessmentTriageLevel.CRITICAL, result.triageLevel());
        assertFalse(result.riskFlags().isEmpty());
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("CT_HEMORRHAGE")));
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("PLATELET_LOW")));
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("INR_ELEVATED")));
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("BP_REVIEW_REQUIRED")));
    }

    @Test
    void comparisonReportsNewAndResolvedRisks() {
        StrokeAssessmentEvaluator evaluator = new StrokeAssessmentEvaluator(CLOCK);
        AssessmentEvaluation before = evaluator.evaluate(completeData(ClinicalState.NO, 180, new BigDecimal("1.1")));
        AssessmentEvaluation after = evaluator.evaluate(completeData(ClinicalState.YES, 85, new BigDecimal("2.0")));

        List<String> changes = evaluator.compare(before, after);

        assertTrue(changes.contains("新增风险：影像提示颅内出血"));
        assertTrue(changes.contains("新增风险：血小板低于复核阈值"));
        assertTrue(changes.contains("新增风险：INR 高于复核阈值"));
        assertTrue(changes.contains("决策状态：READY_FOR_REVIEW → BLOCKED"));
    }

    @Test
    void impossibleTimelineAndOutOfRangeValuesAreBlocked() {
        StrokeAssessmentData data = new StrokeAssessmentData(
                1L,
                LocalDateTime.of(2026, 7, 31, 10, 30),
                LocalDateTime.of(2026, 7, 31, 8, 0),
                360,
                20,
                new BigDecimal("99"),
                50,
                -1,
                new BigDecimal("-0.2"),
                ClinicalState.NO,
                null,
                ClinicalState.NO,
                ClinicalState.UNKNOWN,
                ""
        );

        AssessmentEvaluation result = new StrokeAssessmentEvaluator(CLOCK).evaluate(data);

        assertEquals(AssessmentDecisionStatus.BLOCKED, result.decisionStatus());
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("INVALID_TIMELINE")));
        assertTrue(result.riskFlags().stream().anyMatch(flag -> flag.code().equals("INVALID_CLINICAL_VALUE")));
    }

    private StrokeAssessmentData completeData(
            ClinicalState ctHemorrhage,
            int plateletCount,
            BigDecimal inr
    ) {
        return new StrokeAssessmentData(
                1L,
                LocalDateTime.of(2026, 7, 31, 8, 30),
                LocalDateTime.of(2026, 7, 31, 9, 10),
                165,
                95,
                new BigDecimal("6.2"),
                8,
                plateletCount,
                inr,
                ClinicalState.NO,
                null,
                ctHemorrhage,
                ClinicalState.UNKNOWN,
                ""
        );
    }
}
