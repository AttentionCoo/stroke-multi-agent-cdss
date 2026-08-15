package com.it.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.it.po.uo.Cont;
import com.it.pojo.Talk;
import com.it.service.IContService;
import com.it.service.ITalkService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;

@Service
@RequiredArgsConstructor
@Slf4j
@Transactional
public class ConversationPersistenceService {

    private final IContService contService;
    private final ITalkService talkService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public void persistConversation(Long userId, Long talkId, String question, String answer,
                                    String summary, String title, List<String> images,
                                    String thinkingJson) {
        LocalDateTime now = LocalDateTime.now();

        // 将图片列表序列化为 JSON 字符串，无图片时存 null
        String imagesJson = null;
        if (images != null && !images.isEmpty()) {
            try {
                imagesJson = objectMapper.writeValueAsString(images);
            } catch (JsonProcessingException e) {
                log.warn("图片列表序列化失败，将跳过图片存储: talkId={}, err={}", talkId, e.getMessage());
            }
        }

        // 保存用户问题（附带图片）
        Cont userCont = new Cont();
        userCont.setUserId(userId);
        userCont.setTalkId(talkId);
        userCont.setContent(question);
        userCont.setRole("user");
        userCont.setImages(imagesJson);
        userCont.setCreateTime(now);
        contService.save(userCont);

        // 保存AI回答（无图片）
        Cont aiCont = new Cont();
        aiCont.setUserId(userId);
        aiCont.setTalkId(talkId);
        aiCont.setContent(answer);
        aiCont.setRole("assistant");
        aiCont.setImages(null);
        aiCont.setCreateTime(now);
        contService.save(aiCont);

        // 可选：如果有summary，可以保存到另一个字段或单独的Cont，但根据代码兼容，暂不处理

        // 加载历史（可选，用于验证或日志）
        List<Cont> history = contService.list(new LambdaQueryWrapper<Cont>()
                .eq(Cont::getUserId, userId)
                .eq(Cont::getTalkId, talkId)
                .orderByAsc(Cont::getId));

        // 更新Talk
        Talk talk = talkService.getById(talkId);
        if (talk != null) {
            // 只在默认标题时更新
            if ("新对话".equals(talk.getTitle())
                    && title != null
                    && !title.isBlank()) {

                talk.setTitle(title);
                log.info("更新对话标题：talkId={}, title={}", talkId, title);
            }
            // 设置content为answer（或summary，如果有）
            String finalContent = summary != null && !summary.isEmpty() ? summary : answer;
            talk.setContent(finalContent);
            // 追加本轮思考链(节点过程/专家意见/用量)到历史, 供刷新后重新打开思维链
            if (thinkingJson != null && !thinkingJson.isBlank()) {
                talk.setThinkingJson(appendThinkingRound(talk.getThinkingJson(), thinkingJson));
            }
            talk.setUpdateTime(now);
            talkService.updateById(talk);
        } else {
            log.warn("Talk不存在，无法更新: talkId={}", talkId);
        }
        // 清除历史缓存
        String historyKey = "chat:history:" + userId + ":" + talkId;
    }

    /**
     * 把新一轮思考链 JSON 追加到历史数组(历史可能为 null/空/非法 JSON, 全部降级处理)。
     */
    private String appendThinkingRound(String existing, String newRoundJson) {
        try {
            java.util.ArrayList<Object> rounds = new java.util.ArrayList<>();
            if (existing != null && !existing.isBlank()) {
                try {
                    Object parsed = objectMapper.readValue(existing, Object.class);
                    if (parsed instanceof java.util.List<?> list) {
                        rounds.addAll(list);
                    }
                } catch (Exception e) {
                    log.warn("历史思考链 JSON 解析失败, 按空数组处理: {}", e.getMessage());
                }
            }
            rounds.add(objectMapper.readValue(newRoundJson, Object.class));
            // 上限 200 轮, 防止极端情况下字段无限膨胀
            if (rounds.size() > 200) {
                rounds = new java.util.ArrayList<>(rounds.subList(rounds.size() - 200, rounds.size()));
            }
            return objectMapper.writeValueAsString(rounds);
        } catch (Exception e) {
            log.warn("追加思考链失败, 保留原值: {}", e.getMessage());
            return existing;
        }
    }
}