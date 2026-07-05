package com.it.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.bean.copier.CopyOptions;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.mapper.LoginMapper;
import com.it.po.dto.UserDTO;
import com.it.po.uo.LoginInfo;
import com.it.po.uo.User;
import com.it.pojo.Result;
import com.it.service.ILoginService;
import com.it.utils.IpUtil;
import com.it.utils.JWT;
import com.it.utils.ThreadLocalUtil;
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
public class LoginServiceImpl extends ServiceImpl<LoginMapper, User> implements ILoginService {

    // ===== 登录限流参数 =====
    private static final int MAX_IP_ATTEMPTS = 5;        // 单IP最大次数
    private static final int MAX_USER_ATTEMPTS = 5;      // 单账号最大次数
    private static final int WINDOW_SECONDS = 300;       // 5分钟窗口
    private final StringRedisTemplate stringRedisTemplate;
    private final RedissonClient redissonClient;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    private boolean tryAcquire(String key, int rate, int seconds) {
        var limiter = redissonClient.getRateLimiter(key);
        limiter.trySetRate(RateType.OVERALL, rate, seconds, RateIntervalUnit.SECONDS);
        return limiter.tryAcquire();
    }

    // 原子 incr + expire
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
    public Result loginInto(User u) {
        String username = u.getName();
        if (StrUtil.isBlank(username) || StrUtil.isBlank(u.getPassword())) {
            return Result.error("用户名或密码不能为空");
        }

        String ip = IpUtil.getIp();

        String ipKey = "login:limit:ip:" + ip;
        String userKey = "login:limit:user:" + username;
        String comboKey = "login:limit:combo:" + ip + ":" + username;

        Long ipCount = incrWithExpire(ipKey, WINDOW_SECONDS);
        if (ipCount != null && ipCount > MAX_IP_ATTEMPTS) {
            return Result.error("IP登录过于频繁，请5分钟后再试");
        }

        Long userCount = incrWithExpire(userKey, WINDOW_SECONDS);
        if (userCount != null && userCount > MAX_USER_ATTEMPTS) {
            return Result.error("账号登录过于频繁，请5分钟后再试");
        }

        Long comboCount = incrWithExpire(comboKey, WINDOW_SECONDS);
        if (comboCount != null && comboCount > MAX_USER_ATTEMPTS) {
            return Result.error("检测到异常登录行为，请稍后再试");
        }

        // Redisson 速率限流
        boolean globalRateLimit = tryAcquire("login:rate:global", 100, 1);
        if (!globalRateLimit) {
            return Result.error("系统繁忙");
        }

        boolean ipRateLimit = tryAcquire("login:rate:ip:" + ip, 20, 60);
        if (!ipRateLimit) {
            return Result.error("IP请求过于频繁");
        }

        boolean userRateLimit = tryAcquire("login:rate:user:" + username, 5, 10);
        if (!userRateLimit) {
            return Result.error("操作过于频繁");
        }

        try {
            // 查询用户信息（先查 Redis 缓存）
            String userCacheKey = "cache:user:" + username;
            String userJson = stringRedisTemplate.opsForValue().get(userCacheKey);

            User dbUser = StrUtil.isNotBlank(userJson)
                    ? JSONUtil.toBean(userJson, User.class)
                    : query().eq("name", username).one();

            if (dbUser == null) {
                return Result.error("用户不存在或密码错误");
            }

            String dbPassword = dbUser.getPassword();
            String inputPassword = u.getPassword();

            boolean matched = false;
            if (dbPassword != null && dbPassword.startsWith("$2a$") || (dbPassword != null && dbPassword.startsWith("$2b$"))) {
                // bcrypt 存储
                matched = passwordEncoder.matches(inputPassword, dbPassword);
            } else {
                // 兼容明文旧数据：如果明文匹配则把密码升级为 bcrypt
                if (dbPassword != null && dbPassword.equals(inputPassword)) {
                    matched = true;
                    try {
                        String newHash = passwordEncoder.encode(inputPassword);
                        dbUser.setPassword(newHash);
                        updateById(dbUser); // 更新数据库中的加密密码
                        // 刷新缓存
                        stringRedisTemplate.opsForValue().set(userCacheKey, JSONUtil.toJsonStr(dbUser), 30, TimeUnit.MINUTES);
                    } catch (Exception e) {
                        log.warn("密码升级为 bcrypt 失败: {}", e.getMessage());
                    }
                } else {
                    matched = false;
                }
            }

            if (!matched) {
                return Result.error("用户不存在或密码错误");
            }

            // 登录成功后再删除限流记录（避免前述问题）
            stringRedisTemplate.delete(ipKey);
            stringRedisTemplate.delete(userKey);
            stringRedisTemplate.delete(comboKey);

            // 生成 JTI 并存入 Redis
            String jti = UUID.randomUUID().toString();
            String loginKey = "login:user:" + dbUser.getId();
            stringRedisTemplate.opsForValue().set(loginKey, jti, 3, TimeUnit.DAYS);
            log.info("用户 {} 登录，生成 JTI: {}", dbUser.getId(), jti);

            Map<String, Object> claims = new HashMap<>();
            claims.put("id", dbUser.getId());
            claims.put("name", dbUser.getName());
            claims.put("jti", jti);
            String token = JWT.generateToken(claims);

            // 存 token -> user 映射供拦截器使用
            UserDTO userDTO = BeanUtil.copyProperties(dbUser, UserDTO.class);
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

            ThreadLocalUtil.setCurrentUser(userDTO);

            return Result.success(new LoginInfo(dbUser.getName(), dbUser.getImage(), token));

        } catch (Exception e) {
            log.error("登录异常: ", e);
            return Result.error("登录失败，请重试");
        }
    }

    @Override
    public Result logOut(String token) {
        if (token == null || token.isEmpty()) return Result.error("Token为空");
        if (token.startsWith("Bearer ")) token = token.substring(7);

        try {
            Long userId = JWT.getUserIdFromToken(token);

            // 将当前 Token 的 JTI 加入黑名单，TTL 设为 3 天（与 JWT 过期时间一致）
            String jti = JWT.getJtiFromToken(token);
            if (jti != null) {
                stringRedisTemplate.opsForValue().set(
                        "token:blacklist:" + jti, "1", 3, TimeUnit.DAYS);
                log.info("Token JTI 已加入黑名单: userId={}, jti={}", userId, jti);
            }

            // 清除登录记录和会话
            stringRedisTemplate.delete("login:user:" + userId);
            stringRedisTemplate.delete("user:token:" + token);
            // 清除在线用户状态
            stringRedisTemplate.opsForZSet().remove("online:users", userId.toString());
            // 清除用户对话列表缓存
            stringRedisTemplate.delete("talk:list:" + userId);
            ThreadLocalUtil.removeCurrentUser();
            log.info("用户已退出登录: userId={}", userId);
        } catch (Exception e) {
            log.error("注销异常", e);
        }
        return Result.success("退出成功");
    }
}