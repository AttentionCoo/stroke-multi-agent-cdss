package com.it.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.bean.copier.CopyOptions;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.mapper.RegiMapper;
import com.it.po.dto.UserDTO;
import com.it.po.uo.User;
import com.it.pojo.Result;
import com.it.service.AIStreamingService;
import com.it.utils.IpUtil;
import com.it.utils.JWT;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RateIntervalUnit;
import org.redisson.api.RateType;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
@Transactional
public class RegiServiceImpl extends ServiceImpl<RegiMapper, User> implements com.it.service.IRegiService {

    private final StringRedisTemplate stringRedisTemplate;
    private final BCryptPasswordEncoder passwordEncoder;
    private final RedissonClient redissonClient;
    private final AIStreamingService aiStreamingService; // 新增注入

    /**
     * 使用 redisson 的 rate limiter 尝试获取许可
     */
    private boolean tryAcquire(String key, int rate, int seconds) {
        var limiter = redissonClient.getRateLimiter(key);
        limiter.trySetRate(RateType.OVERALL, rate, seconds, RateIntervalUnit.SECONDS);
        return limiter.tryAcquire();
    }

    /**
     * 原子 incr + expire 脚本
     */
    private Long incrWithExpire(String key, long expireSeconds) {
        String script = "local v = redis.call('incr', KEYS[1]); " +
                "if tonumber(v) == 1 then redis.call('expire', KEYS[1], ARGV[1]); end; return v;";
        DefaultRedisScript<Long> redisScript = new DefaultRedisScript<>(script, Long.class);
        try {
            return stringRedisTemplate.execute(redisScript, Collections.singletonList(key), String.valueOf(expireSeconds));
        } catch (Exception e) {
            log.error("执行 incrWithExpire 失败: key={}, err={}", key, e.getMessage(), e);
            return null;
        }
    }

    @Override
    public Result insertUser(User u) {
        String username = u.getName();
        String ip = IpUtil.getIp();
        String registerKey = "register:limit:" + ip;

        Long count = incrWithExpire(registerKey, 600);
        if (count != null && count > 3) {
            return Result.error("注册过于频繁，请稍后再试");
        }

        log.info("用户注册请求: username={}, ip={}", username, ip);

        if (StrUtil.isBlank(username) || StrUtil.isBlank(u.getPassword())) {
            return Result.error("用户名或密码不能为空");
        }

        try {
            boolean globalRateLimit = tryAcquire("regi:rate:global", 200, 1);
            if (!globalRateLimit) {
                log.warn("全局限流触发: key=regi:rate:global");
                return Result.error("系统繁忙");
            }

            boolean ipRateLimit = tryAcquire("regi:rate:ip:" + ip, 30, 60);
            if (!ipRateLimit) {
                log.warn("IP 限流触发: ip={}", ip);
                return Result.error("IP请求过于频繁");
            }

            boolean userRateLimit = tryAcquire("regi:rate:user:" + username, 3, 60);
            if (!userRateLimit) {
                log.warn("用户限流触发: username={}", username);
                return Result.error("操作过于频繁");
            }
        } catch (Exception e) {
            log.error("限流逻辑异常: {}", e.getMessage(), e);
            return Result.error("系统异常，请稍后再试");
        }

        // 默认头像
        String defaultImagePath = "/images/default.png";
        if (StrUtil.isBlank(u.getImage())) {
            u.setImage(defaultImagePath);
        }

        // 密码加密
        try {
            String raw = u.getPassword();
            String encoded = passwordEncoder.encode(raw);
            u.setPassword(encoded);
        } catch (Exception e) {
            log.error("密码加密失败", e);
            return Result.error("系统异常，请稍后再试");
        }

        try {
            User exist = query().eq("name", username).one();
            if (exist != null) {
                log.warn("用户名已存在: username={}", username);
                return Result.error("用户名已存在");
            }

            // 让数据库自动填充时间（若你的表/实体支持）
            u.setCreateTime(null);
            u.setUpdateTime(null);

            boolean saved = save(u);
            if (!saved) {
                log.error("用户注册失败: username={}", username);
                return Result.error("注册失败");
            }

            // 注册成功，删除限流 key（避免后续被误锁）
            stringRedisTemplate.delete(registerKey);

            // 缓存 user（备用）
            String userCacheKey = "cache:user:" + username;
            stringRedisTemplate.opsForValue().set(userCacheKey, JSONUtil.toJsonStr(u), 30, TimeUnit.MINUTES);

            // 获取插入后回写的 id
            Long newId = u.getId();
            log.info("用户注册成功: username={}, id={}", username, newId);

            // 新增：在注册时创建默认对话
            Long defaultTalkId = aiStreamingService.createNewTalk(newId);
            log.info("注册时创建默认对话: userId={}, talkId={}", newId, defaultTalkId);

            // 生成 jti 并保存在 login:user:<id> 供后续会话管理使用（3天）
            String jti = UUID.randomUUID().toString();
            String loginKey = "login:user:" + newId;
            stringRedisTemplate.opsForValue().set(loginKey, jti, 3, TimeUnit.DAYS);

            // 生成 JWT（包括 id、name、jti）
            Map<String, Object> claims = new HashMap<>();
            claims.put("id", newId);
            claims.put("name", username);
            claims.put("jti", jti);
            String token = JWT.generateToken(claims);

            // 将 user DTO 转为 map，并以 hash 存入 redis，key = user:token:<token>
            UserDTO userDTO = BeanUtil.copyProperties(u, UserDTO.class);
            Map<String, Object> userMap = BeanUtil.beanToMap(userDTO, new HashMap<>(),
                    new CopyOptions()
                            .setIgnoreNullValue(true)
                            .setFieldValueEditor((fieldName, fieldValue) -> fieldValue == null ? null : fieldValue.toString())
            );

            String tokenKey = "user:token:" + token;
            if (!userMap.isEmpty()) {
                stringRedisTemplate.opsForHash().putAll(tokenKey, userMap);
                stringRedisTemplate.expire(tokenKey, 120, TimeUnit.MINUTES);
            }

            // 直接返回 token、userId 和 talkId 给前端
            Map<String, Object> resp = new HashMap<>();
            resp.put("token", token);
            resp.put("userId", newId);
            resp.put("talkId", defaultTalkId); // 新增返回 talkId
            return Result.success(resp);
        } catch (Exception e) {
            log.error("注册异常: username={}, error={}", username, e.getMessage(), e);
            throw e;
        }
    }
}