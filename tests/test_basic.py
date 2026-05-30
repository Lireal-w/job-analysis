"""
功能测试模块
测试浏览器池、MongoDB 数据存储、Redis Cookie 缓存等核心功能是否可用。

运行方式：
    # 运行全部测试
    python -m tests.test_basic

    # 运行单个测试
    python -m tests.test_basic TestRedisHelper
    python -m tests.test_basic TestMongoHelper
    python -m tests.test_basic TestBrowserPool
"""

import sys
import os
import time
import unittest
import logging

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class TestRedisHelper(unittest.TestCase):
    """Redis Cookie 缓存功能测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化：建立 Redis 连接"""
        from get_job.utils.redis_helper import get_redis_client
        try:
            cls.client = get_redis_client()
            cls.connected = True
        except Exception as e:
            logger.warning(f"Redis 连接失败，跳过测试: {e}")
            cls.connected = False

    def setUp(self):
        if not self.connected:
            self.skipTest("Redis 不可用")

    def test_01_connection(self):
        """测试 Redis 连接"""
        from get_job.utils.redis_helper import get_redis_client
        client = get_redis_client()
        result = client.ping()
        self.assertTrue(result, "Redis PING 应该返回 True")
        logger.info("✅ Redis 连接测试通过")

    def test_02_save_and_load_cookies(self):
        """测试 Cookie 保存和加载"""
        from get_job.utils.redis_helper import save_cookies_to_redis, load_cookies_from_redis

        test_cookies = {
            "session_id": "test_abc123",
            "user_token": "test_token_xyz",
            "login_status": "1",
        }
        site = "test_site"

        # 保存
        result = save_cookies_to_redis(test_cookies, site=site)
        self.assertTrue(result, "保存 Cookie 应该返回 True")

        # 加载
        loaded = load_cookies_from_redis(site=site)
        self.assertEqual(loaded, test_cookies, "加载的 Cookie 应该与保存的一致")

        # 清理
        from get_job.utils.redis_helper import delete_cookies_from_redis
        delete_cookies_from_redis(site=site)
        logger.info("✅ Cookie 保存和加载测试通过")

    def test_03_cookie_expiry(self):
        """测试 Cookie TTL 过期机制"""
        from get_job.utils.redis_helper import (
            save_cookies_to_redis,
            load_cookies_from_redis,
            get_cookie_ttl,
            delete_cookies_from_redis,
        )

        test_cookies = {"temp_key": "temp_value"}
        site = "test_expire_site"

        # 保存 Cookie
        save_cookies_to_redis(test_cookies, site=site)

        # 检查 TTL
        ttl = get_cookie_ttl(site=site)
        self.assertGreater(ttl, 0, "Cookie TTL 应该大于 0")

        # 删除后检查
        delete_cookies_from_redis(site=site)
        ttl_after = get_cookie_ttl(site=site)
        self.assertEqual(ttl_after, -2, "删除后 TTL 应该返回 -2（Key 不存在）")

        # 加载已删除的 Cookie
        loaded = load_cookies_from_redis(site=site)
        self.assertEqual(loaded, {}, "已删除的 Cookie 应该返回空字典")
        logger.info("✅ Cookie TTL 过期机制测试通过")

    def test_04_empty_cookies(self):
        """测试空 Cookie 处理"""
        from get_job.utils.redis_helper import (
            save_cookies_to_redis,
            load_cookies_from_redis,
            delete_cookies_from_redis,
        )

        site = "test_empty_site"

        # 保存空 Cookie
        result = save_cookies_to_redis({}, site=site)
        self.assertTrue(result, "保存空 Cookie 应该返回 True")

        # 加载空 Cookie
        loaded = load_cookies_from_redis(site=site)
        self.assertEqual(loaded, {}, "空 Cookie 应该返回空字典")

        # 清理
        delete_cookies_from_redis(site=site)
        logger.info("✅ 空 Cookie 处理测试通过")

    def test_05_overwrite_cookies(self):
        """测试 Cookie 覆盖更新"""
        from get_job.utils.redis_helper import (
            save_cookies_to_redis,
            load_cookies_from_redis,
            delete_cookies_from_redis,
        )

        site = "test_overwrite_site"

        # 第一次保存
        cookies_v1 = {"key1": "value1", "key2": "value2"}
        save_cookies_to_redis(cookies_v1, site=site)

        # 第二次保存（覆盖）
        cookies_v2 = {"key1": "new_value1", "key3": "value3"}
        save_cookies_to_redis(cookies_v2, site=site)

        # 加载应该是最新值
        loaded = load_cookies_from_redis(site=site)
        self.assertEqual(loaded, cookies_v2, "Cookie 应该被覆盖为最新值")

        # 清理
        delete_cookies_from_redis(site=site)
        logger.info("✅ Cookie 覆盖更新测试通过")

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls.connected:
            from get_job.utils.redis_helper import close_redis_client
            close_redis_client()


