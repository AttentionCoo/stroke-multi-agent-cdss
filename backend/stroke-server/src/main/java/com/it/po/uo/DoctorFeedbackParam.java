package com.it.po.uo;

import lombok.Data;

/** 医生提交 AI 回答反馈的请求体。 */
@Data
public class DoctorFeedbackParam {
    private Long talkId;
    /** 1=有帮助, -1=需改进 */
    private Integer rating;
    private String category;
    private String comment;
    private String answerExcerpt;
}
