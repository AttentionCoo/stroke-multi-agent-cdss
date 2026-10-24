package com.it.controller;

import com.it.pojo.Result;
import com.it.service.DashboardSummaryService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/dashboard")
@RequiredArgsConstructor
public class DashboardController {

    private final DashboardSummaryService dashboardSummaryService;

    @GetMapping("/summary")
    public Result summary() {
        return Result.success(dashboardSummaryService.summary(currentDoctorId()));
    }

    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
