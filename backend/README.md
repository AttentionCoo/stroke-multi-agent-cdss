# MyServer - AI 智能对话系统

## 📖 项目简介

MyServer 是一个基于 **Spring Boot 3** 构建的高性能 AI 对话后端服务。项目集成了当下流行的 AI 大模型接口，提供**流式对话 (Streaming)** 体验，并配套了完善的用户鉴权与会话管理系统。

不仅实现了类似 ChatGPT 的打字机回复效果，还在后端架构上引入了**响应式编程 (WebClient + Flux)**、**Redisson 分布式限流**、**双重拦截器鉴权**以及**单设备登录互斥**等企业级特性。

## 🛠️ 技术栈 (Tech Stack)

### 核心框架
- **后端框架**: Spring Boot 3.x (Java 17+)
- **ORM 框架**: MyBatis-Plus
- **响应式编程**: Project Reactor (Flux/Mono), Spring WebFlux Client
- **工具库**: Hutool, Lombok, Jackson

### 中间件与存储
- **数据库**: MySQL 8.0
- **缓存/会话**: Redis (StringRedisTemplate)
- **分布式组件**: Redisson (用于分布式锁、信号量限流)
- **连接池**: HikariCP

## 🚀 核心亮点 (Highlights)

### 1. 响应式 AI 流式对话
核心业务采用 `WebClient` + `Flux` 实现全异步非阻塞的流式响应，支持高并发下的实时 AI 回复。
- **并发控制**: 集成 Redisson `RSemaphore` 实现全局并发量控制，防止 AI 服务过载。
- **异步持久化**: 采用 `ConversationPersistenceService` 异步线程池策略，将对话记录入库与 AI 回复流分离，确保回复无延迟。
- **多级缓存**: 这里的对话上下文 (Context) 支持 Redis 短期缓存，减少数据库查询压力。

### 2. 企业级鉴权体系
- **双重拦截器机制**:
  - `RefreshTokenInterceptor`: 负责全局 Token 自动续期。只要用户活跃，Redis 中的 Token 有效期会自动延长，实现**无感保活**。
  - `TokenInterceptor`: 负责具体的权限校验与路径放行。
- **单设备登录 (Single Sign-On like)**:
  - 登录时生成唯一 `JTI` (JWT ID) 并存入 Redis。
  - 每次请求校验 JTI，一旦用户在通过新设备登录，旧设备的 Token 会因 JTI 不匹配或被主动清理而失效，实现**踢人下线**功能。
- **ThreadLocal 上下文隔离**: 请求链路中通过 `ThreadLocal` 传递用户信息，Controller 层无需从参数解析用户 ID。

### 3. 高性能架构设计
- **Redis 会话管理**: 使用 Redis Hash 结构存储用户信息，String 结构存储 JTI，实现快速鉴权。
- **防止缓存穿透**: 关键高频查询（如用户信息、对话历史）均有缓存策略。
- **优雅停机**: 支持 Spring Boot Graceful Shutdown，保障正在处理流式请求的完整性。

## 📂 核心业务流程

### 用户登录与鉴权
1. **登录**: 验证通过后，生成 JWT 与 JTI。
2. **互斥**: 清理该用户在 Redis 中的旧 Token，设置新 JTI。
3. **缓存**: 将 UserDTO 存入 `user:token:{token}`，设置 TTL (如 30 分钟)。
4. **请求**: 拦截器校验 -> 自动续期 TTL -> 存入 ThreadLocal -> 业务处理 -> 销毁 ThreadLocal。

### AI 对话流
1. **用户提问**: 前端发起 SSE 或流式请求。
2. **限流检查**: Redisson 信号量获取许可。
3. **构建上下文**: 从 Redis/MySQL 获取最近 N 条历史记录。
4. **请求模型**: 通过 WebClient 调用 AI 模型 API。
5. **流式回传**: 收到 Chunk 数据即刻推送到前端。
6. **异步入库**: 对话结束时，异步任务将完整问答落库 MySQL。

## 🔧 快速开始

### 1. 环境准备
- MySQL 8.0+
- Redis 6.0+
- JDK 17+

### 2. 配置文件
修改 `src/main/resources/application.yml`:
```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/ai_db?serverTimezone=Asia/Shanghai
    username: root
    password: your_password
  data:
    redis:
      host: localhost
      port: 6379
```

### 3. 运行
```bash
mvn clean spring-boot:run
```

## 📝 目录结构
```
com.it
├── config          # 配置类 (Redisson, WebClient, MVC等)
├── controller      # 控制层 (处理 HTTP 请求)
├── handler         # 全局异常处理
├── interceptor     # 拦截器 (Token 校验与刷新)
├── mapper          # MyBatis Mapper 接口
├── po              # 持久化对象 (MySQL 实体)
├── service         # 业务逻辑层 (核心业务)
│   ├── impl
│   │   ├── AIStreamingServiceImpl.java  # AI 流式处理核心
│   │   ├── LoginServiceImpl.java        # 登录与 Token 管理
│   │   └── ConversationPersistenceService.java # 异步持久化
├── utils           # 工具类 (JWT, ThreadLocal, Result)
└── MyServerApplication.java # 启动类
