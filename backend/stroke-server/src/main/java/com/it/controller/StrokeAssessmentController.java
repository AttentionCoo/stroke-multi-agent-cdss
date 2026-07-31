package com.it.controller;

import com.it.domain.stroke.AssessmentReviewData;
import com.it.domain.stroke.StrokeAssessmentData;
import com.it.domain.stroke.StrokeAssessmentModule;
import com.it.pojo.Result;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

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
