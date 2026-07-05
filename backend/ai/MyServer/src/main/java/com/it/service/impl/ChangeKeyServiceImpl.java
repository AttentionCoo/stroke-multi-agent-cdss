package com.it.service.impl;

import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.it.pojo.ChangeKey;
import com.it.pojo.Result;
import com.it.mapper.ChangeKeyMapper;
import com.it.po.uo.User;
import com.it.service.IChangeKeyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Transactional
@Slf4j
public class ChangeKeyServiceImpl extends ServiceImpl<ChangeKeyMapper, User> implements IChangeKeyService {

    private final StringRedisTemplate stringRedisTemplate;

    private static final String USER_INFO_PREFIX = "cache:userinfo:";
    private static final String USER_CACHE_PREFIX = "cache:user:";
    private static final long USER_CACHE_TTL_MINUTES = 30;

    @Override
    public Result changeKeyById(Long currentId, ChangeKey changeKey) {
        // 检查密码修改限制
        String password = stringRedisTemplate.opsForValue().get("user:password:" + currentId);
        if (password != null) {
            return Result.success("密码已修改,三十天内不能重复修改");
        }
        User user = query().eq("id", currentId).one();
        if (user == null) {
            return Result.error("用户不存在");
        }
        if (user.getPassword().equals(changeKey.getPrePassword())) {
            user.setPassword(changeKey.getNewPassword());
            user.setUpdateTime(LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
            updateById(user);

            // 更新密码修改限制（30天）
            stringRedisTemplate.opsForValue().set("user:password:" + currentId, changeKey.getNewPassword(), 30, TimeUnit.DAYS);

            // 清除用户相关缓存，确保下次读取时拿到最新数据
            evictUserCaches(currentId, user.getName());

            return Result.success("密码修改成功");
        } else {
            return Result.error("密码错误");
        }
    }

    @Override
    public Result getUserInfo(Long currentId) {
        String cacheKey = USER_INFO_PREFIX + currentId;

        // 尝试从 Redis 读取用户信息缓存
        try {
            String cached = stringRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("用户信息缓存命中: userId={}", currentId);
                User cachedUser = JSONUtil.toBean(cached, User.class);
                // 脱敏：不返回密码
                cachedUser.setPassword(null);
                return Result.success(cachedUser);
            }
        } catch (Exception e) {
            log.warn("读取用户信息缓存失败，降级查询DB: userId={}, err={}", currentId, e.getMessage());
        }

        // 缓存未命中，查询数据库
        User user = query().eq("id", currentId).one();
        if (user != null) {
            // 写入缓存
            try {
                stringRedisTemplate.opsForValue().set(cacheKey, JSONUtil.toJsonStr(user),
                        USER_CACHE_TTL_MINUTES, TimeUnit.MINUTES);
                // 同时更新按用户名索引的缓存
                stringRedisTemplate.opsForValue().set(USER_CACHE_PREFIX + user.getName(), JSONUtil.toJsonStr(user),
                        USER_CACHE_TTL_MINUTES, TimeUnit.MINUTES);
                log.debug("用户信息缓存已写入: userId={}", currentId);
            } catch (Exception e) {
                log.warn("写入用户信息缓存失败: userId={}, err={}", currentId, e.getMessage());
            }
            // 脱敏返回
            user.setPassword(null);
        }
        return Result.success(user);
    }

    /** 清除用户所有缓存 */
    private void evictUserCaches(Long userId, String username) {
        try {
            stringRedisTemplate.delete(USER_INFO_PREFIX + userId);
            stringRedisTemplate.delete(USER_CACHE_PREFIX + username);
            stringRedisTemplate.delete("talk:list:" + userId);
            log.debug("已清除用户缓存: userId={}, username={}", userId, username);
        } catch (Exception e) {
            log.warn("清除用户缓存失败: userId={}, err={}", userId, e.getMessage());
        }
    }
}
