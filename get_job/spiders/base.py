"""BaseSpider - 项目统一爬虫基类

所有平台爬虫都应继承此基类，提供通用的属性和方法：
- name: 爬虫名称（子类必须覆盖）
- site_url: 站点首页 URL
- is_logged_in(): 登录状态检测
- init_search_params(): 初始化搜索参数
- log_start_info(): 打印启动信息
"""

import logging
from datetime import datetime
from typing import List, Tuple

import scrapy
from scrapy.http import Request

from get_job.items import BaseJobItem, BaseCompanyItem
from get_job.region import get_search_keywords_from_env, get_target_regions_from_env, get_max_page_from_env
from get_job.utils.spider_helpers import is_login_required

logger = logging.getLogger(__name__)


class BaseSpider(scrapy.Spider):
    """招聘爬虫统一基类

    封装了所有平台爬虫的通用逻辑，包括：
    - 登录状态检测（is_logged_in）
    - 搜索参数初始化（keyword / region / max_page）
    - 启动信息日志
    - 通用 start_requests 流程
    - 元数据填充（crawl_time / source_platform）

    子类需要实现：
    - name: 爬虫名称
    - site_url: 站点首页 URL
    - source_platform: 来源平台中文名
    - parse(): 首页解析逻辑
    """

    # ---- 子类必须覆盖的属性 ----
    name = "base"  # 子类必须覆盖，如 "xiaoyuan", "liepin"
    site_url: str = ""  # 站点首页 URL
    source_platform: str = ""  # 来源平台中文名，如 "智联校园招聘"

    # ---- 搜索相关属性（子类可覆盖） ----
    region_factory = None  # 地区工厂，子类需赋值
    search_keywords: List[str] = []
    target_regions: List[Tuple[str, int]] = []
    max_page: int = 1

    # ---- 通用设置 ----
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    # ==========================================
    # 登录状态检测
    # ==========================================

    @staticmethod
    def is_logged_in(page) -> bool:
        """检测浏览器页面是否已登录

        使用 DrissionPage 的 page 对象检测登录状态。
        子类应覆盖此方法以实现平台特定的登录检测逻辑。

        Args:
            page: DrissionPage 的页面对象

        Returns:
            bool: True 表示已登录，False 表示未登录
        """
        try:
            # 通用检测：查找常见的已登录元素
            for xpath in [
                "//div[contains(@class,'user-info')]",
                "//a[contains(@class,'username')]",
                "//img[contains(@class,'avatar')]",
            ]:
                if page.ele(f"xpath:{xpath}", timeout=3):
                    return True
        except Exception:
            pass
        return False

    # ==========================================
    # 初始化
    # ==========================================

    def __init__(self, keyword=None, region=None, max_page=None, *args, **kwargs):
        """初始化爬虫，支持通过命令行参数覆盖搜索配置

        Args:
            keyword: 逗号分隔的搜索关键词，覆盖环境变量配置
            region: 逗号分隔的地区名称，覆盖环境变量配置
            max_page: 最大翻页数，覆盖环境变量配置
        """
        super().__init__(*args, **kwargs)
        self._init_search_params(keyword, region, max_page)

    def _init_search_params(self, keyword=None, region=None, max_page=None):
        """初始化搜索参数，优先使用命令行参数，否则使用环境变量

        Args:
            keyword: 逗号分隔的搜索关键词
            region: 逗号分隔的地区名称
            max_page: 最大翻页数
        """
        if keyword:
            self.search_keywords = [k.strip() for k in keyword.split(",")]
        elif not self.search_keywords:
            self.search_keywords = get_search_keywords_from_env()

        if region and self.region_factory:
            self.target_regions = self.region_factory.resolve_all([r.strip() for r in region.split(",")])
        elif not self.target_regions and self.region_factory:
            self.target_regions = get_target_regions_from_env(self.region_factory)

        if max_page:
            self.max_page = int(max_page)
        elif self.max_page <= 0:
            self.max_page = get_max_page_from_env()

    # ==========================================
    # 启动流程
    # ==========================================

    def start_requests(self):
        """通用启动入口，访问站点首页后交由子类 parse 处理"""
        logger.info(f"开始爬取 {self.source_platform} 职位信息")
        yield Request(
            url=self.site_url,
            callback=self.parse,
            dont_filter=True,
            meta={"dont_redirect": False},
        )

    def log_start_info(self):
        """打印爬虫启动信息，便于调试和确认配置"""
        logger.info(f"[{self.name}] 搜索关键词: {self.search_keywords}")
        logger.info(f"[{self.name}] 目标地区: {[(n, r) for n, r in self.target_regions]}")
        logger.info(f"[{self.name}] 最大翻页数: {self.max_page}")

    # ==========================================
    # 元数据填充
    # ==========================================

    def fill_job_metadata(self, item: BaseJobItem) -> BaseJobItem:
        """为职位 Item 填充通用元数据字段

        Args:
            item: 职位 Item 实例

        Returns:
            填充了元数据的 Item
        """
        if not item.get("crawl_time"):
            item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not item.get("source_platform"):
            item["source_platform"] = self.source_platform
        return item

    def fill_company_metadata(self, item: BaseCompanyItem) -> BaseCompanyItem:
        """为公司 Item 填充通用元数据字段

        Args:
            item: 公司 Item 实例

        Returns:
            填充了元数据的 Item
        """
        if not item.get("crawl_time"):
            item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not item.get("source_platform"):
            item["source_platform"] = self.source_platform
        return item

    # ==========================================
    # 登录检测辅助
    # ==========================================

    def check_login_required(self, response) -> bool:
        """检测响应是否要求登录，若需要则记录警告

        Args:
            response: Scrapy Response 对象

        Returns:
            bool: True 表示需要登录，False 表示正常
        """
        if is_login_required(response):
            logger.warning(f"[{self.name}] 检测到需要登录，Cookie 可能已失效")
            return True
        return False
