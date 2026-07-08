package com.it.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

/**
 * OSS 文档信息 VO
 * id 为 OSS key 的 Base64 URL 安全编码，供前端调用签名 URL 接口时传回
 */
@Data
@AllArgsConstructor
public class DocumentVO {
    /** Base64-URL 编码的 OSS key，用于后续请求签名 URL */
    private String id;
    /** 文件名（不含路径），例如：急性缺血性脑卒中诊治指南2024.pdf */
    private String name;
    /** 分类名（OSS 路径第一级子目录），例如：指南 */
    private String category;
    /** 文件大小（字节） */
    private long size;
}
