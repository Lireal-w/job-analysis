"""
DrissionPage 登录工具模块
使用 DrissionPage 启动浏览器，手动或自动登录智联校园招聘网站，
获取登录后的 Cookie，供 Scrapy 爬虫使用。
Cookie 缓存存储在 MongoDB 数据库中，数据库配置通过 .env 文件管理。
"""

import os
import time
import logging

from DrissionPage import ChromiumPage, ChromiumOptions

from get_job.utils.mongo_helper import (
    save_cookies_to_mongo,
    load_cookies_from_mongo,
    close_mongo_client,
)

logger = logging.getLogger(__name__)

# 浏览器数据目录
BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".browser_data")


def get_chromium_options() -> ChromiumOptions:
    """获取 Chromium 浏览器配置选项"""
    co = ChromiumOptions()
    # 设置浏览器路径（如果默认路径找不到浏览器，需要手动指定）
    # co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    # 设置用户数据目录，保留登录状态
    co.set_user_data_path(BROWSER_DATA_DIR)
    # 窗口最大化
    co.set_argument("--start-maximized")
    # 禁用自动化检测
    co.set_argument("--disable-blink-features=AutomationControlled")
    # 禁用 GPU 加速（某些环境下需要）
    co.set_argument("--disable-gpu")
    # 无沙箱模式
    co.set_argument("--no-sandbox")
    return co


def login_xiaoyuan(headless: bool = False, timeout: int = 120) -> dict:
    """
    使用 DrissionPage 启动浏览器登录智联校园招聘网站，获取 Cookie。

    Args:
        headless: 是否使用无头模式（登录时建议设为 False，方便手动操作）
        timeout: 等待用户完成登录的超时时间（秒）

    Returns:
        dict: 登录后的 Cookie 字典
    """
    co = get_chromium_options()

    if headless:
        co.headless()

    page = None
    try:
        logger.info("正在启动浏览器...")
        page = ChromiumPage(co)

        # 访问智联校园招聘首页
        logger.info("正在访问 https://xiaoyuan.zhaopin.com/ ...")
        page.get("https://xiaoyuan.zhaopin.com/")

        # 等待页面加载
        time.sleep(3)

        # 检查是否需要登录（查找登录按钮或已登录状态）
        current_url = page.url
        logger.info(f"当前页面 URL: {current_url}")

        # 尝试点击登录按钮（如果存在）
        try:
            login_btn = page.ele('xpath://a[contains(text(),"登录")]', timeout=5)
            if login_btn:
                logger.info("发现登录按钮，点击进入登录页面...")
                login_btn.click()
                time.sleep(2)
        except Exception:
            logger.info("未找到登录按钮，可能已在登录页面或已登录")

        # 检查是否已登录
        if _is_logged_in(page):
            logger.info("检测到已登录状态，直接获取 Cookie")
        else:
            logger.info("=" * 60)
            logger.info("请在浏览器中完成登录操作...")
            logger.info(f"等待时间: {timeout} 秒")
            logger.info("登录成功后，程序将自动获取 Cookie")
            logger.info("=" * 60)

            # 等待用户完成登录
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(3)
                if _is_logged_in(page):
                    logger.info("检测到登录成功！")
                    break
            else:
                logger.warning(f"等待登录超时（{timeout}秒），尝试获取当前 Cookie...")

        # 获取 Cookie
        cookies = _get_cookies_from_page(page)

        if cookies:
            logger.info(f"成功获取 {len(cookies)} 个 Cookie")
            # 保存 Cookie 到 MongoDB
            save_cookies_to_mongo(cookies)
        else:
            logger.warning("未能获取到有效 Cookie")

        return cookies

    except Exception as e:
        logger.error(f"登录过程发生错误: {e}")
        return {}
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass


def _is_logged_in(page: ChromiumPage) -> bool:
    """
    检查是否已登录。
    通过检测页面上是否存在用户头像、用户名等已登录标识来判断。
    """
    try:
        # 检查是否存在用户头像或用户名元素（已登录状态）
        # 智联招聘登录后通常会有用户头像或用户名显示
        user_avatar = page.ele('xpath://*[contains(@class,"avatar") or contains(@class,"user") or contains(@class,"header-user")]', timeout=3)
        if user_avatar:
            return True

        # 检查 URL 是否包含登录相关参数（跳转回首页说明登录成功）
        if "xiaoyuan.zhaopin.com" in page.url and "login" not in page.url.lower():
            # 再检查是否有退出/个人中心等已登录才有的元素
            logout_btn = page.ele('xpath://a[contains(text(),"退出") or contains(text(),"个人中心") or contains(text(),"我的")]', timeout=3)
            if logout_btn:
                return True

        # 通过 Cookie 判断：如果存在关键登录 Cookie
        cookies = page.cookies()
        cookie_names = [c.get("name", "") for c in cookies] if isinstance(cookies, list) else []
        key_cookies = ["zpData", "sensorsdata2015jssdkChannel", "x-zp-client-id"]
        for key in key_cookies:
            if key in cookie_names:
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
    优先从 MongoDB 缓存加载，如果缓存不存在或已过期或 force_login=True，则启动浏览器登录。

    Args:
        force_login: 是否强制重新登录

    Returns:
        dict: Cookie 字典
    """
    if not force_login:
        cached_cookies = load_cookies_from_mongo()
        if cached_cookies:
            logger.info("使用 MongoDB 缓存的 Cookie")
            return cached_cookies

    logger.info("启动浏览器进行登录获取 Cookie...")
    return login_xiaoyuan(headless=False)


if __name__ == "__main__":
    # 直接运行此模块进行登录获取 Cookie
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    try:
        cookies = get_cookies_with_login(force_login=True)
        if cookies:
            print(f"获取到 {len(cookies)} 个 Cookie（已保存到MongoDB）:")
            for name, value in cookies.items():
                # 只显示前20个字符，避免泄露
                display_val = value[:20] + "..." if len(value) > 20 else value
                print(f"  {name}: {display_val}")
        else:
            print("未能获取到 Cookie，请检查登录流程")
    finally:
        close_mongo_client()
