package com.it.config;

import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.impl.LaissezFaireSubTypeValidator;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.time.Duration;

/**
 * Redis 缓存配置 —— 启用 Spring Cache 抽象。
 *
 * <p>不同业务域使用不同的 TTL 策略：
 * <ul>
 *   <li><b>patient</b> — 患者数据，10 分钟（数据更新频率低，但需要较快反映变更）</li>
 *   <li><b>material</b> — 学习资料，30 分钟（静态内容，几乎不变）</li>
 *   <li><b>talk</b> — 对话列表，5 分钟（频繁增删）</li>
 *   <li><b>oss</b> — OSS 文档列表，30 分钟（文档库不频繁变动）</li>
 *   <li><b>user</b> — 用户信息，30 分钟</li>
 *   <li><b>default</b> — 默认，10 分钟</li>
 * </ul>
 */
@Configuration
@EnableCaching
public class RedisCacheConfig {

    /**
     * 构造带类型的 JSON 序列化器，确保反序列化时能正确还原泛型对象。
     */
    private ObjectMapper cacheObjectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.activateDefaultTyping(
                LaissezFaireSubTypeValidator.instance,
                ObjectMapper.DefaultTyping.NON_FINAL,
                JsonTypeInfo.As.PROPERTY
        );
        return mapper;
    }

    private RedisCacheConfiguration baseConfig(Duration ttl) {
        return RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(ttl)
                .serializeKeysWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(new StringRedisSerializer()))
                .serializeValuesWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(
                                new GenericJackson2JsonRedisSerializer(cacheObjectMapper())))
                .disableCachingNullValues();
    }

    @Bean
    public RedisCacheManagerBuilderCustomizer redisCacheManagerBuilderCustomizer() {
        return builder -> builder
                .cacheDefaults(baseConfig(Duration.ofMinutes(10)))
                .withCacheConfiguration("patient",    baseConfig(Duration.ofMinutes(10)))
                .withCacheConfiguration("material",   baseConfig(Duration.ofMinutes(30)))
                .withCacheConfiguration("talk",       baseConfig(Duration.ofMinutes(5)))
                .withCacheConfiguration("oss",        baseConfig(Duration.ofMinutes(30)))
                .withCacheConfiguration("user",       baseConfig(Duration.ofMinutes(30)));
    }
}
