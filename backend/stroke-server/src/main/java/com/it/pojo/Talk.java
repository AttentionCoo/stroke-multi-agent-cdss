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
    private String title;
    private String content;

    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}