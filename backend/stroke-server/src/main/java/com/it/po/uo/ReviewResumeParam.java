package com.it.po.uo;

import lombok.Data;

/** 医生对挂起会诊结论的复核决定。 */
@Data
public class ReviewResumeParam {
    private Boolean approved;
    private String feedback;
}
