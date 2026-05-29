"""
DrissionPage 登录工具模块
使用浏览器池管理多个 Chromium 实例，利用浏览器缓存刷新 Cookie。

核心流程：
1. 优先从 MongoDB 加载缓存的 Cookie
2. 如果缓存不存在或已过期，从浏览器池获取实例
3. 利用浏览器配置文件中保留的登录状态，访问网站自动刷新 Cookie
4. 如果浏览器缓存也过期（未登录），则等待用户手动登录
5. 获取到的 Cookie 保存到 MongoDB

Cookie 缓存存储在 MongoDB 数据库中，数据库配置通过 .env 文件管理。
浏览器配置文件存储在 .cache/browser_profiles/ 目录下。
"""

import os
import time
import logging

from DrissionPage import ChromiumPage

from get_job.utils.mongo_helper import (
    save_cookies_to_mongo,
    load_cookies_from_mongo,
    close_mongo_client,
)
from get_job.utils.browser_pool import (
    BrowserPool,
    get_browser_pool,
    shutdown_browser_pool,
    BROWSER_PROFILES_DIR,
)

logger = logging.getLogger(__name__)

# 智联校园招聘 URL
XIAOYUAN_URL = "https://xiaoyuan.zhaopin.com/"


def refresh_cookie_via_browser(pool: BrowserPool = None, headless: bool = False, timeout: int = 120) -> dict:
    """
    通过浏览器池刷新 Cookie。
    利用浏览器配置文件中保留的登录状态，访问网站自动获取最新 Cookie。
    如果浏览器未登录，则等待用户手动登录。

    Args:
        pool: 浏览器池实例，如果为 None 则使用全局池
        headless: 是否使用无头模式
        timeout: 等待用户登录的超时时间（秒）

    Returns:
        dict: Cookie 字典
    """
    if pool is None:
        pool = get_browser_pool(headless=headless)

    instance = pool.get(timeout=30)
    if not instance:
        logger.error("无法从浏览器池获取实例")
        return {}

    try:
        logger.info(f"使用浏览器实例 #{instance.instance_id} 刷新 Cookie")

        # 访问智联校园招聘
        instance.page.get(XIAOYUAN_URL)
        time.sleep(3)

        current_url = instance.page.url
        logger.info(f"当前页面 URL: {current_url}")

        # 检查是否已登录
        if _is_logged_in(instance.page):
            logger.info(f"浏览器实例 #{instance.instance_id} 已登录，直接获取 Cookie")
        else:
            # 尝试点击登录按钮
            try:
                login_btn = instance.page.ele('xpath://a[contains(text(),"登录")]', timeout=5)
                if login_btn:
                    logger.info("发现登录按钮，点击进入登录页面...")
                    login_btn.click()
                    time.sleep(2)
            except Exception:
                logger.info("未找到登录按钮")

            # 再次检查登录状态
            if not _is_logged_in(instance.page):
                logger.info("=" * 60)
                logger.info(f"浏览器实例 #{instance.instance_id} 需要登录")
                logger.info("请在浏览器中完成登录操作...")
                logger.info(f"等待时间: {timeout} 秒")
                logger.info("登录成功后，程序将自动获取 Cookie")
                logger.info("=" * 60)

                # 等待用户完成登录
                start_time = time.time()
                while time.time() - start_time < timeout:
                    time.sleep(3)
                    if _is_logged_in(instance.page):
                        logger.info("检测到登录成功！")
                        break
                else:
                    logger.warning(f"等待登录超时（{timeout}秒），尝试获取当前 Cookie...")

        # 获取 Cookie
        cookies = _get_cookies_from_page(instance.page)

        if cookies:
            logger.info(f"成功获取 {len(cookies)} 个 Cookie")
            save_cookies_to_mongo(cookies)
        else:
            logger.warning("未能获取到有效 Cookie")

        return cookies

    except Exception as e:
        logger.error(f"刷新 Cookie 过程发生错误: {e}")
        return {}
    finally:
        # 归还浏览器实例到池中（不关闭，保留登录状态）
        pool.release(instance)
        logger.info(f"浏览器实例 #{instance.instance_id} 已归还到池中")


