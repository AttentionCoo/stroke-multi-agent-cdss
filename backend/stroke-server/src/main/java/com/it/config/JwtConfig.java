package com.it.config;

import com.it.utils.JWT;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 将配置文件中的 JWT 密钥注入到静态工具类 JWT 中。
 * <p>
 * 密钥来源优先级：
 *   环境变量 AI_API_SHARED_JWT_SECRET
 *     → application-prod.yml: aiserver.ai-api.shared-jwt-secret
 *       → application.yml: ai.security.shared-jwt-secret
 * <p>
 * ⚠️  Python 模型服务必须设置相同的环境变量 AI_JWT_SECRET，
 *     两端密钥一致才能通过 /model/get_result 的 Token 校验。
 */
@Component
public class JwtConfig {

    private static final Logger log = LoggerFactory.getLogger(JwtConfig.class);

    @Value("${ai.security.shared-jwt-secret}")
    private String sharedJwtSecret;

    @PostConstruct
    public void init() {
        if (sharedJwtSecret == null || sharedJwtSecret.isBlank()) {
            throw new IllegalStateException(
                    "ai.security.shared-jwt-secret 未配置。" +
                    "请在环境变量中设置 AI_API_SHARED_JWT_SECRET，" +
                    "并确保与 Python 模型服务的 AI_JWT_SECRET 值完全相同。"
            );
        }
        JWT.setSecretKey(sharedJwtSecret);
        log.info("JWT 密钥已从配置加载（长度={}）", sharedJwtSecret.length());
    }
}
