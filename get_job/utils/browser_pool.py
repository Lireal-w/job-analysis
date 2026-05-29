"""
浏览器池模块
管理多个 Chromium 浏览器实例，支持浏览器复用、缓存保留和轮询调度。

核心特性：
- 浏览器配置文件存储在项目 .cache/browser_profiles/ 目录下，保留登录状态
- 利用浏览器缓存访问网站自动刷新 Cookie，无需每次手动登录
- 浏览器池管理多个浏览器实例，支持轮询获取和归还
- 每个浏览器实例有独立的用户数据目录，互不干扰
"""

import os
import time
import logging
import threading
from typing import Optional, Dict, List
from datetime import datetime

from DrissionPage import ChromiumPage, ChromiumOptions

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 缓存根目录
CACHE_DIR = os.path.join(PROJECT_ROOT, ".cache")

# 浏览器配置文件目录
BROWSER_PROFILES_DIR = os.path.join(CACHE_DIR, "browser_profiles")

# 默认浏览器池大小
DEFAULT_POOL_SIZE = 3

# 浏览器空闲超时时间（秒），超过后自动关闭
BROWSER_IDLE_TIMEOUT = 300


class BrowserInstance:
    """浏览器实例封装"""

    def __init__(self, instance_id: int, page: ChromiumPage, profile_dir: str):
        self.instance_id = instance_id
        self.page = page
        self.profile_dir = profile_dir
        self.in_use = False
        self.last_used = time.time()
        self.created_at = datetime.now()
        self._lock = threading.Lock()

    def mark_used(self):
        """标记为使用中"""
        with self._lock:
            self.in_use = True
            self.last_used = time.time()

    def mark_idle(self):
        """标记为空闲"""
        with self._lock:
            self.in_use = False
            self.last_used = time.time()

    def is_idle_timeout(self, timeout: int = BROWSER_IDLE_TIMEOUT) -> bool:
        """检查是否空闲超时"""
        with self._lock:
            return not self.in_use and (time.time() - self.last_used) > timeout

    def is_alive(self) -> bool:
        """检查浏览器是否存活"""
        try:
            if self.page is None:
                return False
            # 尝试访问页面属性判断浏览器是否还活着
            _ = self.page.url
            return True
        except Exception:
            return False

    def quit(self):
        """关闭浏览器"""
        try:
            if self.page:
                self.page.quit()
                logger.info(f"浏览器实例 #{self.instance_id} 已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器实例 #{self.instance_id} 失败: {e}")
        finally:
            self.page = None


