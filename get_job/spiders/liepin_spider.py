
"""
猎聘爬虫
爬取 https://www.liepin.com/ 的职位信息

工作流程：
1. Spider 启动时，DrissionPageCookieMiddleware 会自动启动浏览器登录获取 Cookie
2. 使用获取到的 Cookie 发起请求，通过搜索 API 获取职位列表
3. 解析职位列表，提取职位基本信息
4. 访问职位详情页，提取完整职位信息
5. 数据通过 Pipeline 进行清洗、去重和存储
"""

import json
import logging
import time
from urllib.parse import urlencode, quote
from typing import List, Tuple

import scrapy
from scrapy.http import Request

from get_job.items import LiepinJobItem, LiepinCompanyItem
from get_job.region import (
    get_search_keywords_from_env,
    get_target_regions_from_env,
    get_max_page_from_env,
)
from get_job.region.liepin_strategy import create_liepin_region_factory
from get_job.region.liepin_table import LIEPIN_REGION_TABLE
from get_job.spiders.liepin_parsers import (
    JobListParserMixin,
    JobDetailParserMixin,
    CompanyDetailParserMixin,
)

logger = logging.getLogger(__name__)


class LiepinSpider(
    JobListParserMixin,
    JobDetailParserMixin,
    CompanyDetailParserMixin,
    scrapy.Spider,
):
    """猎聘招聘爬虫"""

    name = "liepin"
    allowed_domains = ["liepin.com", "api-c.liepin.com", "capi.liepin.com"]
    start_urls = ["https://www.liepin.com/"]

    # 自定义设置
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    # 地区策略工厂（猎聘专用）
    region_factory = create_liepin_region_factory()

    # 搜索关键词（优先从 .env 读取，否则使用默认值）
    search_keywords = get_search_keywords_from_env()

    # 目标地区列表：[(地区名称, 地区ID), ...]（优先从 .env 读取，否则使用默认值）
    target_regions: List[Tuple[str, int]] = get_target_regions_from_env(region_factory)

    # 最大翻页数（优先从 .env 读取，否则使用默认值）
    max_page = get_max_page_from_env()

    # 猎聘地区映射表
    REGION_TABLE = LIEPIN_REGION_TABLE

    # ==========================================
    # URL 配置
    # ==========================================

    # 网站首页 URL（供中间件获取 Cookie 使用）
    site_url = "https://www.liepin.com/"

    # 搜索 API URL
    SEARCH_API_URL = "https://api-c.liepin.com/api/com.liepin.search4c.pc-search"

    # 职位详情页 URL 模板
    JOB_DETAIL_URL = "https://www.liepin.com/job/{job_id}.shtml"

    # 公司详情页 URL 模板
    COMPANY_DETAIL_URL = "https://www.liepin.com/company/{company_id}/"

    # ==========================================
    # 搜索参数配置
    # ==========================================

    # 每页职位数量
    PAGE_SIZE = 40

    # 搜索排序方式：0=默认, 1=最新, 2=薪资
    SORT_DEFAULT = 0
    SORT_LATEST = 1
    SORT_SALARY = 2

    @staticmethod
    def is_logged_in(page) -> bool:
        """
        检查猎聘网站是否已登录。
        通过检测页面上是否存在已登录用户信息来判断。

        Args:
            page: DrissionPage ChromiumPage 实例

        Returns:
            bool: 是否已登录
        """
        try:
            # 方式1：检查用户头像或昵称
            user_info = page.ele("xpath://div[contains(@class,'user-info')]", timeout=3)
            if user_info:
                return True

            # 方式2：检查是否有用户名元素
            username = page.ele("xpath://a[contains(@class,'username')]", timeout=3)
            if username:
                return True

            # 方式3：检查页面是否有退出登录按钮
            logout = page.ele("xpath://a[contains(text(),'退出') or contains(text(),'Logout')]", timeout=3)
            if logout:
                return True

        except Exception:
            pass

        return False

    def __init__(self, keyword=None, region=None, max_page=None, *args, **kwargs):
        """
        初始化爬虫

        Args:
            keyword: 搜索关键词，多个关键词用逗号分隔
            region: 目标地区，多个地区用逗号分隔（支持城市名、省份名、地区ID）
            max_page: 最大翻页数
        """
        super().__init__(*args, **kwargs)

        if keyword:
            self.search_keywords = [k.strip() for k in keyword.split(",")]
        if region:
            region_inputs = [r.strip() for r in region.split(",")]
            self.target_regions = self.region_factory.resolve_all(region_inputs)
        if max_page:
            self.max_page = int(max_page)

        # 初始化日志：显示当前配置
        logger.info(f"搜索关键词: {self.search_keywords}")
        logger.info(f"目标地区: {[(name, rid) for name, rid in self.target_regions]}")
        logger.info(f"最大翻页数: {self.max_page}")

    def start_requests(self):
        """
        生成初始请求
        先访问首页确认 Cookie 有效，然后开始搜索职位
        """
        logger.info("开始爬取猎聘职位信息")
        yield Request(
            url=self.site_url,
            callback=self.parse,
            dont_filter=True,
            meta={"dont_redirect": False},
        )

    def parse(self, response):
        """
        解析首页，验证 Cookie 后开始搜索职位
        通过搜索 API 逐页获取职位列表
        """
        logger.info(f"首页响应状态码: {response.status}")
        logger.info(f"首页 URL: {response.url}")

        # 检查是否需要登录
        if self._is_login_required(response):
            logger.warning("检测到需要登录，Cookie 可能已失效")
            return

        # Cookie 有效，开始搜索职位
        for keyword in self.search_keywords:
            for region_name, region_id in self.target_regions:
                for page in range(1, self.max_page + 1):
                    yield self._build_search_request(
                        keyword=keyword,
                        region_name=region_name,
                        page=page,
                    )

    @staticmethod
    def _is_login_required(response) -> bool:
        """
        检测响应是否为登录页面（Cookie 已失效）

        Returns:
            bool: 是否需要重新登录
        """
        # 检查 URL 是否包含登录相关路径
        url_lower = response.url.lower()
        if any(kw in url_lower for kw in ("login", "passport", "signin", "register")):
            return True

        # 检查页面 title 是否包含登录相关文字
        try:
            page_title = response.css("title::text").get("")
            if any(kw in page_title for kw in ("用户登录", "登录", "Login", "Sign In")):
                return True

            # 检查页面是否存在登录表单组件
            login_indicators = [
                'div[class*="login-box"]',
                'div[id*="passport"]',
                'div[id*="login"]',
                'form[action*="login"]',
                'input[name*="password"]',
            ]
            for selector in login_indicators:
                if response.css(selector):
                    return True
        except ValueError:
            pass

        return False

    def _build_search_request(self, keyword: str, region_name: str, page: int) -> Request:
        """
        构建猎聘搜索 API 请求

        猎聘搜索 API 使用 POST 请求，请求体为 JSON 格式：
        {
            "data": {
                "mainSearchPcConditionForm": {
                    "city": 410,
                    "dq": 410,
                    "currentPage": 0,
                    "pageSize": 40,
                    "key": "Python"
                }
            }
        }
        """
        # 构建请求体
        body = {
            "data": {
                "mainSearchPcConditionForm": {
                    "city": 410,
                    "dq": 410,
                    "currentPage": page - 1,  # 猎聘页码从0开始
                    "pageSize": self.PAGE_SIZE,
                    "key": keyword,
                },
            },
        }

        return Request(
            url=self.SEARCH_API_URL,
            method="POST",
            body=json.dumps(body, ensure_ascii=False),
            callback=self.parse_job_list,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.liepin.com",
                "Referer": f"https://www.liepin.com/zhaopin/?key={quote(keyword)}",
                "X-Requested-With": "XMLHttpRequest",
            },
            meta={
                "keyword": keyword,
                "region_name": region_name,
                "page": page,
            },
            dont_filter=True,
        )
