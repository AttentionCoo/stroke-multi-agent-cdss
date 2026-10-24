package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** AI 会诊的医生复核任务。 */
@Data
@TableName("clinical_review_task")
public class ClinicalReviewTask {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long doctorId;
    private Long talkId;
    private String threadId;
    /** PENDING / COMPLETED / FAILED */
    private String status;
    /** 待复核摘要的 JSON 原文。 */
    private String payloadJson;
    /** APPROVED / REJECTED */
    private String decision;
    private String feedback;
    private String answer;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
