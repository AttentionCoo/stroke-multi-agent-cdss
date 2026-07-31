package com.it.domain.consultation;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class QuestionScopeGuardTest {

    private final QuestionScopeGuard guard = new QuestionScopeGuard();

    @Test
    void allowsStrokeClinicalQuestions() {
        assertTrue(guard.inspect("患者突发右侧肢体无力，NIHSS 8分，是否适合静脉溶栓？", List.of()).allowed());
        assertTrue(guard.inspect("Acute stroke thrombectomy window", List.of()).allowed());
    }

    @Test
    void allowsImageQuestionsAndUncertainSymptomsForSemanticRouting() {
        assertTrue(guard.inspect("请分析这张影像", List.of("data:image/png;base64,AA==")).allowed());
        assertTrue(guard.inspect("", List.of("data:image/png;base64,AA==")).allowed());
        assertTrue(guard.inspect("患者昨晚突然不舒服，现在应该怎么办？", List.of()).allowed());
    }

    @Test
    void blocksClearlyUnrelatedQuestionsBeforeModelInference() {
        assertFalse(guard.inspect("明天北京天气怎么样？", List.of()).allowed());
        assertFalse(guard.inspect("What is the weather tomorrow?", List.of("data:image/png;base64,AA==")).allowed());
        assertFalse(guard.inspect("帮我写一段 Python 爬虫代码", List.of()).allowed());
        assertFalse(guard.inspect("你好，你是谁？", List.of()).allowed());
    }

    @Test
    void blocksEmptyQuestionsWithoutImages() {
        assertFalse(guard.inspect("  ", List.of()).allowed());
    }
}
