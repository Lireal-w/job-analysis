# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import os
import time
import logging
from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

from get_job.utils.drissionpage_login import get_cookies_with_login, refresh_cookie_via_browser
from get_job.utils.browser_pool import get_browser_pool, shutdown_browser_pool

logger = logging.getLogger(__name__)


class GetJobSpiderMiddleware:
    """Spider 中间件"""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        s._crawler = crawler
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response):
        return None

    async def process_spider_output(self, response, result):
        async for i in result:
            yield i

    def process_spider_exception(self, response, exception):
        pass

    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class GetJobDownloaderMiddleware:
    """Downloader 中间件"""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        s._crawler = crawler
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request):
        return None

    def process_response(self, request, response):
        return response

    def process_exception(self, request, exception):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class DrissionPageCookieMiddleware:
    """
    DrissionPage Cookie 注入中间件
    在 from_crawler 阶段通过浏览器池获取 Cookie（确保 start_requests 发出时已有 Cookie），
    然后将 Cookie 注入到每个 Scrapy 请求中。
    Cookie 过期时自动通过浏览器池刷新。
    """

    def __init__(self, force_login=False):
        self.force_login = force_login
        self.cookies = {}
        self.browser_pool = None
        self.site_url = None
        self.is_logged_in = None
        self._spider = None

    @classmethod
    def from_crawler(cls, crawler):
        force_login = crawler.settings.getbool("FORCE_LOGIN", False)
        middleware = cls(force_login=force_login)
        # 保存 crawler 引用，以便在需要时获取 spider
        middleware._crawler = crawler
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def _ensure_cookies(self, spider=None):
        """确保 Cookie 已获取（懒加载，首次调用时获取）"""
        if self.cookies:
            return

        if spider:
            self._spider = spider

        if not self._spider:
            return

        logger.info("=" * 60)
        logger.info("DrissionPage Cookie 中间件正在初始化...")
        logger.info("=" * 60)

        # 从爬虫类获取网站特定的配置
        self.site_url = getattr(self._spider, "site_url", None)
        self.is_logged_in = getattr(self._spider, "is_logged_in", None)

        if not self.site_url:
            logger.warning(f"爬虫 {self._spider.name} 未定义 site_url，无法自动刷新 Cookie")
        if not self.is_logged_in:
            logger.warning(f"爬虫 {self._spider.name} 未定义 is_logged_in 方法，无法自动检测登录状态")

        # 初始化浏览器池
        pool_size = self._spider.settings.getint("BROWSER_POOL_SIZE", 3)
        self.browser_pool = get_browser_pool(pool_size=pool_size, headless=False)

        logger.info(f"浏览器池已初始化，池大小: {pool_size}")

        # 获取 Cookie
        self.cookies = get_cookies_with_login(
            url=self.site_url,
            is_logged_in=self.is_logged_in,
            force_login=self.force_login,
        )

        if self.cookies:
            logger.info(f"成功获取 {len(self.cookies)} 个 Cookie，将注入到后续请求中")
        else:
            logger.warning("未能获取到 Cookie，后续请求可能无法访问需要登录的页面")

        # 打印浏览器池状态
        stats = self.browser_pool.get_stats()
        logger.info(f"浏览器池状态: {stats}")

    def spider_closed(self, spider, reason):
        """Spider 关闭时清理浏览器池"""
        logger.info("Spider 关闭，正在清理浏览器池...")
        if self.browser_pool:
            self.browser_pool.cleanup_idle()
            stats = self.browser_pool.get_stats()
            logger.info(f"浏览器池最终状态: {stats}")
        shutdown_browser_pool()
        logger.info("浏览器池已关闭")

    def process_request(self, request):
        """在每个请求中注入 Cookie"""
        # 懒加载：首次请求时确保 Cookie 已获取
        spider = self._crawler.spider if hasattr(self, '_crawler') else None
        self._ensure_cookies(spider)

        if not self.cookies:
            return None

        # 将 Cookie 注入到请求头
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        request.headers.setdefault("Cookie", cookie_str)

        # 同时也设置到 request.cookies 中
        for name, value in self.cookies.items():
            request.cookies[name] = value

        return None

    def process_response(self, request, response):
        """处理响应，检测是否需要重新登录"""
        need_refresh = False

        # 如果返回302重定向到登录页面，说明 Cookie 过期
        if response.status in (302, 301):
            redirect_url = response.headers.get("Location", b"").decode("utf-8", errors="ignore")
            if "login" in redirect_url.lower():
                need_refresh = True

        # 如果返回401或403，可能也需要重新登录
        if response.status in (401, 403):
            need_refresh = True

        # 如果返回200但页面内容是登录页（智联校园招聘常见情况）
        if response.status == 200 and self._is_login_page(response):
            need_refresh = True

        if need_refresh:
            logger.warning(f"检测到 Cookie 过期（状态码: {response.status}，URL: {response.url}），通过浏览器池刷新 Cookie...")
            # 使用浏览器池刷新 Cookie
            if self.browser_pool and self.site_url:
                self.cookies = refresh_cookie_via_browser(
                    url=self.site_url,
                    is_logged_in=self.is_logged_in,
                    pool=self.browser_pool,
                )
            else:
                self.cookies = get_cookies_with_login(
                    url=self.site_url,
                    is_logged_in=self.is_logged_in,
                    force_login=True,
                )

            if self.cookies:
                request.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
                return request.replace(dont_filter=True)

        return response

    @staticmethod
    def _is_login_page(response) -> bool:
        """
        检测200状态码响应是否实际为登录页面

        智联校园招聘在 Cookie 失效时，不会返回 302 重定向，
        而是返回 200 状态码但页面内容是登录页。需要通过页面内容判断。

        Returns:
            bool: 是否为登录页面
        """
        from get_job.utils.spider_helpers import is_login_page_by_content
        return is_login_page_by_content(response)


