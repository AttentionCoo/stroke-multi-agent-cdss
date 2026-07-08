package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.mapper.InitialPageMapper;
import com.it.po.uo.Cont;
import com.it.po.vo.InitialPageVO;
import com.it.pojo.Talk;
import com.it.service.IContService;
import com.it.service.IInitialPageService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

@Service
@Transactional
@RequiredArgsConstructor
@Slf4j
public class InitialPageServiceImpl extends ServiceImpl<InitialPageMapper, Talk> implements IInitialPageService {

    private final StringRedisTemplate stringRedisTemplate;
    private final IContService contService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final String TALK_LIST_PREFIX = "talk:list:";
    private static final long TALK_LIST_TTL_MINUTES = 5;

    @Override
    public List<InitialPageVO> getPage(Long userId) {
        String cacheKey = TALK_LIST_PREFIX + userId;

        // 尝试从 Redis 读取
        try {
            String cached = stringRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null && !cached.isEmpty()) {
                log.debug("对话列表缓存命中: userId={}", userId);
                List<InitialPageVO> cachedList = objectMapper.readValue(cached,
                        new TypeReference<List<InitialPageVO>>() {});
                return cachedList;
            }
        } catch (Exception e) {
            log.warn("读取对话列表缓存失败，降级查询DB: userId={}, err={}", userId, e.getMessage());
        }

        // 查询数据库
        List<Talk> talks = this.lambdaQuery()
                .eq(Talk::getUserId, userId)
                .orderByDesc(Talk::getUpdateTime)
                .list();

        List<InitialPageVO> result = talks.stream()
                .map(talk -> new InitialPageVO(talk.getId(), talk.getTitle()))
                .collect(Collectors.toList());

        // 写入 Redis 缓存
        try {
            stringRedisTemplate.opsForValue().set(cacheKey, objectMapper.writeValueAsString(result),
                    TALK_LIST_TTL_MINUTES, TimeUnit.MINUTES);
            log.debug("对话列表缓存已写入: userId={}, size={}", userId, result.size());
        } catch (Exception e) {
            log.warn("写入对话列表缓存失败: userId={}, err={}", userId, e.getMessage());
        }

        return result;
    }

    @Override
    @Transactional
    public void deleteTalk(Long userId, Long talkId) {
        // 1. 验证权限：确保这个对话属于当前用户
        Talk talk = this.getById(talkId);
        if (talk == null || !talk.getUserId().equals(userId)) {
            throw new RuntimeException("无权删除此对话");
        }

        // 2. 删除 Redis 缓存（聊天历史、流缓存、对话列表）
        try {
            String historyKey = "chat:history:" + userId + ":" + talkId;
            String streamKey = "chat:stream:" + userId + ":" + talkId;
            stringRedisTemplate.delete(historyKey);
            stringRedisTemplate.delete(streamKey);
            // 清除对话列表缓存
            stringRedisTemplate.delete(TALK_LIST_PREFIX + userId);
            log.info("删除对话缓存: talkId={}, keys=[{}, {}, {}]", talkId, historyKey, streamKey, TALK_LIST_PREFIX + userId);
        } catch (Exception e) {
            log.warn("删除缓存失败: talkId={}, err={}", talkId, e.getMessage());
        }

        // 3. 删除对话内容（Cont 表）
        LambdaQueryWrapper<Cont> contWrapper = new LambdaQueryWrapper<>();
        contWrapper.eq(Cont::getUserId, userId)
                .eq(Cont::getTalkId, talkId);

        int contDeleted = contService.remove(contWrapper) ? 1 : 0;
        log.info("删除对话内容: talkId={}, 删除条数={}", talkId, contDeleted);

        // 4. 删除对话记录（Talk 表）
        LambdaQueryWrapper<Talk> talkWrapper = new LambdaQueryWrapper<>();
        talkWrapper.eq(Talk::getUserId, userId)
                .eq(Talk::getId, talkId);

        boolean talkDeleted = this.remove(talkWrapper);
        log.info("删除对话记录: talkId={}, 结果={}", talkId, talkDeleted);

        if (!talkDeleted) {
            throw new RuntimeException("删除对话失败");
        }
    }
}
