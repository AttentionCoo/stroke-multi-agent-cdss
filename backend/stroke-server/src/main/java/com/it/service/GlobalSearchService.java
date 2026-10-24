package com.it.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.it.mapper.LearningMaterialMapper;
import com.it.mapper.PatientMapper;
import com.it.mapper.TalkMapper;
import com.it.pojo.LearningMaterial;
import com.it.pojo.Patient;
import com.it.pojo.Talk;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 全局搜索：患者、历史对话和医学资料。 */
@Service
@RequiredArgsConstructor
public class GlobalSearchService {

    private final PatientMapper patientMapper;
    private final TalkMapper talkMapper;
    private final LearningMaterialMapper learningMaterialMapper;

    public List<Map<String, Object>> search(Long doctorId, String query) {
        if (!StringUtils.hasText(query)) return List.of();
        String q = query.trim();
        List<Map<String, Object>> results = new ArrayList<>();

        patientMapper.selectList(new LambdaQueryWrapper<Patient>()
                        .eq(Patient::getDoctorId, doctorId)
                        .and(w -> w.like(Patient::getName, q).or().like(Patient::getHistory, q)
                                .or().like(Patient::getNotes, q))
                        .orderByDesc(Patient::getUpdateTime)
                        .last("LIMIT 8"))
                .forEach(item -> results.add(result(
                        "patient", item.getId(), item.getName(),
                        StringUtils.hasText(item.getHistory()) ? item.getHistory() : "患者档案",
                        item.getUpdateTime(), "/patients/" + item.getId())));

        talkMapper.selectList(new LambdaQueryWrapper<Talk>()
                        .eq(Talk::getUserId, doctorId)
                        .like(Talk::getTitle, q)
                        .orderByDesc(Talk::getUpdateTime)
                        .last("LIMIT 8"))
                .forEach(item -> results.add(result(
                        "talk", item.getId(),
                        StringUtils.hasText(item.getTitle()) ? item.getTitle() : "历史对话",
                        "AI 问诊对话", item.getUpdateTime(), "/chat/" + item.getId())));

        learningMaterialMapper.selectList(new LambdaQueryWrapper<LearningMaterial>()
                        .and(w -> w.like(LearningMaterial::getTitle, q)
                                .or().like(LearningMaterial::getCategory, q)
                                .or().like(LearningMaterial::getContent, q))
                        .orderByDesc(LearningMaterial::getUpdateTime)
                        .last("LIMIT 8"))
                .forEach(item -> results.add(result(
                        "knowledge", item.getId(), item.getTitle(),
                        StringUtils.hasText(item.getCategory()) ? item.getCategory() : "医学资料",
                        item.getUpdateTime(), "/learning/" + item.getId())));

        return results;
    }

    private Map<String, Object> result(String type, Long id, String title, String subtitle,
                                       Object time, String path) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("type", type);
        row.put("id", id);
        row.put("title", title);
        row.put("subtitle", subtitle);
        row.put("time", time);
        row.put("path", path);
        return row;
    }
}
