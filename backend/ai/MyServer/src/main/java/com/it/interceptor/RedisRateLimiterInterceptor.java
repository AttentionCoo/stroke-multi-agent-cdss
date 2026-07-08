package com.it.interceptor;

import com.it.utils.IpUtil;
import com.it.utils.ThreadLocalUtil;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Collections;

/**
 * 基于 Redis 的全局 API 限流拦截器（order=0，最先执行）。
 *
 * <p>实现三级限流：
 * <ul>
 *   <li><b>全局</b> — 所有请求共享的 QPS 上限</li>
 *   <li><b>IP 级</b> — 单 IP 的请求频率上限</li>
 *   <li><b>用户级</b> — 已登录用户的请求频率上限</li>
 * </ul>
 *
 * <p>使用 Redis Lua 脚本保证滑动窗口计数的原子性。
 * 限流参数从 application.yml 中的 rate-limiter 配置段读取。
 */
@Slf4j
public class RedisRateLimiterInterceptor implements HandlerInterceptor {

    private final StringRedisTemplate stringRedisTemplate;

    @Value("${rate-limiter.global.limit:200}")
    private int globalLimit;
    @Value("${rate-limiter.global.interval:1}")
    private int globalInterval;

    @Value("${rate-limiter.ip.limit:30}")
    private int ipLimit;
    @Value("${rate-limiter.ip.interval:60}")
    private int ipInterval;

    @Value("${rate-limiter.user.limit:3}")
    private int userLimit;
    @Value("${rate-limiter.user.interval:60}")
    private int userInterval;

    /** Lua 脚本：滑动窗口计数器，在单个原子操作中完成 incr + expire + 判断 */
    private static final String SLIDING_WINDOW_SCRIPT =
            "local key = KEYS[1] " +
            "local limit = tonumber(ARGV[1]) " +
            "local window = tonumber(ARGV[2]) " +
            "local current = redis.call('INCR', key) " +
            "if current == 1 then " +
            "    redis.call('EXPIRE', key, window) " +
            "end " +
            "if current > limit then " +
            "    return 0 " +
            "else " +
            "    return 1 " +
            "end";

    private final DefaultRedisScript<Long> rateLimitScript;

    public RedisRateLimiterInterceptor(StringRedisTemplate stringRedisTemplate,
                                                       int globalLimit, int globalInterval,
                                                       int ipLimit, int ipInterval,
                                                       int userLimit, int userInterval) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.rateLimitScript = new DefaultRedisScript<>(SLIDING_WINDOW_SCRIPT, Long.class);
        this.globalLimit = globalLimit;
        this.globalInterval = globalInterval;
        this.ipLimit = ipLimit;
        this.ipInterval = ipInterval;
        this.userLimit = userLimit;
        this.userInterval = userInterval;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) throws Exception {
        String uri = request.getRequestURI();

        // 不限制的路径（静态资源、健康检查等）
        if (isExcluded(uri)) {
            return true;
        }

        // ── 1. 全局限流 ──────────────────────────────────────────────────────
        String globalKey = "rate:global:" + getCurrentSecondKey();
        if (!checkRate(globalKey, globalLimit, globalInterval)) {
            log.warn("全局限流触发: key={}, limit={}/{}s", globalKey, globalLimit, globalInterval);
            sendRateLimited(response, "系统繁忙，请稍后重试");
            return false;
        }

        // ── 2. IP 限流 ───────────────────────────────────────────────────────
        String ip = IpUtil.getIp();
        if (!"unknown".equals(ip)) {
            String ipKey = "rate:ip:" + ip + ":" + getWindowKey(ipInterval);
            if (!checkRate(ipKey, ipLimit, ipInterval)) {
                log.warn("IP 限流触发: ip={}, limit={}/{}s", ip, ipLimit, ipInterval);
                sendRateLimited(response, "请求过于频繁，请稍后重试");
                return false;
            }
        }

        // ── 3. 用户限流 ──────────────────────────────────────────────────────
        try {
            var user = ThreadLocalUtil.getCurrentUser();
            if (user != null && user.getId() != null) {
                String userKey = "rate:user:" + user.getId() + ":" + getWindowKey(userInterval);
                if (!checkRate(userKey, userLimit, userInterval)) {
                    log.warn("用户限流触发: userId={}, limit={}/{}s", user.getId(), userLimit, userInterval);
                    sendRateLimited(response, "操作过于频繁，请稍后重试");
                    return false;
                }
            }
        } catch (Exception e) {
            // ThreadLocal 中没有用户（未登录），跳过用户级限流
            log.debug("用户级限流跳过: 未登录或 ThreadLocal 中没有用户");
        }

        return true;
    }

    /**
     * 执行滑动窗口限流检查。
     *
     * @param key    Redis key
     * @param limit  窗口内最大请求数
     * @param window 窗口大小（秒）
     * @return true=放行, false=限流
     */
    private boolean checkRate(String key, int limit, int window) {
        try {
            Long result = stringRedisTemplate.execute(
                    rateLimitScript,
                    Collections.singletonList(key),
                    String.valueOf(limit),
                    String.valueOf(window)
            );
            return result != null && result == 1;
        } catch (Exception e) {
            log.warn("限流检查异常，默认放行: key={}, err={}", key, e.getMessage());
            return true; // Redis 不可用时默认放行，避免误拦合法请求
        }
    }

    /** 秒级窗口 key（用于全局 QPS 限流） */
    private String getCurrentSecondKey() {
        return String.valueOf(System.currentTimeMillis() / 1000);
    }

    /** 分钟级窗口 key（用于 IP/用户限流，按 interval 分桶） */
    private String getWindowKey(int intervalSeconds) {
        return String.valueOf(System.currentTimeMillis() / 1000 / intervalSeconds);
    }

    /** 排除静态资源和监控端点 */
    private boolean isExcluded(String uri) {
        if (uri == null) return true;
        return uri.startsWith("/api/monitor/")
                || uri.contains(".")
                || uri.startsWith("/error")
                || uri.startsWith("/actuator");
    }

    private void sendRateLimited(HttpServletResponse response, String msg) throws Exception {
        response.setContentType("application/json;charset=UTF-8");
        response.setStatus(429); // HTTP 429 Too Many Requests
        response.getWriter().write("{\"code\": 429, \"msg\": \"" + msg + "\"}");
    }
}
