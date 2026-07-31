package com.it.domain.stroke;

import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class StrokeAssessmentEvaluator {

    private static final int REQUIRED_FIELD_COUNT = 9;
    private final Clock clock;

    public StrokeAssessmentEvaluator(Clock clock) {
        this.clock = clock;
    }

    public AssessmentEvaluation evaluate(StrokeAssessmentData data) {
        List<String> missingFields = findMissingFields(data);
        int completeness = (REQUIRED_FIELD_COUNT - missingFields.size()) * 100 / REQUIRED_FIELD_COUNT;
        LocalDateTime now = LocalDateTime.now(clock);
        Long onsetMinutes = elapsedMinutes(data.lastKnownWellAt(), now);
        Long doorMinutes = elapsedMinutes(data.arrivalAt(), now);

        AssessmentTimeline timeline = new AssessmentTimeline(
                onsetMinutes,
                doorMinutes,
                thrombolysisWindow(onsetMinutes),
                thrombectomyWindow(onsetMinutes),
                doorMinutes != null && doorMinutes > 60
        );

        List<SafetyFlag> riskFlags = evaluateSafetyFlags(data, timeline);
        boolean hasCriticalRisk = riskFlags.stream().anyMatch(flag -> "CRITICAL".equals(flag.severity()));

        AssessmentDecisionStatus decisionStatus = hasCriticalRisk
                ? AssessmentDecisionStatus.BLOCKED
                : missingFields.isEmpty()
                    ? AssessmentDecisionStatus.READY_FOR_REVIEW
                    : AssessmentDecisionStatus.REQUIRES_REVIEW;
        AssessmentTriageLevel triageLevel = hasCriticalRisk
                ? AssessmentTriageLevel.CRITICAL
                : missingFields.isEmpty()
                    ? AssessmentTriageLevel.URGENT
                    : AssessmentTriageLevel.INCOMPLETE;

        return new AssessmentEvaluation(
                completeness,
                List.copyOf(missingFields),
                decisionStatus,
                triageLevel,
                timeline,
                List.copyOf(riskFlags),
                List.of(),
                now
        );
    }

    public List<String> compare(AssessmentEvaluation before, AssessmentEvaluation after) {
        if (before == null || after == null) return List.of();

        Map<String, SafetyFlag> beforeFlags = indexFlags(before.riskFlags());
        Map<String, SafetyFlag> afterFlags = indexFlags(after.riskFlags());
        List<String> changes = new ArrayList<>();

        for (SafetyFlag flag : afterFlags.values()) {
            if (!beforeFlags.containsKey(flag.code())) {
                changes.add("新增风险：" + flag.title());
            }
        }
        for (SafetyFlag flag : beforeFlags.values()) {
            if (!afterFlags.containsKey(flag.code())) {
                changes.add("风险解除：" + flag.title());
            }
        }
        if (before.decisionStatus() != after.decisionStatus()) {
            changes.add("决策状态：" + before.decisionStatus() + " → " + after.decisionStatus());
        }
        if (before.completenessPercent() != after.completenessPercent()) {
            changes.add("信息完整度：" + before.completenessPercent() + "% → " + after.completenessPercent() + "%");
        }
        return List.copyOf(changes);
    }

    private Map<String, SafetyFlag> indexFlags(List<SafetyFlag> flags) {
        Map<String, SafetyFlag> indexed = new LinkedHashMap<>();
        for (SafetyFlag flag : flags) indexed.put(flag.code(), flag);
        return indexed;
    }

    private List<SafetyFlag> evaluateSafetyFlags(StrokeAssessmentData data, AssessmentTimeline timeline) {
        List<SafetyFlag> flags = new ArrayList<>();
        LocalDateTime now = LocalDateTime.now(clock);
        boolean invalidTimeline = (data.lastKnownWellAt() != null && data.lastKnownWellAt().isAfter(now))
                || (data.arrivalAt() != null && data.arrivalAt().isAfter(now))
                || (data.lastKnownWellAt() != null && data.arrivalAt() != null
                    && data.arrivalAt().isBefore(data.lastKnownWellAt()));
        if (invalidTimeline) {
            flags.add(flag(
                    "INVALID_TIMELINE", "CRITICAL", "时间线存在矛盾",
                    "最后正常时间、到院时间或当前时间的先后关系不成立。",
                    "核对原始时间记录后重新评估。"
            ));
        }
        if (hasInvalidClinicalValue(data)) {
            flags.add(flag(
                    "INVALID_CLINICAL_VALUE", "CRITICAL", "临床数值超出录入范围",
                    "至少一个生命体征、量表或实验室数值超出系统允许范围。",
                    "核对单位与原始报告，修正后重新评估。"
            ));
        }
        if (data.ctHemorrhage() == ClinicalState.YES) {
            flags.add(flag(
                    "CT_HEMORRHAGE", "CRITICAL", "影像提示颅内出血",
                    "结构化影像结论标记为存在颅内出血。",
                    "停止自动决策并立即由卒中团队复核影像与处置路径。"
            ));
        }
        if (data.plateletCount() != null && data.plateletCount() < 100) {
            flags.add(flag(
                    "PLATELET_LOW", "CRITICAL", "血小板低于复核阈值",
                    "血小板计数低于 100×10^9/L。",
                    "复核检验结果并进行静脉溶栓禁忌症人工审查。"
            ));
        }
        if (data.inr() != null && data.inr().compareTo(new BigDecimal("1.7")) > 0) {
            flags.add(flag(
                    "INR_ELEVATED", "CRITICAL", "INR 高于复核阈值",
                    "INR 高于 1.7。",
                    "结合抗凝药类型、末次用药时间和实验室结果进行人工审查。"
            ));
        }
        if ((data.systolicBloodPressure() != null && data.systolicBloodPressure() > 185)
                || (data.diastolicBloodPressure() != null && data.diastolicBloodPressure() > 110)) {
            flags.add(flag(
                    "BP_REVIEW_REQUIRED", "CRITICAL", "血压超过再灌注治疗复核阈值",
                    "当前血压高于 185/110 mmHg 中的任一阈值。",
                    "立即复测并由临床医生评估血压管理与治疗路径。"
            ));
        }
        if (timeline.dntOverTarget()) {
            flags.add(flag(
                    "DNT_OVER_TARGET", "WARNING", "到院时间已超过 60 分钟",
                    "系统计时显示到院至当前时间超过 60 分钟。",
                    "核对时间记录并按院内卒中绿色通道升级协调。"
            ));
        }
        return flags;
    }

    private boolean hasInvalidClinicalValue(StrokeAssessmentData data) {
        return outside(data.systolicBloodPressure(), 40, 300)
                || outside(data.diastolicBloodPressure(), 20, 200)
                || outside(data.nihssScore(), 0, 42)
                || outside(data.plateletCount(), 0, 2000)
                || outside(data.bloodGlucoseMmolL(), new BigDecimal("0.5"), new BigDecimal("50"))
                || outside(data.inr(), new BigDecimal("0.1"), new BigDecimal("20"));
    }

    private boolean outside(Integer value, int minimum, int maximum) {
        return value != null && (value < minimum || value > maximum);
    }

    private boolean outside(BigDecimal value, BigDecimal minimum, BigDecimal maximum) {
        return value != null && (value.compareTo(minimum) < 0 || value.compareTo(maximum) > 0);
    }

    private SafetyFlag flag(String code, String severity, String title, String detail, String action) {
        return new SafetyFlag(
                code,
                severity,
                title,
                detail,
                action,
                "《中国急性缺血性卒中诊治指南2023》（请以知识库原文页码复核）"
        );
    }

    private List<String> findMissingFields(StrokeAssessmentData data) {
        List<String> missing = new ArrayList<>();
        if (data.lastKnownWellAt() == null) missing.add("最后正常时间");
        if (data.arrivalAt() == null) missing.add("到院时间");
        if (data.systolicBloodPressure() == null || data.diastolicBloodPressure() == null) missing.add("血压");
        if (data.bloodGlucoseMmolL() == null) missing.add("血糖");
        if (data.nihssScore() == null) missing.add("NIHSS评分");
        if (data.plateletCount() == null) missing.add("血小板计数");
        if (data.inr() == null) missing.add("INR");
        if (isUnknown(data.anticoagulantUse())) missing.add("抗凝药使用情况");
        if (isUnknown(data.ctHemorrhage())) missing.add("头颅CT出血结论");
        return missing;
    }

    private boolean isUnknown(ClinicalState state) {
        return state == null || state == ClinicalState.UNKNOWN;
    }

    private Long elapsedMinutes(LocalDateTime start, LocalDateTime end) {
        if (start == null || start.isAfter(end)) return null;
        return Duration.between(start, end).toMinutes();
    }

    private TimeWindowStatus thrombolysisWindow(Long onsetMinutes) {
        if (onsetMinutes == null) return TimeWindowStatus.UNKNOWN;
        return onsetMinutes <= 270 ? TimeWindowStatus.OPEN : TimeWindowStatus.CLOSED;
    }

    private TimeWindowStatus thrombectomyWindow(Long onsetMinutes) {
        if (onsetMinutes == null) return TimeWindowStatus.UNKNOWN;
        if (onsetMinutes <= 360) return TimeWindowStatus.OPEN;
        if (onsetMinutes <= 1440) return TimeWindowStatus.CONDITIONAL;
        return TimeWindowStatus.CLOSED;
    }
}
