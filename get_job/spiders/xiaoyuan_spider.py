"""
智联校园招聘爬虫
爬取 https://xiaoyuan.zhaopin.com/ 的职位信息

工作流程：
1. Spider 启动时，DrissionPageCookieMiddleware 会自动启动浏览器登录获取 Cookie
2. 使用获取到的 Cookie 发起请求，爬取职位列表页
3. 解析职位列表，提取职位详情链接
4. 访问职位详情页，提取完整职位信息
5. 数据通过 Pipeline 进行清洗、去重和存储
"""

import json
import logging
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlencode

import scrapy
from scrapy.http import Request, Response

from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem

logger = logging.getLogger(__name__)


class XiaoyuanSpider(scrapy.Spider):
    """智联校园招聘爬虫"""

    name = "xiaoyuan"
    allowed_domains = ["xiaoyuan.zhaopin.com", "zhaopin.com"]
    start_urls = ["https://xiaoyuan.zhaopin.com/"]

    # 自定义设置
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    # 搜索关键词（可根据需要修改）
    search_keywords = ["Python", "Java", "前端", "数据分析", "产品经理", "运营"]

    # 城市筛选（可根据需要修改）
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京"]

    # 最大翻页数
    max_page = 10

    def __init__(self, keyword=None, city=None, max_page=None, *args, **kwargs):
        """
        初始化爬虫

        Args:
            keyword: 搜索关键词，多个关键词用逗号分隔
            city: 城市名称，多个城市用逗号分隔
            max_page: 最大翻页数
        """
        super().__init__(*args, **kwargs)

        if keyword:
            self.search_keywords = [k.strip() for k in keyword.split(",")]
        if city:
            self.cities = [c.strip() for c in city.split(",")]
        if max_page:
            self.max_page = int(max_page)

    def start_requests(self):
        """
        生成初始请求
        先访问首页确认 Cookie 有效，然后开始搜索职位
        """
        # 先访问首页，验证 Cookie 是否有效
        yield Request(
            url="https://xiaoyuan.zhaopin.com/search/index",
            callback=self.parse_homepage,
            dont_filter=True,
            meta={"dont_redirect": False},
        )

    def parse_homepage(self, response):
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
            for city in self.cities:
                for page in range(1, self.max_page + 1):
                    url = self._build_search_url(keyword, city, page)
                    yield Request(
                        url=url,
                        callback=self.parse_job_list,
                        meta={
                            "keyword": keyword,
                            "city": city,
                            "page": page,
                        },
                        dont_filter=True,
                    )

    def _build_search_url(self, keyword: str, city: str, page: int) -> str:
        """
        构建搜索 URL

        智联校园招聘的搜索 URL 格式：
        https://xiaoyuan.zhaopin.com/search/jobs?keyword=Python&city=北京&pageNumber=1
        """
        params = {
            "keyword": keyword,
            "city": city,
            "pageNumber": page,
        }
        base_url = "https://xiaoyuan.zhaopin.com/search/jobs"
        return f"{base_url}?{urlencode(params)}"

    def parse_job_list(self, response):
        """
        解析职位列表页
        """
        keyword = response.meta.get("keyword", "")
        city = response.meta.get("city", "")
        page = response.meta.get("page", 1)

        logger.info(f"正在解析职位列表 - 关键词: {keyword}, 城市: {city}, 页码: {page}")

        # 尝试解析 JSON 响应（部分接口返回 JSON）
        try:
            json_data = json.loads(response.text)
            if isinstance(json_data, dict):
                yield from self._parse_json_job_list(json_data, keyword, city)
                return
        except (json.JSONDecodeError, TypeError):
            pass

        # 解析 HTML 响应
        # 职位列表项选择器（根据实际页面结构调整）
        job_items = response.css('div.job-list-item, div[class*="job-item"], div[class*="position-item"]')

        if not job_items:
            # 尝试其他选择器
            job_items = response.css('a[href*="/jobs/"], a[href*="/job/"], div[class*="search-result"]')

        if not job_items:
            logger.warning(f"未找到职位列表项 - 关键词: {keyword}, 城市: {city}, 页码: {page}")
            # 尝试保存页面用于调试
            self._save_debug_page(response, f"job_list_{keyword}_{city}_{page}")
            return

        for job_item in job_items:
            # 提取职位详情链接
            detail_url = job_item.css('a[href*="/jobs/"]::attr(href), a[href*="/job/"]::attr(href)').get()
            if not detail_url:
                detail_url = job_item.css("a::attr(href)").get()

            if detail_url:
                detail_url = urljoin(response.url, detail_url)

                # 先从列表页提取基本信息
                item = XiaoyuanJobItem()
                item["job_title"] = self._extract_text(job_item, [
                    'span[class*="job-name"]', 'div[class*="job-name"]',
                    'a[class*="job-title"]', 'h3', 'h4',
                    'span[class*="title"]', 'div[class*="title"]',
                ])
                item["company_name"] = self._extract_text(job_item, [
                    'span[class*="company"]', 'div[class*="company"]',
                    'a[class*="company"]', 'span[class*="corp"]',
                ])
                item["salary_desc"] = self._extract_text(job_item, [
                    'span[class*="salary"]', 'div[class*="salary"]',
                    'span[class*="pay"]', 'div[class*="pay"]',
                    'em[class*="salary"]',
                ])
                item["work_city"] = city
                item["source_url"] = detail_url

                yield Request(
                    url=detail_url,
                    callback=self.parse_job_detail,
                    meta={"item": item, "keyword": keyword, "city": city},
                    dont_filter=True,
                )

    def _parse_json_job_list(self, json_data: dict, keyword: str, city: str):
        """解析 JSON 格式的职位列表"""
        # 根据实际 API 响应结构调整
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
            item["work_city"] = job.get("city", job.get("workCity", city))
            item["work_district"] = job.get("district", job.get("workDistrict", ""))
            item["education"] = job.get("education", job.get("eduLevel", ""))
            item["experience"] = job.get("experience", job.get("workExp", ""))
            item["welfare"] = job.get("welfare", job.get("benefit", ""))
            item["publish_date"] = job.get("publishDate", job.get("createTime", ""))
            item["recruit_num"] = job.get("recruitNum", job.get("hireNum", ""))

            # 构建详情页 URL
            job_id = item["job_id"]
            if job_id:
                detail_url = f"https://xiaoyuan.zhaopin.com/jobs/{job_id}"
                item["source_url"] = detail_url

                yield Request(
                    url=detail_url,
                    callback=self.parse_job_detail,
                    meta={"item": item, "keyword": keyword, "city": city},
                    dont_filter=True,
                )
            else:
                item["source_url"] = ""
                item["source_platform"] = "智联校园招聘"
                yield item

    def parse_job_detail(self, response):
        """
        解析职位详情页
        """
        item = response.meta.get("item", XiaoyuanJobItem())
        keyword = response.meta.get("keyword", "")
        city = response.meta.get("city", "")

        logger.info(f"正在解析职位详情 - {item.get('job_title', 'Unknown')}")

        # 如果没有从列表页获取到基本信息，从详情页提取
        if not item.get("job_title"):
            item["job_title"] = self._extract_text(response, [
                'h1[class*="job"]', 'h1[class*="title"]', 'h1',
                'div[class*="job-name"]', 'span[class*="job-name"]',
            ])

        if not item.get("company_name"):
            item["company_name"] = self._extract_text(response, [
                'a[class*="company"]', 'span[class*="company"]',
                'div[class*="company-name"]', 'a[class*="corp"]',
            ])

        if not item.get("salary_desc"):
            item["salary_desc"] = self._extract_text(response, [
                'span[class*="salary"]', 'div[class*="salary"]',
                'em[class*="salary"]', 'span[class*="pay"]',
            ])

        # 从详情页提取更多字段
        # 职位ID
        if not item.get("job_id"):
            job_id = response.css('[data-job-id]::attr(data-job-id)').get()
            if not job_id:
                match = re.search(r'/jobs/(\d+)', response.url)
                job_id = match.group(1) if match else ""
            item["job_id"] = job_id

        # 学历要求
        if not item.get("education"):
            item["education"] = self._extract_text(response, [
                'span[class*="edu"]', 'div[class*="edu"]',
                'span[class*="education"]', 'li[class*="edu"]',
            ])

        # 经验要求
        if not item.get("experience"):
            item["experience"] = self._extract_text(response, [
                'span[class*="exp"]', 'div[class*="exp"]',
                'span[class*="experience"]', 'li[class*="exp"]',
            ])

        # 工作城市
        if not item.get("work_city"):
            item["work_city"] = self._extract_text(response, [
                'span[class*="city"]', 'div[class*="city"]',
                'span[class*="location"]', 'div[class*="location"]',
            ])

        # 工作地址
        if not item.get("work_address"):
            item["work_address"] = self._extract_text(response, [
                'span[class*="address"]', 'div[class*="address"]',
                'span[class*="work-addr"]', 'div[class*="work-addr"]',
            ])

        # 职位描述
        item["job_description"] = self._extract_text(response, [
            'div[class*="job-description"]', 'div[class*="job-desc"]',
            'div[class*="description"]', 'div[class*="desc-content"]',
            'div[class*="detail-content"]', 'div[class*="job-detail"]',
        ])

        # 任职要求
        item["job_requirement"] = self._extract_text(response, [
            'div[class*="requirement"]', 'div[class*="require"]',
            'div[class*="qualification"]', 'div[class*="job-require"]',
        ])

        # 技能要求
        skills = response.css(
            'div[class*="skill"] span::text, '
            'span[class*="tag"]::text, '
            'div[class*="keyword"] span::text, '
            'a[class*="tag"]::text'
        ).getall()
        item["skills"] = [s.strip() for s in skills if s.strip()]

        # 福利待遇
        if not item.get("welfare"):
            welfare = response.css(
                'div[class*="welfare"] span::text, '
                'span[class*="benefit"]::text, '
                'div[class*="tag-list"] span::text'
            ).getall()
            item["welfare"] = " | ".join([w.strip() for w in welfare if w.strip()])

        # 公司类型
        if not item.get("company_type"):
            item["company_type"] = self._extract_text(response, [
                'span[class*="company-type"]', 'div[class*="company-type"]',
                'span[class*="corp-type"]', 'div[class*="corp-type"]',
            ])

        # 公司规模
        if not item.get("company_scale"):
            item["company_scale"] = self._extract_text(response, [
                'span[class*="company-scale"]', 'div[class*="company-scale"]',
                'span[class*="corp-scale"]', 'div[class*="corp-scale"]',
            ])

        # 公司行业
        if not item.get("company_industry"):
            item["company_industry"] = self._extract_text(response, [
                'span[class*="industry"]', 'div[class*="industry"]',
                'a[class*="industry"]',
            ])

        # 发布日期
        if not item.get("publish_date"):
            item["publish_date"] = self._extract_text(response, [
                'span[class*="date"]', 'div[class*="date"]',
                'span[class*="time"]', 'div[class*="time"]',
                'span[class*="publish"]',
            ])

        # 招聘人数
        if not item.get("recruit_num"):
            item["recruit_num"] = self._extract_text(response, [
                'span[class*="recruit"]', 'div[class*="recruit"]',
                'span[class*="hire"]', 'div[class*="hire"]',
            ])

        # 设置来源 URL
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"

        yield item

        # 尝试提取公司详情链接，爬取公司信息
        company_url = response.css(
            'a[class*="company"]::attr(href), '
            'a[href*="/company/"]::attr(href), '
            'a[href*="/corp/"]::attr(href)'
        ).get()

        if company_url:
            company_url = urljoin(response.url, company_url)
            yield Request(
                url=company_url,
                callback=self.parse_company_detail,
                meta={"city": city},
                dont_filter=True,
            )

    def parse_company_detail(self, response):
        """
        解析公司详情页
        """
        item = XiaoyuanCompanyItem()

        # 公司ID
        company_id = response.css('[data-company-id]::attr(data-company-id)').get()
        if not company_id:
            match = re.search(r'/company/(\d+)', response.url)
            company_id = match.group(1) if match else ""
        item["company_id"] = company_id

        # 公司名称
        item["company_name"] = self._extract_text(response, [
            'h1[class*="company"]', 'h1[class*="corp"]',
            'div[class*="company-name"]', 'span[class*="company-name"]',
            'h1', 'h2',
        ])

        # 公司简称
        item["company_short_name"] = self._extract_text(response, [
            'span[class*="short-name"]', 'div[class*="short-name"]',
        ])

        # 公司类型
        item["company_type"] = self._extract_text(response, [
            'span[class*="company-type"]', 'div[class*="company-type"]',
            'span[class*="corp-type"]',
        ])

        # 公司规模
        item["company_scale"] = self._extract_text(response, [
            'span[class*="company-scale"]', 'div[class*="company-scale"]',
            'span[class*="corp-scale"]',
        ])

        # 公司行业
        item["company_industry"] = self._extract_text(response, [
            'span[class*="industry"]', 'div[class*="industry"]',
            'a[class*="industry"]',
        ])

        # 公司简介
        item["company_description"] = self._extract_text(response, [
            'div[class*="company-desc"]', 'div[class*="company-intro"]',
            'div[class*="corp-desc"]', 'div[class*="corp-intro"]',
            'div[class*="description"]', 'div[class*="intro"]',
        ])

        # 公司地址
        item["company_address"] = self._extract_text(response, [
            'span[class*="address"]', 'div[class*="address"]',
            'span[class*="location"]',
        ])

        # 公司网站
        item["company_website"] = response.css(
            'a[class*="website"]::attr(href), '
            'a[class*="url"]::attr(href)'
        ).get()

        # 公司Logo
        item["company_logo"] = response.css(
            'img[class*="logo"]::attr(src), '
            'img[class*="avatar"]::attr(src)'
        ).get()

        # 元数据
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"

        yield item

    @staticmethod
    def _extract_text(element, selectors: list) -> str:
        """
        使用多个 CSS 选择器尝试提取文本，返回第一个匹配的结果
        """
        for selector in selectors:
            text = element.css(f"{selector}::text").get()
            if text and text.strip():
                return text.strip()

            # 尝试获取所有子文本拼接
            texts = element.css(f"{selector} *::text").getall()
            if texts:
                combined = " ".join([t.strip() for t in texts if t.strip()])
                if combined:
                    return combined

        return ""

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
