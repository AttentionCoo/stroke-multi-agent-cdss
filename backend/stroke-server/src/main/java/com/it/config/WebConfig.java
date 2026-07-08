package com.it.config;

import com.it.interceptor.RedisRateLimiterInterceptor;
import com.it.interceptor.RefreshTokenInterceptor;
import com.it.interceptor.Tokeninterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@RequiredArgsConstructor
public class WebConfig implements WebMvcConfigurer {

    private final StringRedisTemplate stringRedisTemplate;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // ⭐ 第一步：RedisRateLimiterInterceptor 全局限流（order=0），最先执行
        registry.addInterceptor(new RedisRateLimiterInterceptor(stringRedisTemplate,
                        200, 1,
                        30, 60,
                        3, 60))
                .addPathPatterns("/**")
                .excludePathPatterns(
                        "/api/monitor/**",
                        "/error",
                        "/actuator/**"
                )
                .order(0);

        // ⭐ 第二步：RefreshTokenInterceptor 处理单点登录 / Token 校验（order=1）
        registry.addInterceptor(new RefreshTokenInterceptor(stringRedisTemplate))
                .addPathPatterns("/**")
                .excludePathPatterns(
                        "/api/user/login",
                        "/api/user/register",
                        "/api/user/upload/**",
                        "/error",
                        "/api/monitor/**"
                )
                .order(1);

        // ⭐ 第三步：Tokeninterceptor 检查 ThreadLocal 中是否有用户（order=2）
        registry.addInterceptor(new Tokeninterceptor())
                .addPathPatterns("/**")
                .excludePathPatterns(
                        "/api/user/login",
                        "/api/user/register",
                        "/api/user/upload/**",
                        "/error",
                        "/api/monitor/**"
                )
                .order(2);
    }
}