class BrowserPool:
    """
    浏览器池
    管理多个 Chromium 浏览器实例，支持轮询调度和自动回收。
    每个浏览器实例拥有独立的用户数据目录，保留登录缓存。
    """

    def __init__(self, pool_size: int = DEFAULT_POOL_SIZE, headless: bool = False):
        """
        初始化浏览器池

        Args:
            pool_size: 池中浏览器实例数量
            headless: 是否使用无头模式
        """
        self.pool_size = pool_size
        self.headless = headless
        self._instances: Dict[int, BrowserInstance] = {}
        self._lock = threading.Lock()
        self._round_robin_index = 0
        self._next_id = 0

        # 确保目录存在
        os.makedirs(BROWSER_PROFILES_DIR, exist_ok=True)

        logger.info(f"浏览器池初始化，池大小: {pool_size}，无头模式: {headless}")

    def _get_profile_dir(self, instance_id: int) -> str:
        """获取指定实例的用户数据目录"""
        profile_dir = os.path.join(BROWSER_PROFILES_DIR, f"profile_{instance_id}")
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir

    def _create_chromium_options(self, profile_dir: str) -> ChromiumOptions:
        """创建 Chromium 配置选项"""
        co = ChromiumOptions()
        # 设置用户数据目录，保留登录缓存
        co.set_user_data_path(profile_dir)
        # 窗口最大化
        co.set_argument("--start-maximized")
        # 禁用自动化检测
        co.set_argument("--disable-blink-features=AutomationControlled")
        # 禁用 GPU 加速
        co.set_argument("--disable-gpu")
        # 无沙箱模式
        co.set_argument("--no-sandbox")
        # 禁用 "Chrome 正受到自动测试软件的控制" 提示栏
        co.set_argument("--disable-infobars")
        # 设置偏好：不提示密码保存
        co.set_argument("--disable-save-password-bubble")

        if self.headless:
            co.headless()

        return co

    def _create_instance(self) -> Optional[BrowserInstance]:
        """创建一个新的浏览器实例"""
        with self._lock:
            instance_id = self._next_id
            self._next_id += 1

        profile_dir = self._get_profile_dir(instance_id)
        co = self._create_chromium_options(profile_dir)

        try:
            logger.info(f"正在创建浏览器实例 #{instance_id}，配置目录: {profile_dir}")
            page = ChromiumPage(co)
            instance = BrowserInstance(instance_id, page, profile_dir)
            instance.mark_idle()

            with self._lock:
                self._instances[instance_id] = instance

            logger.info(f"浏览器实例 #{instance_id} 创建成功")
            return instance

        except Exception as e:
            logger.error(f"创建浏览器实例 #{instance_id} 失败: {e}")
            return None

    def get(self, timeout: float = 30) -> Optional[BrowserInstance]:
        """
        从池中获取一个浏览器实例（轮询方式）

        Args:
            timeout: 等待超时时间（秒）

        Returns:
            BrowserInstance 或 None
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._lock:
                # 优先查找空闲实例
                for inst in self._instances.values():
                    if not inst.in_use and inst.is_alive():
                        inst.mark_used()
                        logger.debug(f"复用浏览器实例 #{inst.instance_id}")
                        return inst

                # 如果池未满，创建新实例
                if len(self._instances) < self.pool_size:
                    break

            # 池已满且都在使用，等待
            time.sleep(0.5)

        # 创建新实例
        instance = self._create_instance()
        if instance:
            instance.mark_used()
            return instance

        return None

    def release(self, instance: BrowserInstance):
        """
        归还浏览器实例到池中

        Args:
            instance: 要归还的浏览器实例
        """
        if instance and instance.instance_id in self._instances:
            instance.mark_idle()
            logger.debug(f"浏览器实例 #{instance.instance_id} 已归还到池中")
        else:
            # 不在池中的实例，直接关闭
            if instance:
                instance.quit()

    def cleanup_idle(self):
        """清理空闲超时的浏览器实例"""
        with self._lock:
            to_remove = []
            for inst_id, inst in self._instances.items():
                if inst.is_idle_timeout() and not inst.in_use:
                    to_remove.append(inst_id)

            for inst_id in to_remove:
                inst = self._instances.pop(inst_id)
                inst.quit()
                logger.info(f"已清理空闲超时的浏览器实例 #{inst_id}")

    def cleanup_dead(self):
        """清理已死亡的浏览器实例"""
        with self._lock:
            to_remove = []
            for inst_id, inst in self._instances.items():
                if not inst.is_alive() and not inst.in_use:
                    to_remove.append(inst_id)

            for inst_id in to_remove:
                inst = self._instances.pop(inst_id)
                inst.quit()
                logger.info(f"已清理死亡的浏览器实例 #{inst_id}")

    def get_stats(self) -> Dict:
        """获取浏览器池状态"""
        with self._lock:
            total = len(self._instances)
            in_use = sum(1 for inst in self._instances.values() if inst.in_use)
            idle = total - in_use
            alive = sum(1 for inst in self._instances.values() if inst.is_alive())

        return {
            "total": total,
            "in_use": in_use,
            "idle": idle,
            "alive": alive,
            "pool_size": self.pool_size,
            "profiles_dir": BROWSER_PROFILES_DIR,
        }

    def shutdown(self):
        """关闭所有浏览器实例"""
        with self._lock:
            for inst in self._instances.values():
                inst.quit()
            self._instances.clear()
            logger.info("浏览器池已关闭，所有实例已释放")

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass


# ==========================================
# 全局浏览器池单例
# ==========================================
_global_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_browser_pool(pool_size: int = DEFAULT_POOL_SIZE, headless: bool = False) -> BrowserPool:
    """获取全局浏览器池实例"""
    global _global_pool
    with _pool_lock:
        if _global_pool is None:
            _global_pool = BrowserPool(pool_size=pool_size, headless=headless)
        return _global_pool


def shutdown_browser_pool():
    """关闭全局浏览器池"""
    global _global_pool
    with _pool_lock:
        if _global_pool is not None:
            _global_pool.shutdown()
            _global_pool = None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pool = BrowserPool(pool_size=2, headless=False)

    try:
        # 获取浏览器实例
        inst = pool.get()
        if inst:
            print(f"获取到浏览器实例 #{inst.instance_id}")

            # 查看池状态
            stats = pool.get_stats()
            print(f"浏览器池状态: {stats}")

            # 归还实例
            pool.release(inst)
        else:
            print("未能获取浏览器实例")
    finally:
        pool.shutdown()
