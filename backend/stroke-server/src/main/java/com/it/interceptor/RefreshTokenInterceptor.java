package com.it.interceptor;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import com.it.po.dto.UserDTO;
import com.it.utils.JWT;
import com.it.utils.ThreadLocalUtil;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
public class RefreshTokenInterceptor implements HandlerInterceptor {

    private final StringRedisTemplate stringRedisTemplate;

    public RefreshTokenInterceptor(StringRedisTemplate stringRedisTemplate) {
        this.stringRedisTemplate = stringRedisTemplate;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        String token = resolveToken(request);
        if (StrUtil.isBlank(token)) {
            return true;
        }

        try {
            Long userId = JWT.getUserIdFromToken(token);

            // ── Token 黑名单检查 ──────────────────────────────────────────────
            // 用户退出登录后 Token 的 JTI 会被加入黑名单，TTL 与 Token 剩余有效时间一致
            Object jtiObj = JWT.parseToken(token).get("jti");
            if (jtiObj == null) {
                log.warn("Token 中缺少 jti，可能是旧 Token");
                sendUnauthorized(response, "Token 已过期，请重新登录");
                return false;
            }
            String tokenJti = jtiObj.toString();

            // 检查 JTI 是否在黑名单中（退出登录后加入）
            String blacklistKey = "token:blacklist:" + tokenJti;
            String blacklisted = stringRedisTemplate.opsForValue().get(blacklistKey);
            if (blacklisted != null) {
                log.info("Token 已被加入黑名单（用户已退出登录）: userId={}", userId);
                sendUnauthorized(response, "Token 已失效，请重新登录");
                return false;
            }

            // ── SSO 检查：验证当前 JTI 是否为该用户的最新登录 ──────────────────
            String redisJti = stringRedisTemplate.opsForValue().get("login:user:" + userId);
            if (redisJti == null) {
                log.warn("用户 {} 在 Redis 中没有登录记录，可能是 Token 过期了", userId);
                sendUnauthorized(response, "Token 已过期，请重新登录");
                return false;
            }

            if (!redisJti.equals(tokenJti)) {
                log.warn("用户 {} 在其他地方登录了，当前 Token 已失效", userId);
                sendUnauthorized(response, "您的账号已在其他地方登录，请重新登录");
                return false;
            }

            // ── 加载用户会话 ──────────────────────────────────────────────────
            Map<Object, Object> userMap = stringRedisTemplate.opsForHash().entries("user:token:" + token);
            if (userMap.isEmpty()) {
                log.warn("Token 在 Redis 中未找到用户会话: userId={}", userId);
                sendUnauthorized(response, "登录状态已失效，请重新登录");
                return false;
            }

            UserDTO userDTO = BeanUtil.fillBeanWithMap(userMap, new UserDTO(), false);
            ThreadLocalUtil.setCurrentUser(userDTO);

            // 刷新 Token 会话 TTL
            stringRedisTemplate.expire("user:token:" + token, 30, TimeUnit.MINUTES);

            // ── 在线用户统计 ──────────────────────────────────────────────────
            updateOnlineUser(userId);

        } catch (Exception e) {
            log.error("Token 解析失败: {}", e.getMessage());
            sendUnauthorized(response, "Token 解析失败，请重新登录");
            return false;
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        ThreadLocalUtil.removeCurrentUser();
    }

    /**
     * 更新在线用户心跳时间戳。
     * 使用 Redis ZSet 存储，score = 最后活跃时间戳（epoch ms）。
     * 3 分钟内无请求视为离线。
     */
    private void updateOnlineUser(Long userId) {
        try {
            long now = System.currentTimeMillis();
            stringRedisTemplate.opsForZSet().add("online:users", userId.toString(), now);
            // 异步清理：定期由 @Scheduled 方法执行（见 OnlineUserCleanupTask）
        } catch (Exception e) {
            log.warn("更新在线用户状态失败: userId={}, err={}", userId, e.getMessage());
        }
    }

    private String resolveToken(HttpServletRequest request) {
        String token = request.getHeader("token");
        if (StrUtil.isNotBlank(token)) {
            return token.trim();
        }
        String authorization = request.getHeader("Authorization");
        if (StrUtil.isBlank(authorization)) {
            return null;
        }
        authorization = authorization.trim();
        return authorization.startsWith("Bearer ") ? authorization.substring(7).trim() : authorization;
    }

    private void sendUnauthorized(HttpServletResponse response, String msg) throws Exception {
        response.setContentType("application/json;charset=UTF-8");
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.getWriter().write("{\"code\": 401, \"msg\": \"" + msg + "\"}");
    }
}
