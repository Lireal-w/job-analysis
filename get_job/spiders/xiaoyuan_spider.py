"""
智联校园招聘爬虫
爬取 https://xiaoyuan.zhaopin.com/ 的职位信息

工作流程：
1. Spider 启动时，DrissionPageCookieMiddleware 会自动启动浏览器登录获取 Cookie
2. 使用获取到的 Cookie 发起请求，爬取职位列表页
3. 解析职位列表，提取职位详情链接
4. 访问职位详情页，提取完整职位信息
5. 访问公司详情页，提取公司信息
6. 数据通过 Pipeline 进行清洗、去重和存储
"""

import json
import logging
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlencode
from typing import Dict, List, Tuple

import scrapy
from scrapy.http import Request, Response

from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem
from get_job.region import (
    RegionStrategyFactory,
    XIAOYUAN_REGION_TABLE,
    create_xiaoyuan_region_factory,
    get_search_keywords_from_env,
    get_target_regions_from_env,
    get_max_page_from_env,
)

logger = logging.getLogger(__name__)


class XiaoyuanSpider(scrapy.Spider):
    """智联校园招聘爬虫"""

    name = "xiaoyuan"
    allowed_domains = ["xiaoyuan.zhaopin.com", "zhaopin.com"]
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

    # 职位详情页 URL 模板

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
        # 登录检测用的 XPath（仅在此方法中使用）
        LOGGED_IN_XPATH = "//div[@class='user-info']//img[@class='avatar']/@src"
        
        try:
            # 检查已登录用户头像（精确 XPath）
            avatar_src = page.ele(
                f"xpath:{LOGGED_IN_XPATH}",
                timeout=3,
            )
            if avatar_src:
                return True

            # 备用检查：用户信息区域
            user_info = page.ele(
                "xpath://div[@class='user-info']",
                timeout=3,
            )
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

    def start_requests(self):
        """
        生成初始请求
        先访问搜索页确认 Cookie 有效，然后开始搜索职位
        """
        logger.info(f"开始爬取智联校园招聘职位信息")
        yield Request(
            url=self.SEARCH_URL,
            callback=self.parse_homepage,
            dont_filter=True,
            meta={"dont_redirect": False},
        )

    def parse(self, response):
        """
        解析首页，验证 Cookie 后开始搜索
        """
        logger.info(f"首页响应状态码: {response.status}")
        logger.info(f"首页 URL: {response.url}")

        # 检查是否被重定向到登录页面
        if "login" in response.url.lower():
            logger.warning("被重定向到登录页面，Cookie 可能无效，请重新登录")
            return

        # Cookie 有效，开始搜索职位
        for keyword in self.search_keywords:
            for region_name, region_id in self.target_regions:
                for page in range(1, self.max_page + 1):
                    url = self._build_search_url(keyword, region_id, page)
                    yield Request(
                        url=url,
                        callback=self.parse_job_list,
                        meta={
                            "keyword": keyword,
                            "region_name": region_name,
                            "region_id": region_id,
                            "page": page,
                        },
                        dont_filter=True,
                    )

    def _build_search_url(self, keyword: str, region_id: int, page: int) -> str:
        """
        构建搜索 URL

        智联校园招聘的搜索 URL 格式：
        https://xiaoyuan.zhaopin.com/search/index?keyword=Python&cityId=530&page=1

        支持参数：keyword, cityId, salary, experience, education, page
        """
        params = {
            "keyword": keyword,
            "cityId": region_id,
            "page": page,
        }
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    # ==========================================
    # 搜索页解析
    # ==========================================

    def parse_job_list(self, response):
        """
        解析职位列表页（搜索页）
        使用精确 CSS 选择器提取搜索页数据字段
        """
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        region_id = response.meta.get("region_id", 0)
        page = response.meta.get("page", 1)

        logger.info(f"正在解析职位列表 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")

        # 尝试解析 JSON 响应（部分接口返回 JSON）
        try:
            json_data = json.loads(response.text)
            if isinstance(json_data, dict):
                yield from self._parse_json_job_list(json_data, keyword, region_name)
                return
        except (json.JSONDecodeError, TypeError):
            pass

        # 解析 HTML 响应 - 使用精确 CSS 选择器
        sel = self.SEARCH_SELECTORS
        job_items = response.css(sel["job_item"])

        if not job_items:
            logger.warning(f"未找到职位列表项 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")
            self._save_debug_page(response, f"job_list_{keyword}_{region_name}_{page}")
            return

        logger.info(f"找到 {len(job_items)} 个职位项 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")

        for job_item in job_items:
            # 提取职位详情链接
            detail_link = job_item.css(f'{sel["job_link"]}::attr(href)').get()
            if not detail_link:
                continue

            detail_url = urljoin(response.url, detail_link)

            # 从搜索页提取基本信息
            item = XiaoyuanJobItem()

            # 搜索页数据字段
            item["job_title"] = job_item.css(f'{sel["job_title"]}::text').get("").strip()
            item["company_name"] = job_item.css(f'{sel["company_name"]}::text').get("").strip()
            item["salary_desc"] = job_item.css(f'{sel["salary"]}::text').get("").strip()
            item["work_city"] = job_item.css(f'{sel["location"]}::text').get("").strip() or region_name
            item["publish_date"] = job_item.css(f'{sel["publish_time"]}::text').get("").strip()
            item["education"] = job_item.css(f'{sel["education"]}::text').get("").strip()
            item["experience"] = job_item.css(f'{sel["experience"]}::text').get("").strip()
            item["source_url"] = detail_url

            # 从详情页 URL 提取 job_id
            job_id_match = re.search(r'/(\d+)', detail_link)
            if job_id_match:
                item["job_id"] = job_id_match.group(1)

            yield Request(
                url=detail_url,
                callback=self.parse_job_detail,
                meta={"item": item, "keyword": keyword, "region_name": region_name, "region_id": region_id},
                dont_filter=True,
            )

    def _parse_json_job_list(self, json_data: dict, keyword: str, region_name: str):
        """解析 JSON 格式的职位列表"""
        job_list = json_data.get("data", {}).get("list", [])
        if not job_list:
            job_list = json_data.get("data", {}).get("result", [])
        if not job_list:
            job_list = json_data.get("resultList", [])

        for job in job_list:
            item = XiaoyuanJobItem()

            # 从 JSON 中提取字段
            item["job_id"] = str(job.get("jobId", job.get("id", "")))
            item["job_title"] = job.get("jobName", job.get("title", job.get("positionName", "")))
            item["job_category"] = job.get("jobCategory", job.get("category", ""))
            item["company_id"] = str(job.get("companyId", job.get("corpId", "")))
            item["company_name"] = job.get("companyName", job.get("corpName", job.get("company", "")))
            item["company_type"] = job.get("companyType", job.get("corpType", ""))
            item["company_scale"] = job.get("companyScale", job.get("corpScale", ""))
            item["company_industry"] = job.get("industry", job.get("companyIndustry", ""))
            item["salary_desc"] = job.get("salary", job.get("salaryDesc", ""))
            item["salary_min"] = job.get("salaryMin", None)
            item["salary_max"] = job.get("salaryMax", None)
            item["work_city"] = job.get("city", job.get("workCity", region_name))
            item["work_district"] = job.get("district", job.get("workDistrict", ""))
            item["education"] = job.get("education", job.get("eduLevel", ""))
            item["experience"] = job.get("experience", job.get("workExp", ""))
            item["welfare"] = job.get("welfare", job.get("benefit", ""))
            item["publish_date"] = job.get("publishDate", job.get("createTime", ""))
            item["recruit_num"] = job.get("recruitNum", job.get("hireNum", ""))

            # 构建详情页 URL
            job_id = item["job_id"]
            if job_id:
                detail_url = f"https://www.zhaopin.com/companydetail/{job_id}"
                item["source_url"] = detail_url

                yield Request(
                    url=detail_url,
                    callback=self.parse_job_detail,
                    meta={"item": item, "keyword": keyword, "region_name": region_name},
                    dont_filter=True,
                )
            else:
                item["source_url"] = ""
                item["source_platform"] = "智联校园招聘"
                yield item

    # ==========================================
    # 职位详情页解析
    # ==========================================

    def parse_job_detail(self, response):
        """
        解析职位详情页
        使用精确 CSS 选择器提取职位详情页数据字段
        """
        # 职位详情页选择器（仅在此方法中使用）
        JOB_DETAIL_SELECTORS = {
            "job_title": "h1.job-title",
            "salary": "div.job-info span.salary",
            "location": "div.job-info span.location",
            "experience": "div.job-info span.experience",
            "education": "div.job-info span.education",
            "company_name": "div.company-info a.company-name",
            "company_scale": "div.company-info span.scale",
            "company_industry": "div.company-info span.industry",
            "job_description": "div.job-description",
            "job_requirements": "div.job-requirements",
            "welfare": "div.job-welfare span",
        }
        
        item = response.meta.get("item", XiaoyuanJobItem())
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")

        logger.info(f"正在解析职位详情 - {item.get('job_title', 'Unknown')}")

        sel = JOB_DETAIL_SELECTORS

        # 职位ID（从 URL 提取）
        if not item.get("job_id"):
            match = re.search(r'/companydetail/(\d+)', response.url)
            item["job_id"] = match.group(1) if match else ""

        # 职位名称
        if not item.get("job_title"):
            item["job_title"] = response.css(f'{sel["job_title"]}::text').get("").strip()

        # 薪资范围
        if not item.get("salary_desc"):
            item["salary_desc"] = response.css(f'{sel["salary"]}::text').get("").strip()

        # 工作地点
        if not item.get("work_city"):
            item["work_city"] = response.css(f'{sel["location"]}::text').get("").strip()

        # 工作经验
        if not item.get("experience"):
            item["experience"] = response.css(f'{sel["experience"]}::text').get("").strip()

        # 学历要求
        if not item.get("education"):
            item["education"] = response.css(f'{sel["education"]}::text').get("").strip()

        # 公司名称
        if not item.get("company_name"):
            item["company_name"] = response.css(f'{sel["company_name"]}::text').get("").strip()

        # 公司规模
        if not item.get("company_scale"):
            item["company_scale"] = response.css(f'{sel["company_scale"]}::text').get("").strip()

        # 行业领域
        if not item.get("company_industry"):
            item["company_industry"] = response.css(f'{sel["company_industry"]}::text').get("").strip()

        # 职位描述（提取完整文本，包含子元素）
        job_desc = response.css(sel["job_description"])
        if job_desc:
            item["job_description"] = self._extract_full_text(job_desc)
        else:
            item["job_description"] = ""

        # 任职要求（提取完整文本，包含子元素）
        job_req = response.css(sel["job_requirements"])
        if job_req:
            item["job_requirement"] = self._extract_full_text(job_req)
        else:
            item["job_requirement"] = ""

        # 福利待遇（多个 span 标签）
        if not item.get("welfare"):
            welfare_items = response.css(f'{sel["welfare"]}::text').getall()
            item["welfare"] = " | ".join([w.strip() for w in welfare_items if w.strip()])

        # 工作地址（详情页可能有更详细的地址）
        if not item.get("work_address"):
            item["work_address"] = response.css(f'{sel["location"]}::text').get("").strip()

        # 设置来源 URL
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"

        yield item

        # 提取公司详情链接，爬取公司信息
        company_url = response.css(f'{sel["company_name"]}::attr(href)').get()
        if not company_url:
            # 尝试从公司 ID 构建 URL
            if item.get("company_id"):
                company_url = self.COMPANY_DETAIL_URL.format(company_id=item["company_id"])

        if company_url:
            company_url = urljoin(response.url, company_url)
            yield Request(
                url=company_url,
                callback=self.parse_company_detail,
                meta={"region_name": region_name, "company_name": item.get("company_name", "")},
                dont_filter=True,
            )

    # ==========================================
    # 公司详情页解析
    # ==========================================

    def parse_company_detail(self, response):
        """
        解析公司详情页
        使用精确 CSS 选择器提取公司详情页数据字段
        """
        # 公司详情页选择器（仅在此方法中使用）
        COMPANY_DETAIL_SELECTORS = {
            "company_name": "h1.company-name",
            "company_logo": "div.company-header img.logo",
            "company_scale": "div.company-info span.scale",
            "company_founded": "div.company-info span.founded",
            "company_industry": "div.company-info span.industry",
            "company_address": "div.company-info span.address",
            "company_description": "div.company-description",
            "job_list": "div.job-list div.job-item",
        }
        
        item = XiaoyuanCompanyItem()

        sel = COMPANY_DETAIL_SELECTORS

        # 公司ID（从 URL 提取）
        match = re.search(r'/companydetail/(\d+)', response.url)
        item["company_id"] = match.group(1) if match else ""

        # 公司名称
        item["company_name"] = response.css(f'{sel["company_name"]}::text').get("").strip()

        # 公司Logo
        item["company_logo"] = response.css(f'{sel["company_logo"]}::attr(src)').get("")

        # 公司规模
        item["company_scale"] = response.css(f'{sel["company_scale"]}::text').get("").strip()

        # 公司类型
        item["company_type"] = ""

        # 行业领域
        item["company_industry"] = response.css(f'{sel["company_industry"]}::text').get("").strip()

        # 公司地址
        item["company_address"] = response.css(f'{sel["company_address"]}::text').get("").strip()

        # 公司简介（提取完整文本，包含子元素）
        company_desc = response.css(sel["company_description"])
        if company_desc:
            item["company_description"] = self._extract_full_text(company_desc)
        else:
            item["company_description"] = ""

        # 公司简称
        item["company_short_name"] = ""

        # 公司网站
        item["company_website"] = response.css(
            'a[class*="website"]::attr(href), '
            'a[class*="url"]::attr(href)'
        ).get("")

        # 元数据
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"

        yield item

        # 解析在招职位列表
        job_items = response.css(sel["job_list"])
        if job_items:
            search_sel = self.SEARCH_SELECTORS
            for job_item in job_items:
                detail_link = job_item.css(f'{search_sel["job_link"]}::attr(href)').get()
                if not detail_link:
                    continue

                detail_url = urljoin(response.url, detail_link)

                job = XiaoyuanJobItem()
                job["job_title"] = job_item.css(f'{search_sel["job_title"]}::text').get("").strip()
                job["company_name"] = item.get("company_name", "")
                job["company_id"] = item.get("company_id", "")
                job["salary_desc"] = job_item.css(f'{search_sel["salary"]}::text').get("").strip()
                job["work_city"] = response.meta.get("region_name", "")
                job["source_url"] = detail_url

                job_id_match = re.search(r'/(\d+)', detail_link)
                if job_id_match:
                    job["job_id"] = job_id_match.group(1)

                yield Request(
                    url=detail_url,
                    callback=self.parse_job_detail,
                    meta={"item": job, "keyword": "", "region_name": response.meta.get("region_name", "")},
                    dont_filter=True,
                )

    # ==========================================
    # 工具方法
    # ==========================================

    @staticmethod
    def _extract_full_text(element) -> str:
        """
        提取元素及其所有子元素的文本内容，并清理多余空白
        """
        texts = element.css('*::text').getall()
        combined = " ".join([t.strip() for t in texts if t.strip()])
        return re.sub(r'\s+', ' ', combined)

    @staticmethod
    def _save_debug_page(response, filename: str):
        """保存页面用于调试"""
        try:
            output_dir = "debug_pages"
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f"{filename}.html")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"调试页面已保存: {filepath}")
        except Exception as e:
            logger.error(f"保存调试页面失败: {e}")