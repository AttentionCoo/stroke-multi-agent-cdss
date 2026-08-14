package com.it.utils;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Map;

public class JWT {
    // 由 JwtConfig 在 Spring 启动时通过 setSecretKey() 注入，禁止在此处硬编码密钥
    private static String secretKey;

    /**
     * 由 JwtConfig#init() 调用，将配置文件中的密钥注入到静态字段。
     * 应用启动后仅调用一次。
     */
    public static void setSecretKey(String key) {
        secretKey = key;
    }

    private static SecretKey signingKey() {
        if (secretKey == null || secretKey.isBlank()) {
            throw new IllegalStateException("JWT 密钥未初始化，请检查 ai.security.shared-jwt-secret 配置项");
        }
        return Keys.hmacShaKeyFor(secretKey.getBytes(StandardCharsets.UTF_8));
    }

    public static String generateToken(Map<String, Object> claims) {
        return Jwts.builder()
                .claims(claims)
                .expiration(new Date(System.currentTimeMillis() + 1000 * 60 * 60 * 24 * 3))
                // 显式 HS256：模型服务(PyJWT)按 HS256 验签，需与 ALGORITHM 保持一致
                .signWith(signingKey(), Jwts.SIG.HS256)
                .compact();
    }

    public static Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith(signingKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public static Long getUserIdFromToken(String token) {
        return Long.valueOf(parseToken(token).get("id").toString());
    }

    // --- 新增：从 Token 中获取 JTI ---
    public static String getJtiFromToken(String token) {
        return parseToken(token).get("jti").toString();
    }
}
