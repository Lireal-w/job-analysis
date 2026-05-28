# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import logging
from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

from get_job.utils.drissionpage_login import get_cookies_with_login

logger = logging.getLogger(__name__)


class GetJobSpiderMiddleware:
    """Spider 中间件"""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    async def process_spider_output(self, response, result, spider):
        async for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
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
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class DrissionPageCookieMiddleware:
    """
    DrissionPage Cookie 注入中间件
    在 Spider 启动时通过 DrissionPage 启动浏览器登录获取 Cookie，
    然后将 Cookie 注入到每个 Scrapy 请求中。
    """

    def __init__(self, force_login=False):
        self.force_login = force_login
        self.cookies = {}

    @classmethod
    def from_crawler(cls, crawler):
        force_login = crawler.settings.getbool("FORCE_LOGIN", False)
        middleware = cls(force_login=force_login)
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    def spider_opened(self, spider):
        """Spider 启动时获取 Cookie"""
        logger.info("=" * 60)
        logger.info("DrissionPage Cookie 中间件正在初始化...")
        logger.info("=" * 60)

        self.cookies = get_cookies_with_login(force_login=self.force_login)

        if self.cookies:
            logger.info(f"成功获取 {len(self.cookies)} 个 Cookie，将注入到后续请求中")
        else:
            logger.warning("未能获取到 Cookie，后续请求可能无法访问需要登录的页面")

    def process_request(self, request, spider):
        """在每个请求中注入 Cookie"""
        if not self.cookies:
            return None

        # 将 Cookie 注入到请求头
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        request.headers.setdefault("Cookie", cookie_str)

        # 同时也设置到 request.cookies 中
        for name, value in self.cookies.items():
            request.cookies[name] = value

        return None

    def process_response(self, request, response, spider):
        """处理响应，检测是否需要重新登录"""
        # 如果返回302重定向到登录页面，说明 Cookie 过期
        if response.status in (302, 301):
            redirect_url = response.headers.get("Location", b"").decode("utf-8", errors="ignore")
            if "login" in redirect_url.lower():
                logger.warning("检测到 Cookie 过期，正在重新登录获取 Cookie...")
                self.cookies = get_cookies_with_login(force_login=True)
                if self.cookies:
                    request.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
                    return request.replace(dont_filter=True)

        # 如果返回401或403，可能也需要重新登录
        if response.status in (401, 403):
            logger.warning(f"请求返回状态码 {response.status}，尝试重新登录...")
            self.cookies = get_cookies_with_login(force_login=True)
            if self.cookies:
                request.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
                return request.replace(dont_filter=True)

        return response


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

    def process_request(self, request, spider):
        ua = self._random.choice(self.USER_AGENTS)
        request.headers.setdefault("User-Agent", ua)
