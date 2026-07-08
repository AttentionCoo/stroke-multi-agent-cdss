package com.it.pojo;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@ConfigurationProperties(prefix = "aiserver.alioss")
@Component
public class AliOssProperties {
    public String endpoint ;
    public String bucketName ;
    public String region ;
    public String accessKeyId;
    public String accessKeySecret;
    /** OSS 中 PDF 文档的根路径前缀，例如 documents/ */
    public String documentPrefix = "documents/";
    /** 签名 URL 有效期（秒），默认 30 分钟 */
    public long signUrlExpiration = 1800;
}
