package com.it.config;

import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RedissonConfig {

    @Value("${spring.data.redis.host}")
    private String redisHost;

    @Value("${spring.data.redis.port}")
    private String redisPort;

    @Value("${spring.data.redis.password:}")
    private String redisPassword;

    @Bean(destroyMethod = "shutdown")
    public RedissonClient redissonClient() {

        Config config = new Config();
        String redisAddress = "redis://" + redisHost + ":" + redisPort;

        var single = config.useSingleServer()
                .setAddress(redisAddress)
                .setDatabase(0);

        if (redisPassword != null && !redisPassword.isBlank()) {
            single.setPassword(redisPassword);
        }

        return Redisson.create(config);
    }
}