class TestMongoHelper(unittest.TestCase):
    """MongoDB 数据存储功能测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化：建立 MongoDB 连接"""
        from get_job.utils.mongo_helper import get_mongo_client
        try:
            cls.client = get_mongo_client()
            cls.connected = True
        except Exception as e:
            logger.warning(f"MongoDB 连接失败，跳过测试: {e}")
            cls.connected = False

    def setUp(self):
        if not self.connected:
            self.skipTest("MongoDB 不可用")
        self.test_collection = "_test_collection_"

    def test_01_connection(self):
        """测试 MongoDB 连接"""
        from get_job.utils.mongo_helper import get_mongo_client
        client = get_mongo_client()
        result = client.admin.command("ping")
        self.assertEqual(result.get("ok"), 1.0, "MongoDB PING 应该返回 ok=1")
        logger.info("✅ MongoDB 连接测试通过")

    def test_02_save_and_query_item(self):
        """测试单条数据保存和查询"""
        from get_job.utils.mongo_helper import (
            save_item_to_mongo,
            query_items_from_mongo,
            get_collection,
        )

        test_item = {
            "job_id": "test_001",
            "job_title": "测试职位",
            "company_name": "测试公司",
        }

        # 保存
        result = save_item_to_mongo(test_item, self.test_collection, unique_key="job_id")
        self.assertTrue(result, "保存数据应该返回 True")

        # 查询
        results = query_items_from_mongo(
            self.test_collection,
            filter_dict={"job_id": "test_001"},
        )
        self.assertEqual(len(results), 1, "应该查询到 1 条数据")
        self.assertEqual(results[0]["job_title"], "测试职位", "职位名称应该一致")

        # 清理
        get_collection(self.test_collection).delete_many({"job_id": "test_001"})
        logger.info("✅ 单条数据保存和查询测试通过")

    def test_03_upsert_item(self):
        """测试数据去重 upsert"""
        from get_job.utils.mongo_helper import (
            save_item_to_mongo,
            query_items_from_mongo,
            get_collection,
        )

        # 第一次保存
        item_v1 = {"job_id": "test_upsert", "job_title": "版本1"}
        save_item_to_mongo(item_v1, self.test_collection, unique_key="job_id")

        # 第二次保存（相同 job_id，应更新）
        item_v2 = {"job_id": "test_upsert", "job_title": "版本2"}
        save_item_to_mongo(item_v2, self.test_collection, unique_key="job_id")

        # 查询应该只有 1 条，且为最新值
        results = query_items_from_mongo(
            self.test_collection,
            filter_dict={"job_id": "test_upsert"},
        )
        self.assertEqual(len(results), 1, "upsert 后应该只有 1 条数据")
        self.assertEqual(results[0]["job_title"], "版本2", "应该是更新后的值")

        # 清理
        get_collection(self.test_collection).delete_many({"job_id": "test_upsert"})
        logger.info("✅ 数据去重 upsert 测试通过")

    def test_04_batch_save_items(self):
        """测试批量数据保存"""
        from get_job.utils.mongo_helper import (
            save_items_to_mongo,
            get_collection_count,
            get_collection,
        )

        items = [
            {"job_id": f"batch_{i}", "job_title": f"批量测试职位{i}"}
            for i in range(5)
        ]

        # 批量保存
        count = save_items_to_mongo(items, self.test_collection, unique_key="job_id")
        self.assertEqual(count, 5, "应该成功保存 5 条数据")

        # 验证数量
        total = get_collection_count(self.test_collection, {"job_id": {"$regex": "^batch_"}})
        self.assertEqual(total, 5, "集合中应该有 5 条批量测试数据")

        # 清理
        get_collection(self.test_collection).delete_many({"job_id": {"$regex": "^batch_"}})
        logger.info("✅ 批量数据保存测试通过")

    def test_05_collection_count(self):
        """测试集合文档计数"""
        from get_job.utils.mongo_helper import (
            save_item_to_mongo,
            get_collection_count,
            get_collection,
        )

        # 保存几条数据
        for i in range(3):
            save_item_to_mongo(
                {"job_id": f"count_{i}", "index": i},
                self.test_collection,
                unique_key="job_id",
            )

        # 计数
        total = get_collection_count(self.test_collection, {"job_id": {"$regex": "^count_"}})
        self.assertEqual(total, 3, "应该有 3 条数据")

        # 清理
        get_collection(self.test_collection).delete_many({"job_id": {"$regex": "^count_"}})
        logger.info("✅ 集合文档计数测试通过")

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls.connected:
            from get_job.utils.mongo_helper import close_mongo_client
            close_mongo_client()


