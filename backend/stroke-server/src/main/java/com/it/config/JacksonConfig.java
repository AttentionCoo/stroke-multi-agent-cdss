package com.it.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import tools.jackson.databind.module.SimpleModule;
import tools.jackson.databind.ser.std.ToStringSerializer;

@Configuration
public class JacksonConfig {

    /**
     * Jackson 2 ObjectMapper(供服务层注入: 评估快照/FHIR 等序列化)。
     * 注意: Spring Boot 4 的 REST 消息转换器使用 Jackson 3(tools.jackson),
     * 此 bean 不影响 REST 输出, 仅作为可注入的通用 Jackson 2 实例。
     */
    @Bean
    public ObjectMapper jacksonObjectMapper() {
        ObjectMapper om = new ObjectMapper();
        om.registerModule(new JavaTimeModule());
        om.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return om;
    }

    /**
     * REST 层全局 Long → String 序列化(作用于 Boot 4 自动配置的 Jackson 3 JsonMapper)。
     *
     * 雪花 ID(对话/患者/评估等)约 2.08e18, 超出 JavaScript Number.MAX_SAFE_INTEGER(2^53-1)。
     * 若以 JSON 数字返回, 浏览器 JSON.parse 会丢失精度(如 2088471000008830978 变 2088471000008831000),
     * 导致前端携带错误 ID 请求历史/删除接口 —— 表现为"刷新后问答消失"。
     * 统一序列化为字符串后精度无损, 前端均已按字符串处理。
     */
    @Bean
    public JsonMapperBuilderCustomizer longToStringCustomizer() {
        SimpleModule longToString = new SimpleModule("longToString");
        longToString.addSerializer(Long.class, ToStringSerializer.instance);
        longToString.addSerializer(Long.TYPE, ToStringSerializer.instance);
        return builder -> builder.addModule(longToString);
    }
}
