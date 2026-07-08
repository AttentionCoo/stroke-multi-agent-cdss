package com.it.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

/**
 * OSS 文档签名 URL 响应 VO
 * previewUrl：直接在浏览器内预览（inline）
 * downloadUrl：强制下载（content-disposition: attachment）
 */
@Data
@AllArgsConstructor
public class DocumentUrlVO {
    private String id;
    private String name;
    /** 预览签名 URL（有效期 30 分钟） */
    private String previewUrl;
    /** 下载签名 URL（带 content-disposition=attachment，有效期 30 分钟） */
    private String downloadUrl;
}