class TestBrowserPool(unittest.TestCase):
    """浏览器池功能测试"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        try:
            from DrissionPage import ChromiumPage
            cls.drissionpage_available = True
        except ImportError:
            cls.drissionpage_available = False
            logger.warning("DrissionPage 未安装，跳过浏览器池测试")

    def setUp(self):
        if not self.drissionpage_available:
            self.skipTest("DrissionPage 不可用")

    def test_01_create_pool(self):
        """测试浏览器池创建"""
        from get_job.utils.browser_pool import BrowserPool

        pool = BrowserPool(pool_size=2, headless=True)
        self.assertIsNotNone(pool, "浏览器池应该创建成功")
        self.assertEqual(pool.pool_size, 2, "池大小应该为 2")

        pool.shutdown()
        logger.info("✅ 浏览器池创建测试通过")

    def test_02_get_and_release_instance(self):
        """测试获取和归还浏览器实例"""
        from get_job.utils.browser_pool import BrowserPool

        pool = BrowserPool(pool_size=1, headless=True)

        try:
            # 获取实例
            instance = pool.get(timeout=30)
            self.assertIsNotNone(instance, "应该能获取到浏览器实例")
            self.assertIsNotNone(instance.page, "实例应该有 page 属性")
            self.assertTrue(instance.in_use, "实例应该标记为使用中")

            instance_id = instance.instance_id

            # 归还实例
            pool.release(instance)
            self.assertFalse(instance.in_use, "归还后实例应该标记为空闲")

            # 再次获取应该复用同一个实例
            instance2 = pool.get(timeout=30)
            self.assertEqual(instance2.instance_id, instance_id, "应该复用同一个实例")

            pool.release(instance2)
        finally:
            pool.shutdown()
        logger.info("✅ 获取和归还浏览器实例测试通过")

    def test_03_pool_stats(self):
        """测试浏览器池状态统计"""
        from get_job.utils.browser_pool import BrowserPool

        pool = BrowserPool(pool_size=2, headless=True)

        try:
            instance = pool.get(timeout=30)
            self.assertIsNotNone(instance)

            stats = pool.get_stats()
            self.assertIn("total", stats, "统计信息应包含 total")
            self.assertIn("in_use", stats, "统计信息应包含 in_use")
            self.assertIn("idle", stats, "统计信息应包含 idle")
            self.assertGreaterEqual(stats["total"], 1, "总数应该 >= 1")
            self.assertGreaterEqual(stats["in_use"], 1, "使用中应该 >= 1")

            pool.release(instance)
        finally:
            pool.shutdown()
        logger.info("✅ 浏览器池状态统计测试通过")

    def test_04_instance_alive_check(self):
        """测试浏览器实例存活检查"""
        from get_job.utils.browser_pool import BrowserPool

        pool = BrowserPool(pool_size=1, headless=True)

        try:
            instance = pool.get(timeout=30)
            self.assertIsNotNone(instance)

            # 实例应该存活
            self.assertTrue(instance.is_alive(), "刚创建的实例应该存活")

            pool.release(instance)
        finally:
            pool.shutdown()

        # 关闭后实例应该不存活
        self.assertFalse(instance.is_alive(), "关闭后的实例不应该存活")
        logger.info("✅ 浏览器实例存活检查测试通过")

    def test_05_global_pool(self):
        """测试全局浏览器池单例"""
        from get_job.utils.browser_pool import get_browser_pool, shutdown_browser_pool

        try:
            pool1 = get_browser_pool(pool_size=1, headless=True)
            pool2 = get_browser_pool(pool_size=1, headless=True)
            self.assertIs(pool1, pool2, "全局池应该是同一个实例")
        finally:
            shutdown_browser_pool()
        logger.info("✅ 全局浏览器池单例测试通过")


def run_tests(test_names=None):
    """运行测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = {
        "TestRedisHelper": TestRedisHelper,
        "TestMongoHelper": TestMongoHelper,
        "TestBrowserPool": TestBrowserPool,
    }

    if test_names:
        for name in test_names:
            if name in test_classes:
                suite.addTests(loader.loadTestsFromTestCase(test_classes[name]))
            else:
                logger.error(f"未知测试类: {name}，可选: {', '.join(test_classes.keys())}")
                return
    else:
        # 按顺序添加所有测试
        suite.addTests(loader.loadTestsFromTestCase(TestRedisHelper))
        suite.addTests(loader.loadTestsFromTestCase(TestMongoHelper))
        suite.addTests(loader.loadTestsFromTestCase(TestBrowserPool))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("" + "=" * 60)
    if result.wasSuccessful():
        print("🎉 所有测试通过！")
    else:
        print(f"❌ 测试失败: {len(result.failures)} 个失败, {len(result.errors)} 个错误")
    print(f"   总计: {result.testsRun} 个测试")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    # 从命令行参数获取要运行的测试类名
    test_names = sys.argv[1:] if len(sys.argv) > 1 else None
    success = run_tests(test_names)
    sys.exit(0 if success else 1)
