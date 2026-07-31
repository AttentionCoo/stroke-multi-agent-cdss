package com.it.domain.stroke;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class StrokeAssessmentModule {

    private final StrokeAssessmentStore store;
    private final StrokeAssessmentEvaluator evaluator;
    private final Clock clock;

    public StrokeAssessmentModule(StrokeAssessmentStore store, Clock clock) {
        this.store = store;
        this.evaluator = new StrokeAssessmentEvaluator(clock);
        this.clock = clock;
    }

    public AssessmentEvaluation evaluate(StrokeAssessmentData data) {
        validatePatientAccess(null, data.patientId());
        return evaluator.evaluate(data);
    }

    public StrokeAssessmentView create(Long doctorId, StrokeAssessmentData data) {
        validatePatientAccess(doctorId, data.patientId());
        StrokeAssessmentRecord record = store.create(doctorId, data, now());
        return toView(record, evaluator.evaluate(data));
    }

    public StrokeAssessmentView get(Long doctorId, Long assessmentId) {
        StrokeAssessmentRecord record = find(doctorId, assessmentId);
        return toView(record, evaluator.evaluate(record.data()));
    }

    public List<StrokeAssessmentView> list(Long doctorId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return store.list(doctorId, safeLimit).stream()
                .map(record -> toView(record, evaluator.evaluate(record.data())))
                .toList();
    }

    public StrokeAssessmentView update(Long doctorId, Long assessmentId, StrokeAssessmentData data) {
        StrokeAssessmentRecord existing = find(doctorId, assessmentId);
        validatePatientAccess(doctorId, data.patientId());
        AssessmentEvaluation before = evaluator.evaluate(existing.data());
        AssessmentEvaluation after = evaluator.evaluate(data);
        List<String> changes = evaluator.compare(before, after);
        AssessmentEvaluation withChanges = withChanges(after, changes);
        StrokeAssessmentRecord updated = store.update(existing, data, AssessmentRecordStatus.DRAFT, now());
        return toView(updated, withChanges);
    }

    public StrokeAssessmentView review(Long doctorId, Long assessmentId, AssessmentReviewData review) {
        StrokeAssessmentRecord existing = find(doctorId, assessmentId);
        AssessmentEvaluation evaluation = evaluator.evaluate(existing.data());
        validateReview(review, evaluation);
        AssessmentRecordStatus status = switch (review.action()) {
            case ACCEPT -> AssessmentRecordStatus.ACCEPTED;
            case REQUEST_EDIT -> AssessmentRecordStatus.EDIT_REQUIRED;
            case REJECT -> AssessmentRecordStatus.REJECTED;
        };
        StrokeAssessmentRecord updated = store.review(existing, doctorId, review, status, now());
        return toView(updated, evaluation);
    }

    public List<AssessmentReviewRecord> reviews(Long doctorId, Long assessmentId) {
        find(doctorId, assessmentId);
        return store.reviews(doctorId, assessmentId);
    }

    public Map<String, Object> exportFhir(Long doctorId, Long assessmentId) {
        StrokeAssessmentView view = get(doctorId, assessmentId);
        Map<String, Object> bundle = new LinkedHashMap<>();
        bundle.put("resourceType", "Bundle");
        bundle.put("type", "document");
        bundle.put("timestamp", view.updatedAt().toString());
        bundle.put("identifier", Map.of("value", "stroke-assessment-" + view.id() + "-v" + view.version()));

        List<Map<String, Object>> entries = new ArrayList<>();
        entries.add(fhirEntry("Composition", compositionResource(view)));
        entries.add(fhirEntry("Patient", patientResource(view)));
        entries.add(fhirEntry("Observation", observationResource(view)));
        bundle.put("entry", entries);
        bundle.put("meta", Map.of(
                "tag", List.of(Map.of(
                        "system", "https://medllm.local/fhir/export-status",
                        "code", "prototype",
                        "display", "原型导出，接入院内系统前需进行 FHIR 一致性验证"
                ))
        ));
        return bundle;
    }

    private StrokeAssessmentRecord find(Long doctorId, Long assessmentId) {
        return store.find(doctorId, assessmentId).orElseThrow(AssessmentNotFoundException::new);
    }

    private void validatePatientAccess(Long doctorId, Long patientId) {
        if (doctorId != null && patientId != null && !store.patientBelongsToDoctor(patientId, doctorId)) {
            throw new AssessmentNotFoundException();
        }
    }

    private void validateReview(AssessmentReviewData review, AssessmentEvaluation evaluation) {
        if (review == null || review.action() == null) {
            throw new InvalidAssessmentReviewException("审核动作不能为空");
        }
        String reason = review.reason() == null ? "" : review.reason().trim();
        if (review.action() != AssessmentReviewAction.ACCEPT && reason.isEmpty()) {
            throw new InvalidAssessmentReviewException("要求修改或驳回时必须填写原因");
        }
        if (review.action() == AssessmentReviewAction.ACCEPT
                && evaluation.decisionStatus() != AssessmentDecisionStatus.READY_FOR_REVIEW) {
            throw new InvalidAssessmentReviewException("存在缺失信息或高风险项，不能直接采纳");
        }
    }

    private AssessmentEvaluation withChanges(AssessmentEvaluation evaluation, List<String> changes) {
        return new AssessmentEvaluation(
                evaluation.completenessPercent(),
                evaluation.missingFields(),
                evaluation.decisionStatus(),
                evaluation.triageLevel(),
                evaluation.timeline(),
                evaluation.riskFlags(),
                changes,
                evaluation.evaluatedAt()
        );
    }

    private StrokeAssessmentView toView(StrokeAssessmentRecord record, AssessmentEvaluation evaluation) {
        return new StrokeAssessmentView(
                record.id(), record.doctorId(), record.data(), record.version(), record.status(),
                evaluation, record.createdAt(), record.updatedAt()
        );
    }

    private Map<String, Object> fhirEntry(String resourceType, Map<String, Object> resource) {
        return Map.of("fullUrl", "urn:uuid:" + resourceType.toLowerCase() + "-assessment", "resource", resource);
    }

    private Map<String, Object> compositionResource(StrokeAssessmentView view) {
        Map<String, Object> resource = new LinkedHashMap<>();
        resource.put("resourceType", "Composition");
        resource.put("id", "stroke-assessment-" + view.id());
        resource.put("status", view.status() == AssessmentRecordStatus.ACCEPTED ? "final" : "preliminary");
        resource.put("type", Map.of("text", "脑卒中急诊结构化评估"));
        resource.put("date", view.updatedAt().toString());
        resource.put("title", "脑卒中急诊结构化评估");
        resource.put("subject", Map.of("reference", "Patient/patient-assessment"));
        resource.put("section", List.of(Map.of(
                "title", "安全复核结论",
                "text", Map.of(
                        "status", "generated",
                        "div", "<div xmlns=\"http://www.w3.org/1999/xhtml\">"
                                + view.evaluation().decisionStatus() + "</div>"
                )
        )));
        return resource;
    }

    private Map<String, Object> patientResource(StrokeAssessmentView view) {
        Map<String, Object> resource = new LinkedHashMap<>();
        resource.put("resourceType", "Patient");
        resource.put("id", "patient-assessment");
        if (view.data().patientId() != null) {
            resource.put("identifier", List.of(Map.of(
                    "system", "https://medllm.local/patient-id",
                    "value", view.data().patientId().toString()
            )));
        }
        return resource;
    }

    private Map<String, Object> observationResource(StrokeAssessmentView view) {
        Map<String, Object> resource = new LinkedHashMap<>();
        resource.put("resourceType", "Observation");
        resource.put("id", "stroke-safety-assessment");
        resource.put("status", "final");
        resource.put("code", Map.of("text", "脑卒中安全复核状态"));
        resource.put("subject", Map.of("reference", "Patient/patient-assessment"));
        resource.put("valueString", view.evaluation().decisionStatus().name());
        resource.put("note", view.evaluation().riskFlags().stream()
                .map(flag -> Map.of("text", flag.title() + "：" + flag.requiredAction()))
                .toList());
        return resource;
    }

    private LocalDateTime now() {
        return LocalDateTime.now(clock);
    }
}
