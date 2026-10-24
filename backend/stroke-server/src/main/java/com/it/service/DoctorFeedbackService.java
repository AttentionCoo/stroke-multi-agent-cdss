package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.DoctorFeedbackMapper;
import com.it.mapper.TalkMapper;
import com.it.po.uo.DoctorFeedbackParam;
import com.it.pojo.DoctorFeedback;
import com.it.pojo.Talk;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/** 医生对 AI 回答的反馈入库与聚合统计。 */
@Service
@RequiredArgsConstructor
@Slf4j
public class DoctorFeedbackService {

    private final DoctorFeedbackMapper feedbackMapper;
    private final TalkMapper talkMapper;

    @Transactional
    public DoctorFeedback submit(Long doctorId, DoctorFeedbackParam param) {
        if (param == null || param.getTalkId() == null) {
            throw new IllegalArgumentException("talkId 不能为空");
        }
        if (param.getRating() == null || (param.getRating() != 1 && param.getRating() != -1)) {
            throw new IllegalArgumentException("rating 只能为 1 或 -1");
        }
        Talk talk = talkMapper.selectById(param.getTalkId());
        if (talk == null || !doctorId.equals(talk.getUserId())) {
            throw new IllegalArgumentException("对话不存在或无权限");
        }

        DoctorFeedback feedback = new DoctorFeedback();
        feedback.setDoctorId(doctorId);
        feedback.setTalkId(param.getTalkId());
        feedback.setRating(param.getRating());
        feedback.setCategory(truncate(param.getCategory(), 64));
        feedback.setComment(truncate(param.getComment(), 1000));
        feedback.setAnswerExcerpt(truncate(param.getAnswerExcerpt(), 4000));
        feedback.setCreateTime(LocalDateTime.now());
        feedbackMapper.insert(feedback);
        log.info("收到医生回答反馈: doctorId={}, talkId={}, rating={}", doctorId, param.getTalkId(), param.getRating());
        return feedback;
    }

    public Map<String, Object> summary(Long doctorId) {
        Long total = feedbackMapper.selectCount(new LambdaQueryWrapper<DoctorFeedback>()
                .eq(DoctorFeedback::getDoctorId, doctorId));
        Long positive = feedbackMapper.selectCount(new LambdaQueryWrapper<DoctorFeedback>()
                .eq(DoctorFeedback::getDoctorId, doctorId)
                .eq(DoctorFeedback::getRating, 1));
        Long negative = feedbackMapper.selectCount(new LambdaQueryWrapper<DoctorFeedback>()
                .eq(DoctorFeedback::getDoctorId, doctorId)
                .eq(DoctorFeedback::getRating, -1));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", total == null ? 0 : total);
        result.put("positive", positive == null ? 0 : positive);
        result.put("negative", negative == null ? 0 : negative);
        result.put("positiveRate", total != null && total > 0
                ? Math.round((positive == null ? 0 : positive) * 1000.0 / total) / 10.0 : 0.0);
        return result;
    }

    private String truncate(String value, int maxLength) {
        if (!StringUtils.hasText(value)) return null;
        String text = value.trim();
        return text.length() <= maxLength ? text : text.substring(0, maxLength);
    }
}
