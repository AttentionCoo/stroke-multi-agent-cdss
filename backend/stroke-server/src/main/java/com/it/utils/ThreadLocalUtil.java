package com.it.utils;

import com.it.po.uo.User; // 请根据你项目中 User 类的实际包名调整
// 如果你的 User 类并非在 com.it.po.uo 下，请替换为正确的 import

public class ThreadLocalUtil {

    // 存当前用户对象（登录后由你的鉴权逻辑放入）
    private static final ThreadLocal<User> USER_LOCAL = new ThreadLocal<>();

    // 存当前请求的 IP（由拦截器放入）
    private static final ThreadLocal<String> IP_LOCAL = new ThreadLocal<>();

    /**
     * 注意：这里使用 Object 类型以避免因你的 User 类包名不同导致编译问题，
     * 在项目中如果确定 User 类型，建议改成具体类型，例如 private static final ThreadLocal<User> USER_LOCAL
     */
    public static void setCurrentUser(User user) {
        USER_LOCAL.set(user);
    }

    public static User getCurrentUser() {
        return USER_LOCAL.get();
    }

    public static void removeCurrentUser() {
        USER_LOCAL.remove();
    }

    public static void setCurrentIp(String ip) {
        IP_LOCAL.set(ip);
    }

    public static String getCurrentIp() {
        return IP_LOCAL.get();
    }

    public static void removeCurrentIp() {
        IP_LOCAL.remove();
    }
}