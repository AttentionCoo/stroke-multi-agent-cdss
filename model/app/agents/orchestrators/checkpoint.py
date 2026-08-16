"""LangGraph 检查点持久化(阶段3)。

- CHECKPOINTER_PATH 未配置 → InMemorySaver(单机单元测试/无持久化场景);
- 配置后 → AsyncSqliteSaver, 支撑 HITL 中断/续跑与断点状态落盘;
- 启动期按 TTL 清理过期线程, 避免 sqlite 无限增长。

注意: 普通推理线程在流式结束后由 QwenAgent 主动删除;
只有 HITL 待复核线程保留(等待 /model/resume), 超期后由 prune_stale_threads 兜底清理。
"""

import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 7

# sqlite checkpoint 库的三张表
_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs")

# 持有活跃的 async context manager: 被 GC 会触发生成器清理而关闭 sqlite 连接
_ACTIVE_SAVER_CM = None


def checkpoint_db_path() -> str:
    """解析 CHECKPOINTER_PATH, 确保父目录存在; 未配置返回空串。"""
    path = os.getenv("CHECKPOINTER_PATH", "").strip()
    if not path:
        return ""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def prune_stale_threads(path: str, ttl_days: int = DEFAULT_TTL_DAYS) -> int:
    """清理超过 TTL 未活动的线程检查点, 返回清理数量(失败时静默返回 0)。"""
    if not path or not os.path.exists(path):
        return 0
    cutoff = time.time() - ttl_days * 86400
    try:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "SELECT thread_id, MAX(CAST(json_extract(checkpoint, '$.ts') AS REAL)) AS ts "
                "FROM checkpoints GROUP BY thread_id"
            ).fetchall()
            stale = [r[0] for r in rows if r[1] is None or float(r[1]) < cutoff]
            for tid in stale:
                for table in _TABLES:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
            conn.commit()
            if stale:
                logger.info("🧹 [Checkpoint] 清理 %d 个过期线程(>%d 天)", len(stale), ttl_days)
            return len(stale)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - 清理失败不影响启动
        logger.warning("[Checkpoint] 过期线程清理失败: %s", exc)
        return 0


def build_checkpointer():
    """同步上下文可用的内存检查点(单元测试/无持久化场景)。

    注意: Sqlite 持久化必须用 open_checkpointer()(async), 因为 aiosqlite
    连接绑定创建时的事件循环, 必须在应用主事件循环内创建。
    """
    from langgraph.checkpoint.memory import InMemorySaver
    return InMemorySaver()


async def open_checkpointer():
    """在应用主事件循环内构建检查点存储(优先 Sqlite, 失败回退内存)。"""
    global _ACTIVE_SAVER_CM
    path = checkpoint_db_path()
    if not path:
        logger.info("[Checkpoint] 未配置 CHECKPOINTER_PATH, 使用内存检查点(无持久化)")
        return build_checkpointer()

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        prune_stale_threads(path)
        cm = AsyncSqliteSaver.from_conn_string(path)
        saver = await cm.__aenter__()
        # 全程持有上下文管理器, 防止被 GC 关闭底层 sqlite 连接
        _ACTIVE_SAVER_CM = cm
        logger.info("✅ [Checkpoint] Sqlite 检查点已启用: %s", path)
        return saver
    except Exception as exc:  # noqa: BLE001 - 依赖缺失/文件损坏时不阻塞服务
        logger.warning("[Checkpoint] Sqlite 检查点初始化失败, 回退内存: %s", exc)
        return build_checkpointer()
