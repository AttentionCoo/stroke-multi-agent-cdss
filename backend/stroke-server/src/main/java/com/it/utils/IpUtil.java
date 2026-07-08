package com.it.utils;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.net.InetAddress;
import java.net.UnknownHostException;

public class IpUtil {

    /**
     * 更严格的 getIp 实现：
     * - 仅在请求来自可信代理时才信任 X-Forwarded-For
     * - 处理回环地址和 IPv6 ::1
     * - 过滤空/unknown，尽量返回可用 IP
     */
    public static String getIp() {
        ServletRequestAttributes attributes =
                (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();

        if (attributes == null) {
            return "unknown";
        }

        HttpServletRequest request = attributes.getRequest();

        String remoteAddr = request.getRemoteAddr();
        if (remoteAddr == null || remoteAddr.isEmpty()) {
            remoteAddr = "unknown";
        }

        boolean trustedProxy = isTrustedProxy(remoteAddr);

        String ip = null;

        if (trustedProxy) {
            String forwarded = request.getHeader("X-Forwarded-For");
            if (forwarded != null && !forwarded.isBlank() && !"unknown".equalsIgnoreCase(forwarded)) {
                // X-Forwarded-For 可能为：client, proxy1, proxy2
                String first = forwarded.split(",")[0].trim();
                if (!first.isEmpty() && !"unknown".equalsIgnoreCase(first)) {
                    ip = first;
                }
            }
        }

        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = remoteAddr;
        }

        if ("0:0:0:0:0:0:0:1".equals(ip) || "::1".equals(ip)) {
            ip = "127.0.0.1";
        }

        // 防止返回私网/loopback 被滥用时返回空
        if (ip == null || ip.isEmpty()) {
            return "unknown";
        }

        // 保证返回一个合法的字符串（不抛异常）
        try {
            InetAddress.getByName(ip);
        } catch (UnknownHostException e) {
            return "unknown";
        }

        return ip;
    }

    private static boolean isTrustedProxy(String remoteAddr) {
        if (remoteAddr == null) return false;
        // 常见的内网/代理段判断（可按需扩展）
        return remoteAddr.startsWith("127.")
                || remoteAddr.startsWith("10.")
                || remoteAddr.startsWith("192.168.")
                || remoteAddr.startsWith("172.")
                || remoteAddr.equals("unknown");
    }
}