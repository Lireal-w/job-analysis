"""
MongoDB 工具模块
提供 MongoDB 连接和操作功能，使用 .env 文件管理数据库配置。
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

# MongoDB 配置
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGODB_DATABASE", "job_analysis")
MONGO_COOKIE_COLLECTION = os.getenv("MONGODB_COOKIE_COLLECTION", "cookies")
COOKIE_EXPIRE_SECONDS = int(os.getenv("COOKIE_EXPIRE_SECONDS", "86400"))

# 数据存储集合
MONGO_JOB_COLLECTION = os.getenv("MONGODB_JOB_COLLECTION", "jobs")
MONGO_COMPANY_COLLECTION = os.getenv("MONGODB_COMPANY_COLLECTION", "companies")

# 全局 MongoDB 客户端（单例模式）
_client = None
_db = None


def get_mongo_client() -> MongoClient:
    """获取 MongoDB 客户端（单例）"""
    global _client
    if _client is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            # 测试连接
            _client.admin.command("ping")
            logger.info(f"MongoDB 连接成功: {MONGO_URI}")
        except ConnectionFailure as e:
            logger.error(f"MongoDB 连接失败: {e}")
            raise
    return _client


def get_database():
    """获取数据库实例"""
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[MONGO_DATABASE]
        logger.info(f"使用数据库: {MONGO_DATABASE}")
    return _db


def get_collection(collection_name: str = None):
    """获取集合实例"""
    db = get_database()
    collection_name = collection_name or MONGO_COOKIE_COLLECTION
    return db[collection_name]


# ==========================================
# Cookie 缓存操作
# ==========================================

COOKIE_DOC_ID = "xiaoyuan_zhaopin"


def save_cookies_to_mongo(cookies: dict, site: str = None) -> bool:
    """
    保存 Cookie 到 MongoDB

    Args:
        cookies: Cookie 字典
        site: 站点标识，默认为 "xiaoyuan_zhaopin"

    Returns:
        bool: 是否保存成功
    """
    site = site or COOKIE_DOC_ID
    try:
        collection = get_collection()
        doc = {
            "_id": site,
            "cookies": cookies,
            "updated_at": datetime.now(timezone.utc),
            "cookie_count": len(cookies),
        }
        collection.update_one(
            {"_id": site},
            {"$set": doc},
            upsert=True,
        )
        logger.info(f"Cookie 已保存到 MongoDB（站点: {site}, 数量: {len(cookies)}）")
        return True
    except OperationFailure as e:
        logger.error(f"保存 Cookie 到 MongoDB 失败: {e}")
        return False
    except Exception as e:
        logger.error(f"保存 Cookie 发生未知错误: {e}")
        return False


def load_cookies_from_mongo(site: str = None, check_expire: bool = True) -> dict:
    """
    从 MongoDB 加载 Cookie

    Args:
        site: 站点标识，默认为 "xiaoyuan_zhaopin"
        check_expire: 是否检查过期时间

    Returns:
        dict: Cookie 字典，如果不存在或已过期则返回空字典
    """
    site = site or COOKIE_DOC_ID
    try:
        collection = get_collection()
        doc = collection.find_one({"_id": site})

        if not doc:
            logger.info(f"MongoDB 中未找到 Cookie（站点: {site}）")
            return {}

        # 检查过期时间
        if check_expire:
            updated_at = doc.get("updated_at")
            if updated_at:
                elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
                if elapsed > COOKIE_EXPIRE_SECONDS:
                    logger.info(
                        f"Cookie 已过期（站点: {site}, "
                        f"已过 {int(elapsed)}秒 / 过期阈值 {COOKIE_EXPIRE_SECONDS}秒）"
                    )
                    return {}

        cookies = doc.get("cookies", {})
        if cookies:
            logger.info(f"从 MongoDB 加载了 {len(cookies)} 个 Cookie（站点: {site}）")
        return cookies

    except ConnectionFailure as e:
        logger.error(f"MongoDB 连接失败，无法加载 Cookie: {e}")
        return {}
    except Exception as e:
        logger.error(f"加载 Cookie 发生未知错误: {e}")
        return {}


def delete_cookies_from_mongo(site: str = None) -> bool:
    """
    从 MongoDB 删除 Cookie

    Args:
        site: 站点标识

    Returns:
        bool: 是否删除成功
    """
    site = site or COOKIE_DOC_ID
    try:
        collection = get_collection()
        result = collection.delete_one({"_id": site})
        if result.deleted_count > 0:
            logger.info(f"Cookie 已从 MongoDB 删除（站点: {site}）")
            return True
        else:
            logger.info(f"MongoDB 中未找到需要删除的 Cookie（站点: {site}）")
            return False
    except Exception as e:
        logger.error(f"删除 Cookie 失败: {e}")
        return False


# ==========================================
# 通用数据存储操作
# ==========================================

def save_item_to_mongo(item: dict, collection_name: str, unique_key: str = None) -> bool:
    """
    保存单条数据到 MongoDB

    Args:
        item: 数据字典
        collection_name: 集合名称
        unique_key: 唯一键字段名（如 "job_id"），如果提供则按该字段去重 upsert

    Returns:
        bool: 是否保存成功
    """
    try:
        collection = get_collection(collection_name)
        if unique_key and unique_key in item:
            collection.update_one(
                {unique_key: item[unique_key]},
                {"$set": item},
                upsert=True,
            )
            logger.debug(f"数据已保存到 MongoDB（集合: {collection_name}, {unique_key}: {item[unique_key]}）")
        else:
            collection.insert_one(item)
            logger.debug(f"数据已插入 MongoDB（集合: {collection_name}）")
        return True
    except OperationFailure as e:
        logger.error(f"保存数据到 MongoDB 失败（集合: {collection_name}）: {e}")
        return False
    except Exception as e:
        logger.error(f"保存数据发生未知错误（集合: {collection_name}）: {e}")
        return False


def save_items_to_mongo(items: list, collection_name: str, unique_key: str = None) -> int:
    """
    批量保存数据到 MongoDB

    Args:
        items: 数据字典列表
        collection_name: 集合名称
        unique_key: 唯一键字段名，如果提供则按该字段去重 upsert

    Returns:
        int: 成功保存的数量
    """
    if not items:
        return 0

    success_count = 0
    try:
        collection = get_collection(collection_name)

        if unique_key:
            # 逐条 upsert（保证去重）
            for item in items:
                if unique_key in item:
                    try:
                        collection.update_one(
                            {unique_key: item[unique_key]},
                            {"$set": item},
                            upsert=True,
                        )
                        success_count += 1
                    except Exception as e:
                        logger.error(f"批量保存单条数据失败: {e}")
                else:
                    try:
                        collection.insert_one(item)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"批量插入单条数据失败: {e}")
        else:
            # 无唯一键，批量插入
            try:
                result = collection.insert_many(items, ordered=False)
                success_count = len(result.inserted_ids)
            except Exception as e:
                logger.error(f"批量插入数据失败: {e}")

        logger.info(f"批量保存数据到 MongoDB（集合: {collection_name}, 成功: {success_count}/{len(items)}）")
        return success_count

    except Exception as e:
        logger.error(f"批量保存数据发生未知错误（集合: {collection_name}）: {e}")
        return success_count


def query_items_from_mongo(
    collection_name: str,
    filter_dict: dict = None,
    projection: dict = None,
    limit: int = 0,
    sort: list = None,
) -> list:
    """
    从 MongoDB 查询数据

    Args:
        collection_name: 集合名称
        filter_dict: 查询条件
        projection: 返回字段投影
        limit: 返回数量限制（0 表示不限制）
        sort: 排序规则，如 [("crawl_time", -1)]

    Returns:
        list: 查询结果列表
    """
    try:
        collection = get_collection(collection_name)
        cursor = collection.find(filter_dict or {}, projection)

        if sort:
            cursor = cursor.sort(sort)
        if limit > 0:
            cursor = cursor.limit(limit)

        results = list(cursor)
        logger.info(f"从 MongoDB 查询到 {len(results)} 条数据（集合: {collection_name}）")
        return results

    except Exception as e:
        logger.error(f"查询数据失败（集合: {collection_name}）: {e}")
        return []


def get_collection_count(collection_name: str, filter_dict: dict = None) -> int:
    """
    获取集合中的文档数量

    Args:
        collection_name: 集合名称
        filter_dict: 查询条件

    Returns:
        int: 文档数量
    """
    try:
        collection = get_collection(collection_name)
        return collection.count_documents(filter_dict or {})
    except Exception as e:
        logger.error(f"获取文档数量失败（集合: {collection_name}）: {e}")
        return 0


def close_mongo_client():
    """关闭 MongoDB 客户端连接"""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB 连接已关闭")


if __name__ == "__main__":
    # 测试 MongoDB 连接
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        client = get_mongo_client()
        db = get_database()
        collections = db.list_collection_names()
        print(f"数据库 {MONGO_DATABASE} 中的集合: {collections}")

        # 测试 Cookie 读写
        test_cookies = {"test_key": "test_value", "session_id": "abc123"}
        save_cookies_to_mongo(test_cookies)
        loaded = load_cookies_from_mongo()
        print(f"加载的 Cookie: {loaded}")

        # 清理测试数据
        delete_cookies_from_mongo()
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        close_mongo_client()
