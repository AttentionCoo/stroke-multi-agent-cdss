package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;

/** 卒中患者的随访任务与结局记录。 */
@Data
@TableName("patient_followup")
public class PatientFollowup {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long doctorId;
    private Long patientId;
    private LocalDate plannedDate;
    private String followupType;
    /** PENDING / COMPLETED / CANCELLED */
    private String status;
    private Integer mrsScore;
    private String recurrence;
    private String adherence;
    private String notes;
    private LocalDateTime completedAt;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
