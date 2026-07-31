package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("stroke_assessment_review")
public class AssessmentReviewEntity {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long assessmentId;
    private Long doctorId;
    private String action;
    private String reason;
    private Integer assessmentVersion;
    private String assessmentSnapshot;
    private LocalDateTime createTime;
}
