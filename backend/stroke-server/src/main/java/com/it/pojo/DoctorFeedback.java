package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 医生对某条 AI 回答的结构化反馈。 */
@Data
@TableName("doctor_feedback")
public class DoctorFeedback {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long doctorId;
    private Long talkId;
    /** 1=有帮助, -1=需改进 */
    private Integer rating;
    private String category;
    private String comment;
    private String answerExcerpt;
    private LocalDateTime createTime;
}
