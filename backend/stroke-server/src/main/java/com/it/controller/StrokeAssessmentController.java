package com.it.controller;

import com.it.domain.stroke.AssessmentReviewData;
import com.it.domain.stroke.StrokeAssessmentData;
import com.it.domain.stroke.StrokeAssessmentModule;
import com.it.domain.stroke.StrokeAssessmentView;
import com.it.pojo.Result;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/stroke-assessments")
@RequiredArgsConstructor
public class StrokeAssessmentController {

    private final StrokeAssessmentModule module;

    @PostMapping("/evaluate")
    public Result evaluate(@RequestBody StrokeAssessmentData data) {
        return Result.success(module.evaluate(data));
    }

    @PostMapping
    public Result create(@RequestBody StrokeAssessmentData data) {
        return Result.success(module.create(currentDoctorId(), data));
    }

    @GetMapping
    public Result list(@RequestParam(defaultValue = "20") int limit) {
        return Result.success(module.list(currentDoctorId(), limit));
    }

    /**
     * 绿道质控看板: 聚合当前医生的评估记录, 计算 DNT/时间窗/完整率/风险信号等过程质量指标。
     */
    @GetMapping("/qc-stats")
    public Result qcStats() {
        List<StrokeAssessmentView> records = module.list(currentDoctorId(), 200);
        Map<String, Object> stats = computeQcStats(records);
        return Result.success(stats);
    }

    private Map<String, Object> computeQcStats(List<StrokeAssessmentView> records) {
        Map<String, Object> stats = new HashMap<>();
        stats.put("total", records.size());

        // DNT(到院-最后正常)与 4.5h 窗口内比例
        List<Long> dntMinutes = new ArrayList<>();
        int withinWindow = 0;
        int dntCount = 0;
        double nihssSum = 0;
        int nihssCount = 0;
        int riskHits = 0;
        int missingFields = 0;
        int totalKeyFields = 0;
        Map<String, Integer> statusCounts = new LinkedHashMap<>();
        Map<String, Integer> trend = new LinkedHashMap<>();

        for (StrokeAssessmentView r : records) {
            StrokeAssessmentData d = r.data();
            if (d.lastKnownWellAt() != null && d.arrivalAt() != null) {
                long minutes = Math.max(0, Duration.between(d.lastKnownWellAt(), d.arrivalAt()).toMinutes());
                dntMinutes.add(minutes);
                dntCount++;
                if (minutes <= 270) withinWindow++;
            }
            if (d.nihssScore() != null) {
                nihssSum += d.nihssScore();
                nihssCount++;
            }
            // 关键风险信号
            boolean risky = (d.systolicBloodPressure() != null && d.systolicBloodPressure() > 185)
                    || (d.diastolicBloodPressure() != null && d.diastolicBloodPressure() > 110)
                    || (d.bloodGlucoseMmolL() != null && d.bloodGlucoseMmolL().compareTo(new BigDecimal("10")) >= 0)
                    || (d.inr() != null && d.inr().compareTo(new BigDecimal("1.7")) >= 0)
                    || (d.plateletCount() != null && d.plateletCount() < 100);
            if (risky) riskHits++;
            // 关键字段完整率(8 个关键字段)
            Object[] keyFields = {
                    d.lastKnownWellAt(), d.arrivalAt(), d.systolicBloodPressure(),
                    d.bloodGlucoseMmolL(), d.nihssScore(), d.plateletCount(), d.inr(), d.ctHemorrhage()
            };
            for (Object f : keyFields) {
                totalKeyFields++;
                if (f == null) missingFields++;
            }
            statusCounts.merge(r.status().name(), 1, Integer::sum);
            if (r.updatedAt() != null) {
                String day = r.updatedAt().toLocalDate().toString();
                trend.merge(day, 1, Integer::sum);
            }
        }

        stats.put("dntCount", dntCount);
        stats.put("dntAvgMinutes", dntCount > 0 ? Math.round(dntMinutes.stream().mapToLong(Long::longValue).average().orElse(0)) : 0);
        stats.put("dntMedianMinutes", median(dntMinutes));
        stats.put("withinWindowCount", withinWindow);
        stats.put("withinWindowRate", dntCount > 0 ? Math.round(withinWindow * 1000.0 / dntCount) / 10.0 : 0.0);
        stats.put("nihssAvg", nihssCount > 0 ? Math.round(nihssSum * 10.0 / nihssCount) / 10.0 : 0.0);
        stats.put("riskHitCount", riskHits);
        stats.put("keyFieldCompleteRate", totalKeyFields > 0
                ? Math.round((totalKeyFields - missingFields) * 1000.0 / totalKeyFields) / 10.0 : 0.0);
        stats.put("statusCounts", statusCounts);
        stats.put("trend", trend);
        return stats;
    }

    private long median(List<Long> values) {
        if (values.isEmpty()) return 0;
        List<Long> sorted = new ArrayList<>(values);
        sorted.sort(Long::compareTo);
        int n = sorted.size();
        if (n % 2 == 1) return sorted.get(n / 2);
        return Math.round((sorted.get(n / 2 - 1) + sorted.get(n / 2)) / 2.0);
    }

    @GetMapping("/{id}")
    public Result get(@PathVariable Long id) {
        return Result.success(module.get(currentDoctorId(), id));
    }

    @PutMapping("/{id}")
    public Result update(@PathVariable Long id, @RequestBody StrokeAssessmentData data) {
        return Result.success(module.update(currentDoctorId(), id, data));
    }

    @PostMapping("/{id}/reviews")
    public Result review(@PathVariable Long id, @RequestBody AssessmentReviewData data) {
        return Result.success(module.review(currentDoctorId(), id, data));
    }

    @GetMapping("/{id}/reviews")
    public Result reviews(@PathVariable Long id) {
        return Result.success(module.reviews(currentDoctorId(), id));
    }

    @GetMapping("/{id}/fhir")
    public Result exportFhir(@PathVariable Long id) {
        return Result.success(module.exportFhir(currentDoctorId(), id));
    }

    private Long currentDoctorId() {
        if (ThreadLocalUtil.getCurrentUser() == null) {
            throw new IllegalStateException("当前用户未登录");
        }
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
