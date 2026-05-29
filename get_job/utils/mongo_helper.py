"""
MongoDB 工具模块
提供 MongoDB 连接和数据存储操作功能，使用 .env 文件管理数据库配置。
Cookie 缓存已迁移到 redis_helper.py，本模块只负责数据存储。
"""

import os
import logging

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

# MongoDB 配置
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGODB_DATABASE", "job_analysis")

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


def get_collection(collection_name: str):
    """获取集合实例"""
    db = get_database()
    return db[collection_name]


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

        # 测试数据读写
        test_item = {"job_id": "test_001", "job_title": "测试职位", "company_name": "测试公司"}
        save_item_to_mongo(test_item, MONGO_JOB_COLLECTION, unique_key="job_id")
        results = query_items_from_mongo(MONGO_JOB_COLLECTION, {"job_id": "test_001"})
        print(f"查询结果: {results}")

        # 清理测试数据
        db[MONGO_JOB_COLLECTION].delete_many({"job_id": "test_001"})
        print("测试数据已清理")
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        close_mongo_client()
