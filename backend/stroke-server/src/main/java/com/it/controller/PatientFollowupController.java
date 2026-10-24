package com.it.controller;

import com.it.po.uo.PatientFollowupParam;
import com.it.pojo.PatientFollowup;
import com.it.pojo.Result;
import com.it.service.PatientFollowupService;
import com.it.service.PatientTimelineService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/patients/{patientId}")
@RequiredArgsConstructor
public class PatientFollowupController {

    private final PatientFollowupService followupService;
    private final PatientTimelineService timelineService;

    @GetMapping("/followups")
    public Result list(@PathVariable Long patientId) {
        return Result.success(followupService.list(currentDoctorId(), patientId));
    }

    @PostMapping("/followups")
    public Result create(@PathVariable Long patientId, @RequestBody PatientFollowupParam param) {
        return Result.success(followupService.create(currentDoctorId(), patientId, param));
    }

    @PutMapping("/followups/{followupId}/complete")
    public Result complete(@PathVariable Long patientId,
                           @PathVariable Long followupId,
                           @RequestBody PatientFollowupParam param) {
        return Result.success(followupService.complete(currentDoctorId(), patientId, followupId, param));
    }

    @GetMapping("/timeline")
    public Result timeline(@PathVariable Long patientId) {
        return Result.success(timelineService.timeline(currentDoctorId(), patientId));
    }

    @GetMapping("/followups/summary")
    public Result followupSummary(@PathVariable Long patientId) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("pendingDue", followupService.pendingCount(currentDoctorId(), patientId));
        return Result.success(data);
    }

    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
