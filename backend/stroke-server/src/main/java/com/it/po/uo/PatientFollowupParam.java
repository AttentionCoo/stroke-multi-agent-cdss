package com.it.po.uo;

import lombok.Data;

import java.time.LocalDate;

/** 新建随访任务 / 录入随访结局的请求体。 */
@Data
public class PatientFollowupParam {
    private LocalDate plannedDate;
    private String followupType;
    private Integer mrsScore;
    private String recurrence;
    private String adherence;
    private String notes;
}
