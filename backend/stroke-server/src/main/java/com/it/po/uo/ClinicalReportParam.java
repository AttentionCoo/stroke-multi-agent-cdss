package com.it.po.uo;

import lombok.Data;

/** 保存 AI 报告草稿的请求体。 */
@Data
public class ClinicalReportParam {
    private Long talkId;
    private Integer messageIndex;
    private String title;
    private String originalContent;
    private String content;
    private String signature;
}