class RequestDebugMiddleware:
    """
    请求调试中间件
    将所有请求和响应的详细信息保存为文件，用于排查问题。
    保存内容包括：请求 URL、方法、Headers、Cookie、响应状态码、响应体等。
    文件保存在 debug_requests/ 目录下。
    """

    def __init__(self, debug_dir="debug_requests"):
        self.debug_dir = debug_dir
        self._request_count = 0
        self._session_id = time.strftime("%Y%m%d_%H%M%S")

    @classmethod
    def from_crawler(cls, crawler):
        debug_dir = crawler.settings.get("REQUEST_DEBUG_DIR", "debug_requests")
        middleware = cls(debug_dir=debug_dir)
        return middleware

    def _get_debug_filepath(self, request, response=None):
        """生成调试文件路径"""
        self._request_count += 1
        status_suffix = f"_{response.status}" if response else ""
        filename = f"{self._request_count:04d}{status_suffix}_{self._session_id}.txt"
        return os.path.join(self.debug_dir, filename)

    def _save_request_debug(self, request, response=None):
        """保存请求和响应调试信息到文件"""
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            filepath = self._get_debug_filepath(request, response)

            lines = []
            lines.append("=" * 80)
            lines.append("请求调试信息")
            lines.append("=" * 80)
            lines.append("")

            # 请求信息
            lines.append("【请求信息】")
            lines.append(f"  URL:        {request.url}")
            lines.append(f"  方法:       {request.method}")
            lines.append(f"  Meta:       {dict(request.meta)}")
            lines.append(f"  Dont Filter: {request.dont_filter}")
            lines.append("")

            # 请求 Headers
            lines.append("【请求 Headers】")
            for key, value in request.headers.items():
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                value_str = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                # 脱敏 Cookie 中的敏感信息
                if key_str.lower() == "cookie":
                    cookie_parts = value_str.split("; ")
                    masked_parts = []
                    for part in cookie_parts:
                        if "=" in part:
                            k, v = part.split("=", 1)
                            if len(v) > 8:
                                masked_parts.append(f"{k}={v[:4]}...{v[-4:]}")
                            else:
                                masked_parts.append(f"{k}=****")
                        else:
                            masked_parts.append(part)
                    value_str = "; ".join(masked_parts)
                lines.append(f"  {key_str}: {value_str}")
            lines.append("")

            # 请求 Cookies
            lines.append("【请求 Cookies】")
            if request.cookies:
                for name, value in request.cookies.items():
                    value_str = str(value)
                    if len(value_str) > 8:
                        value_str = f"{value_str[:4]}...{value_str[-4:]}"
                    lines.append(f"  {name}: {value_str}")
            else:
                lines.append("  (无)")
            lines.append("")

            # 响应信息
            if response:
                lines.append("【响应信息】")
                lines.append(f"  状态码:     {response.status}")
                lines.append(f"  URL:        {response.url}")
                lines.append(f"  编码:       {response.encoding}")
                lines.append(f"  Body 长度:  {len(response.body)} bytes")
                lines.append("")

                # 响应 Headers
                lines.append("【响应 Headers】")
                for key, value in response.headers.items():
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    value_str = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                    lines.append(f"  {key_str}: {value_str}")
                lines.append("")

                # 响应体（截取前 5000 字符）
                lines.append("【响应体（前 5000 字符）】")
                try:
                    body_text = response.text[:5000]
                except Exception:
                    body_text = response.body[:5000].decode("utf-8", errors="replace")
                lines.append(body_text)
                if len(response.body) > 5000:
                    lines.append(f"... (共 {len(response.body)} bytes，已截取前 5000 字符)")
                lines.append("")
            else:
                lines.append("【响应信息】(无响应，请求可能被中间件拦截)")
                lines.append("")

            lines.append("=" * 80)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.debug(f"请求调试信息已保存: {filepath}")

        except Exception as e:
            logger.error(f"保存请求调试信息失败: {e}")

    def process_request(self, request):
        """记录发出的请求"""
        # 只记录目标网站的请求，不记录静态资源等
        if "zhaopin.com" in request.url:
            logger.info(f"[DEBUG] 请求发出 -> {request.method} {request.url}")
        return None

    def process_response(self, request, response):
        """记录收到的响应，并保存完整调试信息"""
        if "zhaopin.com" in request.url:
            logger.info(f"[DEBUG] 响应收到 <- {response.status} {request.url} (Body: {len(response.body)} bytes)")
            # 保存完整调试信息到文件
            self._save_request_debug(request, response)
        return response

    def process_exception(self, request, exception):
        """记录请求异常"""
        if "zhaopin.com" in request.url:
            logger.warning(f"[DEBUG] 请求异常 !! {request.method} {request.url} -> {type(exception).__name__}: {exception}")
            self._save_request_debug(request)
        return None


class RandomUserAgentMiddleware:
    """随机 User-Agent 中间件"""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]

    def __init__(self):
        import random
        self._random = random.Random()

    def process_request(self, request):
        ua = self._random.choice(self.USER_AGENTS)
        request.headers.setdefault("User-Agent", ua)
