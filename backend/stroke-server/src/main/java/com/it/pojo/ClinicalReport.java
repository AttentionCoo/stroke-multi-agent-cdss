package com.it.pojo;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** AI 临床报告工作台草稿与签署记录。 */
@Data
@TableName("clinical_report")
public class ClinicalReport {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long doctorId;
    private Long talkId;
    private Integer messageIndex;
    private String title;
    private String originalContent;
    private String content;
    /** DRAFT / SIGNED */
    private String status;
    private String signature;
    private Integer version;
    private LocalDateTime signedAt;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
