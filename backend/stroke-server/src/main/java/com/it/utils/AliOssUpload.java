package com.it.utils;

import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import com.aliyun.oss.common.auth.EnvironmentVariableCredentialsProvider;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;

import java.io.ByteArrayInputStream;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

@Data
@Slf4j
@AllArgsConstructor
public class AliOssUpload {
    private String endpoint ;
    private String bucketName ;
    private String region ;
    private String accessKeyId;
    private String accessKeySecret;

    public String upload(byte[] content, String originalFilename) throws Exception {
        String dir = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy/MM"));
        String newFileName = UUID.randomUUID() + originalFilename.substring(originalFilename.lastIndexOf("."));
        String objectName = dir + "/" + newFileName;

        // 创建OSSClient实例（修改这里）
        OSS ossClient;
        if (accessKeyId != null && !accessKeyId.isEmpty()) {
            // 使用配置文件的 Key
             ossClient = new OSSClientBuilder().build(endpoint, accessKeyId, accessKeySecret);
        } else {
            // 从环境变量中获取访问凭证
            EnvironmentVariableCredentialsProvider credentialsProvider =
                    CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
            ossClient = new OSSClientBuilder().build(endpoint, credentialsProvider);
        }

        try {
            ossClient.putObject(bucketName, objectName, new ByteArrayInputStream(content));
        } finally {
            ossClient.shutdown();
        }

        return endpoint.split("//")[0] + "//" + bucketName + "." + endpoint.split("//")[1] + "/" + objectName;
    }
}
