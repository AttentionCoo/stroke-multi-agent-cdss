package com.it.cache;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Set;

/**
 * 在线用户追踪器。
 *
 * <p>通过 Redis ZSet 维护在线用户及其最后活跃时间：
 * <ul>
 *   <li>用户每次请求时由 {@code RefreshTokenInterceptor} 更新 score（epoch ms）</li>
 *   <li>每 2 分钟自动清理超过 3 分钟无请求的离线用户</li>
 * </ul>
 *
 * <p>查询接口：
 * <ul>
 *   <li>{@link #getOnlineUserCount()} — 获取当前在线用户数</li>
 *   <li>{@link #getOnlineUserIds()} — 获取当前在线用户 ID 集合</li>
 *   <li>{@link #isUserOnline(Long)} — 检查指定用户是否在线</li>
 * </ul>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OnlineUserTracker {

    private final StringRedisTemplate stringRedisTemplate;

    private static final String ONLINE_USERS_KEY = "online:users";
    /** 超过此时间（毫秒）无请求视为离线 */
    private static final long OFFLINE_THRESHOLD_MS = 3 * 60 * 1000L; // 3 分钟

    /**
     * 每 2 分钟清理一次离线用户。
     */
    @Scheduled(fixedDelay = 120_000)
    public void cleanOfflineUsers() {
        long cutoff = System.currentTimeMillis() - OFFLINE_THRESHOLD_MS;
        try {
            Long removed = stringRedisTemplate.opsForZSet()
                    .removeRangeByScore(ONLINE_USERS_KEY, 0, cutoff);
            if (removed != null && removed > 0) {
                log.debug("已清理 {} 个离线用户（超过 {}ms 无请求）", removed, OFFLINE_THRESHOLD_MS);
            }
        } catch (Exception e) {
            log.warn("清理离线用户失败: {}", e.getMessage());
        }
    }

    /**
     * 获取当前在线用户数。
     */
    public long getOnlineUserCount() {
        try {
            Long count = stringRedisTemplate.opsForZSet().size(ONLINE_USERS_KEY);
            return count != null ? count : 0;
        } catch (Exception e) {
            log.warn("获取在线用户数失败: {}", e.getMessage());
            return 0;
        }
    }

    /**
     * 获取当前在线用户 ID 集合。
     */
    public Set<String> getOnlineUserIds() {
        long cutoff = System.currentTimeMillis() - OFFLINE_THRESHOLD_MS;
        try {
            return stringRedisTemplate.opsForZSet()
                    .rangeByScore(ONLINE_USERS_KEY, cutoff, Double.MAX_VALUE);
        } catch (Exception e) {
            log.warn("获取在线用户列表失败: {}", e.getMessage());
            return Set.of();
        }
    }

    /**
     * 检查用户是否在线（3 分钟内有请求）。
     */
    public boolean isUserOnline(Long userId) {
        try {
            Double score = stringRedisTemplate.opsForZSet()
                    .score(ONLINE_USERS_KEY, userId.toString());
            if (score == null) return false;
            return System.currentTimeMillis() - score.longValue() < OFFLINE_THRESHOLD_MS;
        } catch (Exception e) {
            log.warn("检查用户在线状态失败: userId={}, err={}", userId, e.getMessage());
            return false;
        }
    }
}
