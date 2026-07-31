package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("stroke_assessment")
public class StrokeAssessmentEntity {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long doctorId;
    private Long patientId;
    private LocalDateTime lastKnownWellAt;
    private LocalDateTime arrivalAt;
    private Integer systolicBloodPressure;
    private Integer diastolicBloodPressure;
    private BigDecimal bloodGlucoseMmolL;
    private Integer nihssScore;
    private Integer plateletCount;
    private BigDecimal inr;
    private String anticoagulantUse;
    private LocalDateTime anticoagulantLastDoseAt;
    private String ctHemorrhage;
    private String ctaLargeVesselOcclusion;
    private String notes;
    private Integer version;
    private String status;
    private String changeSummary;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
