package com.it.domain.stroke;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StrokeAssessmentModuleTest {

    private StrokeAssessmentModule module;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-07-31T02:00:00Z"),
                ZoneId.of("Asia/Shanghai")
        );
        module = new StrokeAssessmentModule(new InMemoryStrokeAssessmentStore(), clock);
    }

    @Test
    void doctorCanCreateAndReadOwnAssessment() {
        StrokeAssessmentView created = module.create(7L, completeData());

        StrokeAssessmentView loaded = module.get(7L, created.id());

        assertEquals(created.id(), loaded.id());
        assertEquals(1, loaded.version());
        assertEquals(AssessmentRecordStatus.DRAFT, loaded.status());
        assertEquals(100, loaded.evaluation().completenessPercent());
    }

    @Test
    void doctorCannotReadAnotherDoctorsAssessment() {
        StrokeAssessmentView created = module.create(7L, completeData());

        assertThrows(AssessmentNotFoundException.class, () -> module.get(8L, created.id()));
    }

    @Test
    void updateReturnsDecisionChangesAndIncrementsVersion() {
        StrokeAssessmentView created = module.create(7L, completeData());
        StrokeAssessmentData changed = new StrokeAssessmentData(
                1L,
                completeData().lastKnownWellAt(),
                completeData().arrivalAt(),
                completeData().systolicBloodPressure(),
                completeData().diastolicBloodPressure(),
                completeData().bloodGlucoseMmolL(),
                completeData().nihssScore(),
                85,
                new BigDecimal("2.0"),
                completeData().anticoagulantUse(),
                completeData().anticoagulantLastDoseAt(),
                ClinicalState.YES,
                completeData().ctaLargeVesselOcclusion(),
                "新增影像与化验结果"
        );

        StrokeAssessmentView updated = module.update(7L, created.id(), changed);

        assertEquals(2, updated.version());
        assertEquals(AssessmentDecisionStatus.BLOCKED, updated.evaluation().decisionStatus());
        assertTrue(updated.evaluation().changes().contains("新增风险：影像提示颅内出血"));
        assertTrue(module.get(7L, created.id()).evaluation().changes()
                .contains("新增风险：影像提示颅内出血"));
    }

    @Test
    void blockedAssessmentCannotBeAcceptedButRejectionIsAudited() {
        StrokeAssessmentData blocked = new StrokeAssessmentData(
                1L,
                completeData().lastKnownWellAt(),
                completeData().arrivalAt(),
                190,
                115,
                completeData().bloodGlucoseMmolL(),
                completeData().nihssScore(),
                85,
                new BigDecimal("2.0"),
                ClinicalState.YES,
                completeData().anticoagulantLastDoseAt(),
                ClinicalState.YES,
                ClinicalState.YES,
                ""
        );
        StrokeAssessmentView created = module.create(7L, blocked);

        assertThrows(InvalidAssessmentReviewException.class, () ->
                module.review(7L, created.id(), new AssessmentReviewData(AssessmentReviewAction.ACCEPT, ""))
        );

        StrokeAssessmentView reviewed = module.review(
                7L,
                created.id(),
                new AssessmentReviewData(AssessmentReviewAction.REJECT, "影像与实验室结果触发高风险复核")
        );

        assertEquals(AssessmentRecordStatus.REJECTED, reviewed.status());
        assertEquals(2, reviewed.version());
        var reviews = module.reviews(7L, created.id());
        assertEquals(1, reviews.size());
        assertEquals(1, reviews.getFirst().assessmentVersion());
        assertEquals(AssessmentRecordStatus.DRAFT, reviews.getFirst().assessmentSnapshot().status());
        assertEquals(AssessmentDecisionStatus.BLOCKED,
                reviews.getFirst().assessmentSnapshot().evaluation().decisionStatus());
        assertEquals(StrokeAssessmentEvaluator.RULE_VERSION,
                reviews.getFirst().assessmentSnapshot().ruleVersion());
    }

    @Test
    void fhirExportUsesDocumentBundleAndCarriesSafetyConclusion() {
        StrokeAssessmentView created = module.create(7L, completeData());

        var bundle = module.exportFhir(7L, created.id());

        assertEquals("Bundle", bundle.get("resourceType"));
        assertEquals("document", bundle.get("type"));
        assertTrue(bundle.toString().contains("READY_FOR_REVIEW"));
    }

    private StrokeAssessmentData completeData() {
        return new StrokeAssessmentData(
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
    }
}
