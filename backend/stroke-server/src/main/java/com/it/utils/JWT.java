package com.it.utils;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
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

    private static byte[] keyBytes() {
        if (secretKey == null || secretKey.isBlank()) {
            throw new IllegalStateException("JWT 密钥未初始化，请检查 ai.security.shared-jwt-secret 配置项");
        }
        return secretKey.getBytes(StandardCharsets.UTF_8);
    }

    public static String generateToken(Map<String,Object> claims) {
        return Jwts.builder()
                .signWith(SignatureAlgorithm.HS256, keyBytes())
                .setExpiration(new Date(System.currentTimeMillis() + 1000 * 60 * 60 * 24 * 3))
                .addClaims(claims)
                .compact();
    }

    public static Claims parseToken(String token) {
        return Jwts.parser()
                .setSigningKey(keyBytes())
                .parseClaimsJws(token)
                .getBody();
    }

    public static Long getUserIdFromToken(String token) {
        return Long.valueOf(parseToken(token).get("id").toString());
    }

    // --- 新增：从 Token 中获取 JTI ---
    public static String getJtiFromToken(String token) {
        return parseToken(token).get("jti").toString();
    }
}