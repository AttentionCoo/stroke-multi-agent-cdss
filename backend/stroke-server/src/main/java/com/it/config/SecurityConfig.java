package com.it.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.Arrays;
import java.util.List;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Value("${app.cors.allowed-origins:http://localhost,http://localhost:5173,http://127.0.0.1:5173}")
    private String allowedOrigins;

    @Bean
    public BCryptPasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            // 1. 禁用 CSRF（前后端分离 + JWT 无需 CSRF 保护）
            .csrf(csrf -> csrf.disable())
            // 2. 让 Spring Security 使用我们的 CORS 配置（必须在 Spring Security 层放行 OPTIONS 预检）
            .cors(cors -> cors.configurationSource(corsConfigurationSource()))
            // 3. 无状态 Session（JWT 鉴权，不依赖 HttpSession）
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // 4. 路由放行规则
            //    - 登录/注册/退出：完全放行，无需任何 Token
            //    - 其余接口：Spring Security 层放行，由 MVC 拦截器（Tokeninterceptor）做真正的 JWT 鉴权
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/api/user/login",
                    "/api/user/register",
                    "/api/user/logOut",
                    "/api/user/upload/**",
                    "/error"
                ).permitAll()
                .anyRequest().permitAll()
            );
        return http.build();
    }

    /**
     * CORS 全局配置 —— 必须注册到 Spring Security 过滤器链，
     * 否则跨域预检（OPTIONS）会在到达 MVC 层之前被 Security 拦截并返回 401/403。
     */
    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(Arrays.stream(allowedOrigins.split(","))
                .map(String::trim)
                .filter(origin -> !origin.isEmpty())
                .toList());
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        // 预检结果缓存 1 小时，减少 OPTIONS 请求
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
