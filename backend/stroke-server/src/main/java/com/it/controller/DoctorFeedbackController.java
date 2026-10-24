package com.it.controller;

import com.it.po.uo.DoctorFeedbackParam;
import com.it.pojo.Result;
import com.it.service.DoctorFeedbackService;
import com.it.utils.ThreadLocalUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/feedback")
@RequiredArgsConstructor
public class DoctorFeedbackController {

    private final DoctorFeedbackService feedbackService;

    @PostMapping
    public Result submit(@RequestBody DoctorFeedbackParam param) {
        return Result.success(feedbackService.submit(currentDoctorId(), param));
    }

    @GetMapping("/summary")
    public Result summary() {
        return Result.success(feedbackService.summary(currentDoctorId()));
    }

    private Long currentDoctorId() {
        return ThreadLocalUtil.getCurrentUser().getId();
    }
}
