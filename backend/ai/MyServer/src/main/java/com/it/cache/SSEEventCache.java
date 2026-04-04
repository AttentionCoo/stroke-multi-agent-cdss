package com.it.cache;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * SSE 断线续传事件缓存。
 *
 * <p>为每个 talkId 维护一个 Reactor replay sink，同时承担两个职责：
 * <ol>
 *   <li>为当次连接的每条事件分配单调递增序列号（seq），注入 SSE id 字段（格式 talkId:seq）</li>
 *   <li>客户端重连时，通过 seq 过滤出未收到的事件进行回放，
 *       若原始流仍在推送则自动续接直播</li>
 * </ol>
 *
 * <p>缓存生命周期：流结束（done/error）后保留 {@code ai.sse.cache-ttl-minutes} 分钟，
 * 供客户端在此窗口内重连恢复。窗口过期后由 {@link #cleanExpired()} 定期清理。
 */
@Slf4j
@Component
public class SSEEventCache {

    /** 携带序列号的事件包装，重连时按 seq 过滤已收到的事件 */
    public record SequencedEvent(long seq, String data) {}

    /** 每个 talkId 的滑动窗口事件数上限，超出后最旧的事件被淘汰 */
    @Value("${ai.sse.ring-buffer-size:200}")
    private int ringBufferSize;

    /** done/error 后缓存保留时长（分钟），给重连留出窗口 */
    @Value("${ai.sse.cache-ttl-minutes:5}")
    private long cacheTtlMinutes;

    // talkId → replay sink（流结束后保留 ttl 分钟，供重连回放）
    private final ConcurrentHashMap<String, Sinks.Many<SequencedEvent>> sinks = new ConcurrentHashMap<>();
    // talkId → 单调递增序列号（从 1 开始）
    private final ConcurrentHashMap<String, AtomicLong> seqCounters = new ConcurrentHashMap<>();
    // talkId → 过期时刻 epoch ms（completeStream 写入，cleanExpired 读取）
    private final ConcurrentHashMap<String, Long> expiryTimes = new ConcurrentHashMap<>();

    /**
     * 新流开始前调用，创建并注册 replay sink 和 seq 计数器。
     *
     * @param talkId 对话 ID（字符串形式，作为缓存 key）
     */
    public void registerStream(String talkId) {
        Sinks.Many<SequencedEvent> existing = sinks.get(talkId);
        if (existing != null) {
            try {
                existing.tryEmitComplete();
            } catch (Exception e) {
                // ignore exception when emitting complete
            }
            long expiryMs = System.currentTimeMillis() + cacheTtlMinutes * 60_000L;
            expiryTimes.put(talkId, expiryMs);
            seqCounters.remove(talkId);
            log.debug("替换已有 SSE sink，并设置旧 sink 的过期时间: talkId={}, expiresInMin={}", talkId, cacheTtlMinutes);
        }

        Sinks.Many<SequencedEvent> sink = Sinks.many().replay().limit(ringBufferSize);
        sinks.put(talkId, sink);
        seqCounters.put(talkId, new AtomicLong(0));
        log.debug("已注册 SSE 事件缓存: talkId={}, ringBufferSize={}", talkId, ringBufferSize);
    }

    /**
     * 缓存一条事件并分配序列号。
     *
     * @param talkId 对话 ID
     * @param data   原始 JSON 字符串事件
     * @return 分配的序列号（1-based）；若 talkId 未注册则返回 -1
     */
    public long addEvent(String talkId, String data) {
        AtomicLong counter = seqCounters.get(talkId);
        if (counter == null) return -1;
        long seq = counter.incrementAndGet();
        Sinks.Many<SequencedEvent> sink = sinks.get(talkId);
        if (sink != null) {
            if (data != null && data.length() > 200_000) {
                log.warn("SSE 事件过大，跳过写入缓存以保护内存: length={}, talkId={}", data.length(), talkId);
            } else {
                sink.tryEmitNext(new SequencedEvent(seq, data));
            }
        }
        return seq;
    }

    /**
     * 流结束（正常 done 或 error 恢复后）时调用：
     * <ol>
     *   <li>complete sink，通知所有订阅者（含正在等待的重连客户端）流已结束</li>
     *   <li>记录过期时刻，{@link #cleanExpired()} 到期后释放内存</li>
     * </ol>
     *
     * @param talkId 对话 ID
     */
    public void completeStream(String talkId) {
        Sinks.Many<SequencedEvent> sink = sinks.get(talkId);
        if (sink != null) {
            sink.tryEmitComplete();
        }
        long expiryMs = System.currentTimeMillis() + cacheTtlMinutes * 60_000L;
        expiryTimes.put(talkId, expiryMs);
        log.debug("SSE 流已完成，缓存将在 {} 分钟后过期: talkId={}", cacheTtlMinutes, talkId);
    }

    /**
     * 获取重连回放流，返回 seq > lastSeq 的所有事件（历史回放 + 后续实时推送）。
     *
     * @param talkId  对话 ID
     * @param lastSeq 客户端最后收到的事件序列号（来自 Last-Event-ID header）
     * @return {@code null} 表示缓存不存在或已过期，应向客户端返回 E2003；
     *         否则返回包含历史回放和后续直播的 Flux
     */
    public Flux<SequencedEvent> getReplayStream(String talkId, long lastSeq) {
        Sinks.Many<SequencedEvent> sink = sinks.get(talkId);
        if (sink == null) return null; // 缓存已过期或从未注册
        return sink.asFlux().filter(se -> se.seq() > lastSeq);
    }

    /**
     * 每分钟扫描一次，清理已超过 ttl 的 talkId 缓存，释放 sink 和计数器占用的内存。
     */
    @Scheduled(fixedDelay = 60_000)
    public void cleanExpired() {
        long now = System.currentTimeMillis();
        expiryTimes.entrySet().removeIf(entry -> {
            if (entry.getValue() <= now) {
                String tid = entry.getKey();
                sinks.remove(tid);
                seqCounters.remove(tid);
                log.debug("已清理过期 SSE 事件缓存: talkId={}", tid);
                return true;
            }
            return false;
        });
    }
}