def login_xiaoyuan(headless: bool = False, timeout: int = 120) -> dict:
    """
    登录智联校园招聘网站获取 Cookie（兼容旧接口）。
    内部使用浏览器池实现。

    Args:
        headless: 是否使用无头模式
        timeout: 等待用户登录的超时时间（秒）

    Returns:
        dict: Cookie 字典
    """
    return refresh_cookie_via_browser(headless=headless, timeout=timeout)


def _is_logged_in(page: ChromiumPage) -> bool:
    """
    检查是否已登录。
    通过检测页面上是否存在用户头像、用户名等已登录标识来判断。
    """
    try:
        # 检查是否存在用户头像或用户名元素（已登录状态）
        user_avatar = page.ele(
            'xpath://*[contains(@class,"avatar") or contains(@class,"user") or contains(@class,"header-user")]',
            timeout=3,
        )
        if user_avatar:
            return True

        # 检查 URL 是否包含登录相关参数
        if "xiaoyuan.zhaopin.com" in page.url and "login" not in page.url.lower():
            logout_btn = page.ele(
                'xpath://a[contains(text(),"退出") or contains(text(),"个人中心") or contains(text(),"我的")]',
                timeout=3,
            )
            if logout_btn:
                return True

    except Exception:
        pass

    return False


def _get_cookies_from_page(page: ChromiumPage) -> dict:
    """从 DrissionPage 页面获取 Cookie，返回字典格式"""
    cookies = {}
    try:
        raw_cookies = page.cookies()
        if isinstance(raw_cookies, list):
            for cookie in raw_cookies:
                if isinstance(cookie, dict):
                    name = cookie.get("name", "")
                    value = cookie.get("value", "")
                    if name and value:
                        cookies[name] = value
        elif isinstance(raw_cookies, dict):
            cookies = raw_cookies
    except Exception as e:
        logger.error(f"获取 Cookie 失败: {e}")
    return cookies


def get_cookies_with_login(force_login: bool = False) -> dict:
    """
    获取 Cookie 的统一入口。

    流程：
    1. 如果非强制登录，优先从 MongoDB 加载缓存的 Cookie
    2. 如果缓存不存在或已过期，从浏览器池获取实例
    3. 利用浏览器配置文件中保留的登录状态访问网站刷新 Cookie
    4. 如果浏览器也未登录，等待用户手动登录

    Args:
        force_login: 是否强制重新登录（跳过 MongoDB 缓存，直接用浏览器刷新）

    Returns:
        dict: Cookie 字典
    """
    if not force_login:
        cached_cookies = load_cookies_from_mongo()
        if cached_cookies:
            logger.info("使用 MongoDB 缓存的 Cookie")
            return cached_cookies

    logger.info("通过浏览器池刷新 Cookie...")
    return refresh_cookie_via_browser(headless=False)


if __name__ == "__main__":
    # 直接运行此模块进行登录获取 Cookie
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    pool = None
    try:
        pool = BrowserPool(pool_size=2, headless=False)
        cookies = refresh_cookie_via_browser(pool=pool, timeout=120)
        if cookies:
            print(f"获取到 {len(cookies)} 个 Cookie（已保存到MongoDB）:")
            for name, value in cookies.items():
                display_val = value[:20] + "..." if len(value) > 20 else value
                print(f"  {name}: {display_val}")
        else:
            print("未能获取到 Cookie，请检查登录流程")

        # 查看浏览器池状态
        stats = pool.get_stats()
        print(f"\n浏览器池状态: {stats}")
    finally:
        if pool:
            pool.shutdown()
        close_mongo_client()
