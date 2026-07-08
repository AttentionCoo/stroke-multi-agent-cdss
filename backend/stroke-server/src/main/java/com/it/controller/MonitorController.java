package com.it.controller;

import com.it.cache.OnlineUserTracker;
import com.it.pojo.Result;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api/monitor")
@RequiredArgsConstructor
@Slf4j
public class MonitorController {

    private final StringRedisTemplate stringRedisTemplate;
    private final OnlineUserTracker onlineUserTracker;

    @GetMapping("/rate-limit/status")
    public Result getRateLimitStatus() {
        Map<String, Object> status = new HashMap<>();

        try {
            // 获取失败次数
            String failureCountStr = stringRedisTemplate.opsForValue().get("login:failure:count");
            long failureCount = failureCountStr != null ? Long.parseLong(failureCountStr) : 0;

            // 获取成功次数
            String successCountStr = stringRedisTemplate.opsForValue().get("login:success:count");
            long successCount = successCountStr != null ? Long.parseLong(successCountStr) : 0;

            // 获取熔断器状态
            String circuitBreakerState = stringRedisTemplate.opsForValue().get("login:circuit:breaker");
            if (circuitBreakerState == null) {
                circuitBreakerState = "closed";
            }

            // 计算失败率
            long totalRequests = failureCount + successCount;
            double failureRate = totalRequests > 0 ? (double) failureCount / totalRequests * 100 : 0;

            status.put("failureCount", failureCount);
            status.put("successCount", successCount);
            status.put("totalRequests", totalRequests);
            status.put("failureRate", String.format("%.2f%%", failureRate));
            status.put("circuitBreakerState", circuitBreakerState);

            return Result.success(status);
        } catch (Exception e) {
            log.error("获取限流状态异常", e);
            return Result.error("获取状态失败");
        }
    }

    @GetMapping("/rate-limit/reset")
    public Result resetRateLimit() {
        try {
            // 清除所有计数器
            stringRedisTemplate.delete("login:failure:count");
            stringRedisTemplate.delete("login:success:count");
            stringRedisTemplate.delete("login:circuit:breaker");
            stringRedisTemplate.delete("login:circuit:half:open:time");
            stringRedisTemplate.delete("login:failure:window");
            stringRedisTemplate.delete("login:response:time:success");
            stringRedisTemplate.delete("login:response:time:failure");

            return Result.success("重置成功");
        } catch (Exception e) {
            log.error("重置限流状态异常", e);
            return Result.error("重置失败");
        }
    }

    /** 获取在线用户统计 */
    @GetMapping("/online-users")
    public Result getOnlineUsers() {
        try {
            long count = onlineUserTracker.getOnlineUserCount();
            Set<String> userIds = onlineUserTracker.getOnlineUserIds();

            Map<String, Object> data = new HashMap<>();
            data.put("onlineCount", count);
            data.put("userIds", userIds);
            return Result.success(data);
        } catch (Exception e) {
            log.error("获取在线用户统计异常", e);
            return Result.error("获取失败");
        }
    }

    /** 获取 Redis 缓存统计信息 */
    @GetMapping("/cache/stats")
    public Result getCacheStats() {
        try {
            Map<String, Object> stats = new HashMap<>();

            // 统计各类缓存 key 数量
            stats.put("patientPageKeys", countKeys("patient:page:*"));
            stats.put("patientDetailKeys", countKeys("patient:detail:*"));
            stats.put("materialPageKeys", countKeys("material:page:*"));
            stats.put("materialDetailKeys", countKeys("material:detail:*"));
            stats.put("talkListKeys", countKeys("talk:list:*"));
            stats.put("chatHistoryKeys", countKeys("chat:history:*"));
            stats.put("userCacheKeys", countKeys("cache:user:*"));
            stats.put("userInfoCacheKeys", countKeys("cache:userinfo:*"));
            stats.put("userSessionKeys", countKeys("user:token:*"));
            stats.put("tokenBlacklistKeys", countKeys("token:blacklist:*"));
            stats.put("persistRetryQueueSize",
                    stringRedisTemplate.opsForList().size("persist:retry:queue"));
            stats.put("onlineUsers", onlineUserTracker.getOnlineUserCount());

            return Result.success(stats);
        } catch (Exception e) {
            log.error("获取缓存统计异常", e);
            return Result.error("获取失败");
        }
    }

    /** 刷新所有业务缓存（清除后下次请求重新加载） */
    @PostMapping("/cache/refresh")
    public Result refreshAllCaches() {
        try {
            deleteKeysByPattern("patient:page:*");
            deleteKeysByPattern("patient:detail:*");
            deleteKeysByPattern("material:page:*");
            deleteKeysByPattern("material:detail:*");
            deleteKeysByPattern("talk:list:*");
            deleteKeysByPattern("oss:documents:*");
            deleteKeysByPattern("cache:user:*");
            deleteKeysByPattern("cache:userinfo:*");
            log.info("所有业务缓存已刷新");
            return Result.success("所有业务缓存已刷新");
        } catch (Exception e) {
            log.error("刷新缓存异常", e);
            return Result.error("刷新失败");
        }
    }

    /** 清除持久化重试队列 */
    @PostMapping("/cache/clear-retry-queue")
    public Result clearRetryQueue() {
        try {
            stringRedisTemplate.delete("persist:retry:queue");
            log.info("持久化重试队列已清除");
            return Result.success("持久化重试队列已清除");
        } catch (Exception e) {
            log.error("清除重试队列异常", e);
            return Result.error("清除失败");
        }
    }

    private long countKeys(String pattern) {
        try {
            var keys = stringRedisTemplate.keys(pattern);
            return keys != null ? keys.size() : 0;
        } catch (Exception e) {
            return 0;
        }
    }

    private void deleteKeysByPattern(String pattern) {
        try {
            var keys = stringRedisTemplate.keys(pattern);
            if (keys != null && !keys.isEmpty()) {
                stringRedisTemplate.delete(keys);
            }
        } catch (Exception e) {
            log.warn("删除缓存失败: pattern={}, err={}", pattern, e.getMessage());
        }
    }
}
