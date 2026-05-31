"""
智联校园招聘爬虫
爬取 https://xiaoyuan.zhaopin.com/ 的职位信息

工作流程：
1. Spider 启动时，DrissionPageCookieMiddleware 会自动启动浏览器登录获取 Cookie
2. 使用获取到的 Cookie 发起请求，爬取职位列表页
3. 第一页从 SSR 数据提取，第二页起通过 API POST 请求获取
4. 解析职位列表，提取职位详情链接
5. 访问职位详情页，提取完整职位信息
6. 数据通过 Pipeline 进行清洗、去重和存储
"""

import logging
from urllib.parse import urlencode
from typing import List, Tuple

import scrapy
from scrapy.http import Request

from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem
from get_job.region import (
    XIAOYUAN_REGION_TABLE,
    create_xiaoyuan_region_factory,
    get_search_keywords_from_env,
    get_target_regions_from_env,
    get_max_page_from_env,
)
from get_job.spiders.xiaoyuan_parsers import (
    JobListParserMixin,
    ApiParserMixin,
    JobDetailParserMixin,
    CompanyDetailParserMixin,
)

logger = logging.getLogger(__name__)


class XiaoyuanSpider(
    JobListParserMixin,
    ApiParserMixin,
    JobDetailParserMixin,
    CompanyDetailParserMixin,
    scrapy.Spider,
):
    """智联校园招聘爬虫"""

    name = "xiaoyuan"
    allowed_domains = ["xiaoyuan.zhaopin.com", "zhaopin.com", "cgate.zhaopin.com"]
    start_urls = ["https://xiaoyuan.zhaopin.com/search/index"]

    # 自定义设置
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    # 地区策略工厂（智联校园招聘专用）
    region_factory = create_xiaoyuan_region_factory()

    # 搜索关键词（优先从 .env 读取，否则使用默认值）
    search_keywords = get_search_keywords_from_env()

    # 目标地区列表：[(地区名称, 地区ID), ...]（优先从 .env 读取，否则使用默认值）
    target_regions: List[Tuple[str, int]] = get_target_regions_from_env(region_factory)

    # 最大翻页数（优先从 .env 读取，否则使用默认值）
    max_page = get_max_page_from_env()

    # 智联校园招聘地区映射表（供外部查询使用）
    REGION_TABLE = XIAOYUAN_REGION_TABLE

    # ==========================================
    # URL 配置
    # ==========================================

    # 搜索页 URL
    SEARCH_URL = "https://xiaoyuan.zhaopin.com/search/index"

    # 职位搜索 API URL（第2页起使用）
    SEARCH_API_URL = "https://cgate.zhaopin.com/positionbusiness/searchrecommend/searchPositions"

    # 公司详情页 URL 模板
    COMPANY_DETAIL_URL = "https://www.zhaopin.com/companydetail/{company_id}"

    # ==========================================
    # 搜索页选择器（被 parse_job_list 和 parse_company_detail 共用）
    # ==========================================
    SEARCH_SELECTORS = {
        "job_item": "div.job-item",
        "job_title": "div.job-item h3 a",
        "job_link": "div.job-item h3 a",
        "company_name": "div.job-item div.company-name",
        "salary": "div.job-item span.salary",
        "location": "div.job-item span.location",
        "publish_time": "div.job-item span.publish-time",
        "education": "div.job-item span.education",
        "experience": "div.job-item span.experience",
    }

    @staticmethod
    def is_logged_in(page) -> bool:
        """
        检查智联校园招聘网站是否已登录。
        通过检测页面上是否存在已登录用户头像来判断。

        Args:
            page: DrissionPage ChromiumPage 实例

        Returns:
            bool: 是否已登录
        """
        LOGGED_IN_XPATH = "//div[@class='user-info']//img[@class='avatar']/@src"

        try:
            avatar_src = page.ele(f"xpath:{LOGGED_IN_XPATH}", timeout=3)
            if avatar_src:
                return True

            user_info = page.ele("xpath://div[@class='user-info']", timeout=3)
            if user_info:
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

    # 网站首页 URL（供中间件获取 Cookie 使用）
    site_url = "https://xiaoyuan.zhaopin.com/"

    def start_requests(self):
        """
        生成初始请求
        先访问搜索页确认 Cookie 有效，然后开始搜索职位
        """
        logger.info("开始爬取智联校园招聘职位信息")
        yield Request(
            url=self.SEARCH_URL,
            callback=self.parse,
            dont_filter=True,
            meta={"dont_redirect": False},
        )

    def parse(self, response):
        """
        解析首页，验证 Cookie 后开始搜索职位
        第一页使用 SSR 页面请求，第二页起使用 API POST 请求
        """
        logger.info(f"首页响应状态码: {response.status}")
        logger.info(f"首页 URL: {response.url}")

        # 检查是否需要登录（多种检测方式）
        if self._is_login_required(response):
            logger.warning("检测到需要登录，Cookie 可能已失效")
            return

        # Cookie 有效，开始搜索职位
        for keyword in self.search_keywords:
            for region_name, region_id in self.target_regions:
                # 第一页：使用 SSR 页面请求
                url = self._build_search_url(keyword, region_id, 1)
                yield Request(
                    url=url,
                    callback=self.parse_job_list,
                    meta={
                        "keyword": keyword,
                        "region_name": region_name,
                        "region_id": region_id,
                        "page": 1,
                    },
                    dont_filter=True,
                )

    @staticmethod
    def _is_login_required(response) -> bool:
        """
        检测响应是否为登录页面（Cookie 已失效）

        Returns:
            bool: 是否需要重新登录
        """
        # 方式1：检查 URL 是否包含登录相关路径
        url_lower = response.url.lower()
        if any(kw in url_lower for kw in ("login", "passport", "signin")):
            return True

        # 方式2：检查页面 title 是否包含登录相关文字
        try:
            page_title = response.css("title::text").get("")
            if any(kw in page_title for kw in ("用户登录", "登录", "Login", "Sign In")):
                return True

            # 方式3：检查页面是否存在登录表单组件
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
            # JSON 响应不支持 CSS 选择器
            pass

        return False

    def _build_search_url(self, keyword: str, region_id: int, page: int) -> str:
        """
        构建搜索 URL

        智联校园招聘的搜索 URL 格式：
        https://xiaoyuan.zhaopin.com/search/index?keyword=Python&city=530&pageIndex=1
        """
        params = {
            "keyword": keyword,
            "city": region_id,
            "pageIndex": page,
        }
        return f"{self.SEARCH_URL}?{urlencode(params)}"
