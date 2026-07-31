package com.it.domain.consultation;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.regex.Pattern;

@Component
public class QuestionScopeGuard {

    private static final String SCOPE_MESSAGE =
            "该问题与脑卒中临床诊疗无关。请提供患者症状、发病时间、影像或检验结果，"
                    + "或询问脑卒中评估与处置问题。";

    private static final Pattern STROKE_CLINICAL_PATTERN = Pattern.compile(
            "卒中|中风|脑梗|脑出血|蛛网膜下腔|短暂性脑缺血|\\bTIA\\b|\\bstroke\\b|"
                    + "NIHSS|ASPECTS|溶栓|取栓|血栓|偏瘫|偏身|口角歪斜|失语|言语不清|"
                    + "突发.{0,8}(无力|麻木|视物不清|复视|头痛|眩晕|意识障碍)|"
                    + "颅脑|头颅|大脑中动脉|颈动脉|椎基底动脉|CTA|DWI|"
                    + "阿替普酶|替奈普酶|尿激酶|抗血小板|抗凝|房颤",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
    );

    private static final Pattern NON_CLINICAL_TASK_PATTERN = Pattern.compile(
            "Python|JavaScript|编程|代码|程序开发|爬虫|算法题|写.{0,8}(作文|诗|歌词)|"
                    + "翻译.{0,8}(文章|小说|歌词)",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
    );

    private static final Pattern DAILY_TOPIC_PATTERN = Pattern.compile(
            "天气|气温|股票|基金|彩票|足球|篮球|比赛比分|电影|电视剧|游戏攻略|"
                    + "旅游攻略|酒店推荐|餐厅推荐|菜谱|星座|笑话|新闻摘要|几点了|星期几|"
                    + "\\b(weather|stock|lottery|football|basketball|movie|game|travel|hotel|"
                    + "restaurant|recipe|horoscope|joke)\\b",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
    );

    private static final Pattern GREETING_ONLY_PATTERN = Pattern.compile(
            "^((你好|您好|嗨|hello|hi)[，,。.!！?？\\s]*)?"
                    + "(你是谁|你能做什么|介绍一下自己)?[，,。.!！?？\\s]*$",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
    );

    public Decision inspect(String question, List<String> images) {
        String normalized = question == null ? "" : question.trim();
        if (normalized.isEmpty()) {
            if (images != null && !images.isEmpty()) {
                return Decision.allow();
            }
            return Decision.reject("EMPTY_QUESTION", "请输入脑卒中临床问题，或上传需要分析的医学影像。");
        }

        if (NON_CLINICAL_TASK_PATTERN.matcher(normalized).find()) {
            return Decision.reject("NON_CLINICAL_TASK", SCOPE_MESSAGE);
        }
        if (STROKE_CLINICAL_PATTERN.matcher(normalized).find()) {
            return Decision.allow();
        }
        if (DAILY_TOPIC_PATTERN.matcher(normalized).find()
                || GREETING_ONLY_PATTERN.matcher(normalized).matches()) {
            return Decision.reject("OUT_OF_SCOPE", SCOPE_MESSAGE);
        }

        // 边界不明确的症状描述继续交给现有模型意图节点判断，避免误拦截临床信息。
        return Decision.allow();
    }

    public record Decision(boolean allowed, String reasonCode, String message) {

        private static Decision allow() {
            return new Decision(true, "", "");
        }

        private static Decision reject(String reasonCode, String message) {
            return new Decision(false, reasonCode, message);
        }
    }
}
