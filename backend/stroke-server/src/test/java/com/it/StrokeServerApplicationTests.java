package com.it;

import com.it.cache.OnlineUserTracker;
import com.it.service.impl.AIStreamingServiceImpl;
import org.junit.jupiter.api.Test;
import org.redisson.api.RedissonClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class StrokeServerApplicationTests {

    @MockBean
    private RedissonClient redissonClient;

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private AIStreamingServiceImpl aiStreamingService;

    @MockBean
    private OnlineUserTracker onlineUserTracker;

    @Test
    void contextLoads() {
    }

}
