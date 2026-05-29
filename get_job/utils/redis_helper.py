"""
Redis 工具模块
提供 Redis 连接和 Cookie 缓存操作功能，使用 .env 文件管理配置。
Cookie 存储使用 Redis Hash，天然支持 TTL 过期。
"""

import os
import json
import logging
from typing import Optional

from dotenv import load_dotenv
import redis

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

# Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") or None
REDIS_DATABASE = int(os.getenv("REDIS_DATABASE", "0"))

# Cookie 缓存配置
COOKIE_KEY_PREFIX = os.getenv("REDIS_COOKIE_KEY_PREFIX", "cookie")
COOKIE_EXPIRE_SECONDS = int(os.getenv("COOKIE_EXPIRE_SECONDS", "86400"))

# 全局 Redis 客户端（单例模式）
_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """获取 Redis 客户端（单例）"""
    global _client
    if _client is None:
        try:
            _client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DATABASE,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # 测试连接
            _client.ping()
            logger.info(f"Redis 连接成功: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DATABASE}")
        except redis.ConnectionError as e:
            logger.error(f"Redis 连接失败: {e}")
            raise
    return _client


# ==========================================
# Cookie 缓存操作
# ==========================================

def _cookie_key(site: str) -> str:
    """生成 Cookie 存储的 Redis Key"""
    return f"{COOKIE_KEY_PREFIX}:{site}"


def save_cookies_to_redis(cookies: dict, site: str = "xiaoyuan_zhaopin") -> bool:
    """
    保存 Cookie 到 Redis

    使用 Redis Hash 存储 Cookie，并设置 TTL 过期时间。

    Args:
        cookies: Cookie 字典
        site: 站点标识，默认为 "xiaoyuan_zhaopin"

    Returns:
        bool: 是否保存成功
    """
    try:
        client = get_redis_client()
        key = _cookie_key(site)

        # 使用 pipeline 保证原子性
        pipe = client.pipeline(transaction=True)
        # 先删除旧数据
        pipe.delete(key)
        if cookies:
            pipe.hset(key, mapping=cookies)
        # 设置过期时间
        pipe.expire(key, COOKIE_EXPIRE_SECONDS)
        pipe.execute()

        logger.info(f"Cookie 已保存到 Redis（站点: {site}, 数量: {len(cookies)}, TTL: {COOKIE_EXPIRE_SECONDS}s）")
        return True
    except redis.RedisError as e:
        logger.error(f"保存 Cookie 到 Redis 失败: {e}")
        return False
    except Exception as e:
        logger.error(f"保存 Cookie 发生未知错误: {e}")
        return False


def load_cookies_from_redis(site: str = "xiaoyuan_zhaopin") -> dict:
    """
    从 Redis 加载 Cookie

    如果 Key 已过期或不存在，返回空字典。
    Redis TTL 机制自动处理过期，无需手动检查。

    Args:
        site: 站点标识，默认为 "xiaoyuan_zhaopin"

    Returns:
        dict: Cookie 字典，如果不存在或已过期则返回空字典
    """
    try:
        client = get_redis_client()
        key = _cookie_key(site)

        # 检查 Key 是否存在
        if not client.exists(key):
            logger.info(f"Redis 中未找到 Cookie（站点: {site}）")
            return {}

        # 获取 Hash 中所有字段
        cookies = client.hgetall(key)

        if cookies:
            ttl = client.ttl(key)
            logger.info(f"从 Redis 加载了 {len(cookies)} 个 Cookie（站点: {site}, 剩余 TTL: {ttl}s）")
        return cookies

    except redis.RedisError as e:
        logger.error(f"从 Redis 加载 Cookie 失败: {e}")
        return {}
    except Exception as e:
        logger.error(f"加载 Cookie 发生未知错误: {e}")
        return {}


def delete_cookies_from_redis(site: str = "xiaoyuan_zhaopin") -> bool:
    """
    从 Redis 删除 Cookie

    Args:
        site: 站点标识

    Returns:
        bool: 是否删除成功
    """
    try:
        client = get_redis_client()
        key = _cookie_key(site)
        result = client.delete(key)
        if result > 0:
            logger.info(f"Cookie 已从 Redis 删除（站点: {site}）")
            return True
        else:
            logger.info(f"Redis 中未找到需要删除的 Cookie（站点: {site}）")
            return False
    except Exception as e:
        logger.error(f"删除 Cookie 失败: {e}")
        return False


def get_cookie_ttl(site: str = "xiaoyuan_zhaopin") -> int:
    """
    获取 Cookie 的剩余 TTL（秒）

    Args:
        site: 站点标识

    Returns:
        int: 剩余秒数，-1 表示 Key 存在但未设置过期，-2 表示 Key 不存在
    """
    try:
        client = get_redis_client()
        key = _cookie_key(site)
        return client.ttl(key)
    except Exception as e:
        logger.error(f"获取 Cookie TTL 失败: {e}")
        return -2


def close_redis_client():
    """关闭 Redis 客户端连接"""
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("Redis 连接已关闭")


if __name__ == "__main__":
    # 测试 Redis 连接
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        client = get_redis_client()
        print(f"Redis 连接成功: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DATABASE}")
        print(f"Redis 服务器信息: {client.info('server').get('redis_version', 'unknown')}")

        # 测试 Cookie 读写
        test_cookies = {"test_key": "test_value", "session_id": "abc123"}
        save_cookies_to_redis(test_cookies)
        loaded = load_cookies_from_redis()
        print(f"加载的 Cookie: {loaded}")

        ttl = get_cookie_ttl()
        print(f"Cookie TTL: {ttl}s")

        # 清理测试数据
        delete_cookies_from_redis()
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        close_redis_client()
