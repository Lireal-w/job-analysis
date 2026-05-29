"""
DrissionPage 通用登录工具模块
提供通用的浏览器登录和 Cookie 刷新功能，不包含任何网站特定的登录检查逻辑。

核心流程：
1. 优先从 MongoDB 加载缓存的 Cookie
2. 如果缓存不存在或已过期，从浏览器池获取实例
3. 利用浏览器配置文件中保留的登录状态，访问网站自动刷新 Cookie
4. 如果浏览器缓存也过期（未登录），则等待用户手动登录
5. 获取到的 Cookie 保存到 MongoDB

网站特定的登录检查逻辑（is_logged_in）由调用方（如爬虫类）提供。
Cookie 缓存存储在 MongoDB 数据库中，数据库配置通过 .env 文件管理。
浏览器配置文件存储在 .cache/browser_profiles/ 目录下。
"""

import time
import logging
from typing import Callable, Optional

from DrissionPage import ChromiumPage

from get_job.utils.redis_helper import (
    save_cookies_to_redis,
    load_cookies_from_redis,
    close_redis_client,
)
from get_job.utils.browser_pool import (
    BrowserPool,
    get_browser_pool,
    shutdown_browser_pool,
)

logger = logging.getLogger(__name__)

# 默认登录检查函数：始终返回 False（未登录），需要调用方提供真实的检查逻辑
DEFAULT_LOGIN_CHECK = lambda page: False


def extract_cookies_from_page(page: ChromiumPage) -> dict:
    """
    从 DrissionPage 页面提取 Cookie，返回字典格式。
    这是通用的 Cookie 提取函数，适用于所有网站。

    Args:
        page: DrissionPage 页面实例

    Returns:
        dict: Cookie 字典 {name: value}
    """
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
        logger.error(f"提取 Cookie 失败: {e}")
    return cookies


def refresh_cookie_via_browser(
    url: str,
    is_logged_in: Callable[[ChromiumPage], bool] = None,
    pool: BrowserPool = None,
    headless: bool = False,
    timeout: int = 120,
) -> dict:
    """
    通过浏览器池刷新 Cookie（通用方法）。

    利用浏览器配置文件中保留的登录状态，访问目标网站自动获取最新 Cookie。
    如果浏览器未登录，则等待用户手动登录。

    Args:
        url: 要访问的目标网站 URL
        is_logged_in: 登录状态检查函数，接收 ChromiumPage 实例，返回是否已登录。
                      如果为 None，则使用默认检查（始终返回 False，即始终等待手动登录）。
        pool: 浏览器池实例，如果为 None 则使用全局池
        headless: 是否使用无头模式
        timeout: 等待用户登录的超时时间（秒）

    Returns:
        dict: Cookie 字典
    """
    if is_logged_in is None:
        is_logged_in = DEFAULT_LOGIN_CHECK

    if pool is None:
        pool = get_browser_pool(headless=headless)

    instance = pool.get(timeout=30)
    if not instance:
        logger.error("无法从浏览器池获取实例")
        return {}

    try:
        logger.info(f"使用浏览器实例 #{instance.instance_id} 访问 {url}")

        # 访问目标网站
        instance.page.get(url)
        time.sleep(3)

        current_url = instance.page.url
        logger.info(f"当前页面 URL: {current_url}")

        # 使用调用方提供的检查函数判断是否已登录
        if is_logged_in(instance.page):
            logger.info(f"浏览器实例 #{instance.instance_id} 已登录，直接获取 Cookie")
        else:
            logger.info(f"浏览器实例 #{instance.instance_id} 未登录，等待用户手动登录...")
            logger.info("=" * 60)
            logger.info("请在浏览器中完成登录操作...")
            logger.info(f"等待时间: {timeout} 秒")
            logger.info("登录成功后，程序将自动获取 Cookie")
            logger.info("=" * 60)

            # 等待用户完成登录
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(3)
                if is_logged_in(instance.page):
                    logger.info("检测到登录成功！")
                    break
            else:
                logger.warning(f"等待登录超时（{timeout}秒），尝试获取当前 Cookie...")

        # 获取 Cookie
        cookies = extract_cookies_from_page(instance.page)

        if cookies:
            logger.info(f"成功获取 {len(cookies)} 个 Cookie")
            save_cookies_to_redis(cookies)
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


def get_cookies_with_login(
    url: str = None,
    is_logged_in: Callable[[ChromiumPage], bool] = None,
    force_login: bool = False,
) -> dict:
    """
    获取 Cookie 的统一入口（通用方法）。

    流程：
    1. 如果非强制登录，优先从 MongoDB 加载缓存的 Cookie
    2. 如果缓存不存在或已过期，从浏览器池获取实例
    3. 利用浏览器配置文件中保留的登录状态访问网站刷新 Cookie
    4. 如果浏览器也未登录，等待用户手动登录

    Args:
        url: 要访问的目标网站 URL
        is_logged_in: 登录状态检查函数，接收 ChromiumPage 实例，返回是否已登录
        force_login: 是否强制重新登录（跳过 MongoDB 缓存，直接用浏览器刷新）

    Returns:
        dict: Cookie 字典
    """
    if not force_login:
        cached_cookies = load_cookies_from_redis()
        if cached_cookies:
            logger.info("使用 Redis 缓存的 Cookie")
            return cached_cookies

    if not url:
        logger.error("未提供目标网站 URL，无法刷新 Cookie")
        return {}

    logger.info(f"通过浏览器池刷新 Cookie（{url}）...")
    return refresh_cookie_via_browser(url=url, is_logged_in=is_logged_in, headless=False)


if __name__ == "__main__":
    # 直接运行此模块进行测试
    # 需要提供 url 和 is_logged_in 才能正常工作
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("本模块为通用登录工具，需要由爬虫类提供 is_logged_in 检查函数。")
    print("请通过爬虫中间件调用，或参考以下示例：")
    print()
    print("  from get_job.utils.drissionpage_login import refresh_cookie_via_browser")
    print()
    print("  def my_login_check(page):")
    print('      return bool(page.ele(\'xpath://*[@class="avatar"]\', timeout=3))')
    print()
    print("  cookies = refresh_cookie_via_browser(")
    print('      url="https://example.com",')
    print("      is_logged_in=my_login_check,")
    print("  )")
