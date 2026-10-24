package com.it.controller;

import com.it.po.uo.ClinicalReportParam;
import com.it.po.uo.ReportSignParam;
import com.it.pojo.Result;
import com.it.service.ClinicalReportService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/reports")
@RequiredArgsConstructor
public class ClinicalReportController {

    private final ClinicalReportService reportService;

    @GetMapping("/by-talk/{talkId}")
    public Result listByTalk(@PathVariable Long talkId) {
        return Result.success(reportService.listByTalk(currentDoctorId(), talkId));
    }

    @GetMapping("/{reportId}")
    public Result get(@PathVariable Long reportId) {
        return Result.success(reportService.getOwned(currentDoctorId(), reportId));
    }

    @PostMapping
    public Result saveDraft(@RequestBody ClinicalReportParam param) {
        return Result.success(reportService.saveDraft(currentDoctorId(), param));
    }

    @PostMapping("/{reportId}/sign")
    public Result sign(@PathVariable Long reportId, @RequestBody ReportSignParam param) {
        return Result.success(reportService.sign(currentDoctorId(), reportId, param.getSignature()));
    }

    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
