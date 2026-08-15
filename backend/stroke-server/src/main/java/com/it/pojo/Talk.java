package com.it.pojo;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Builder;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("talk")
@Builder
public class Talk {

    // 关键：前端传入时间戳
    @TableId(type = IdType.INPUT)
    private Long id;

    private Long userId;
    private Long patientId;
    private String title;
    private String content;
    /** 思考链历史(JSON数组, 每轮推理过程/专家意见/用量), 供刷新后重新打开思维链 */
    private String thinkingJson;

    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
