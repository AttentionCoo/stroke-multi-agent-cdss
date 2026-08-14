package com.it;

import com.it.cache.OnlineUserTracker;
import com.it.service.impl.AIStreamingServiceImpl;
import org.junit.jupiter.api.Test;
import org.redisson.api.RedissonClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class StrokeServerApplicationTests {

    @MockitoBean
    private RedissonClient redissonClient;

    @MockitoBean
    private StringRedisTemplate stringRedisTemplate;

    @MockitoBean
    private AIStreamingServiceImpl aiStreamingService;

    @MockitoBean
    private OnlineUserTracker onlineUserTracker;

    @Test
    void contextLoads() {
    }

}
