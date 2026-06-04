"""猎聘爬虫 - Spider / Parsers / Utils 合并模块"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import quote
from typing import List, Tuple

import scrapy
from scrapy.http import Request

from get_job.items import LiepinJobItem, LiepinCompanyItem
from get_job.region import get_search_keywords_from_env, get_target_regions_from_env, get_max_page_from_env
from get_job.region.liepin_strategy import create_liepin_region_factory
from get_job.region.liepin_table import LIEPIN_REGION_TABLE
from get_job.utils.spider_helpers import extract_ssr_data, extract_json_data, parse_salary, is_login_required, save_debug_page

logger = logging.getLogger(__name__)

# ==================== Utils ====================

LIEPIN_SSR_VAR = "window.__INITIAL_STATE__"


def extract_liepin_ssr_data(response):
    return extract_ssr_data(response, variable_name=LIEPIN_SSR_VAR)


def parse_liepin_salary(salary_desc: str):
    """解析猎聘薪资，万单位按年薪折算月薪"""
    result_min, result_max = parse_salary(salary_desc)
    if salary_desc and "万" in salary_desc.strip() and result_min is not None:
        wan_match = re.match(r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*万', salary_desc.strip().split('·')[0].strip())
        if wan_match:
            min_val, max_val = int(float(wan_match.group(1)) * 10000), int(float(wan_match.group(2)) * 10000)
            bonus_match = re.search(r'[·\-\s](\d+)薪', salary_desc)
            annual_months = int(bonus_match.group(1)) if bonus_match else None
            min_val, max_val = round(min_val / 12), round(max_val / 12)
            if annual_months and annual_months > 12:
                min_val, max_val = round(min_val * annual_months / 12), round(max_val * annual_months / 12)
            return min_val, max_val
    return result_min, result_max


# ==================== Spider ====================

class LiepinSpider(scrapy.Spider):
    """猎聘招聘爬虫"""
    name = "liepin"
    allowed_domains = ["liepin.com", "api-c.liepin.com", "capi.liepin.com"]
    start_urls = ["https://www.liepin.com/"]
    custom_settings = {"DOWNLOAD_DELAY": 3, "CONCURRENT_REQUESTS_PER_DOMAIN": 2}
    region_factory = create_liepin_region_factory()
    search_keywords = get_search_keywords_from_env()
    target_regions: List[Tuple[str, int]] = get_target_regions_from_env(region_factory)
    max_page = get_max_page_from_env()
    REGION_TABLE = LIEPIN_REGION_TABLE
    site_url = "https://www.liepin.com/"
    SEARCH_API_URL = "https://api-c.liepin.com/api/com.liepin.search4c.pc-search"
    PAGE_SIZE = 40

    @staticmethod
    def is_logged_in(page) -> bool:
        try:
            for xpath in [
                "//div[contains(@class,'user-info')]",
                "//a[contains(@class,'username')]",
                "//a[contains(text(),'退出') or contains(text(),'Logout')]",
            ]:
                if page.ele(f"xpath:{xpath}", timeout=3):
                    return True
        except Exception:
            pass
        return False

    def __init__(self, keyword=None, region=None, max_page=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if keyword:
            self.search_keywords = [k.strip() for k in keyword.split(",")]
        if region:
            self.target_regions = self.region_factory.resolve_all([r.strip() for r in region.split(",")])
        if max_page:
            self.max_page = int(max_page)
        logger.info(f"搜索关键词: {self.search_keywords}")
        logger.info(f"目标地区: {[(n, r) for n, r in self.target_regions]}")
        logger.info(f"最大翻页数: {self.max_page}")

    def start_requests(self):
        logger.info("开始爬取猎聘职位信息")
        yield Request(url=self.site_url, callback=self.parse, dont_filter=True, meta={"dont_redirect": False})

    def parse(self, response):
        logger.info(f"首页响应状态码: {response.status}, URL: {response.url}")
        if is_login_required(response):
            logger.warning("检测到需要登录，Cookie 可能已失效")
            return
        for keyword in self.search_keywords:
            for region_name, _ in self.target_regions:
                for page in range(1, self.max_page + 1):
                    yield self._build_search_request(keyword, region_name, page)

    def _build_search_request(self, keyword, region_name, page):
        body = {"data": {"mainSearchPcConditionForm": {
            "city": 410, "dq": 410, "currentPage": page - 1, "pageSize": self.PAGE_SIZE, "key": keyword,
        }}}
        return Request(
            url=self.SEARCH_API_URL, method="POST",
            body=json.dumps(body, ensure_ascii=False),
            callback=self.parse_job_list,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.liepin.com",
                "Referer": f"https://www.liepin.com/zhaopin/?key={quote(keyword)}",
                "X-Requested-With": "XMLHttpRequest",
            },
            meta={"keyword": keyword, "region_name": region_name, "page": page},
            dont_filter=True,
        )

    # ---------- 职位列表解析 ----------

    def parse_job_list(self, response):
        keyword, region_name, page = response.meta.get("keyword", ""), response.meta.get("region_name", ""), response.meta.get("page", 1)
        api_data = extract_json_data(response)
        if not api_data:
            logger.warning(f"猎聘 API 数据解析失败 - {keyword}/{region_name}/{page}")
            save_debug_page(response, f"liepin_api_{keyword}_{region_name}_{page}")
            return
        if api_data.get("flag", 0) != 1:
            logger.warning(f"猎聘 API 返回错误: {api_data.get('msg', '未知错误')}")
            return
        data = api_data.get("data", {})
        inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        job_list = (inner or data).get("jobList", [])
        if not job_list:
            logger.warning(f"猎聘 API 未返回职位 - {keyword}/{region_name}/{page}")
            return
        logger.info(f"猎聘返回 {len(job_list)} 个职位 - {keyword}/{region_name}/{page}")
        for job in job_list:
            item = self._parse_api_job_item(job, keyword, region_name)
            if item:
                job_id = item.get("job_id", "")
                if job_id:
                    yield Request(url=f"https://www.liepin.com/job/{job_id}.shtml",
                                  callback=self.parse_job_detail,
                                  meta={"item": item, "keyword": keyword, "region_name": region_name},
                                  dont_filter=True)
                else:
                    yield item

    def _parse_api_job_item(self, job, keyword, region_name):
        item = LiepinJobItem()
        j = job.get("job", job)
        item["job_id"] = str(j.get("jobId", j.get("id", "")))
        item["job_title"] = j.get("title", j.get("jobName", ""))
        item["job_category"] = j.get("jobCategory", j.get("categoryName", ""))
        item["job_type"] = j.get("jobType", "")
        salary_desc = j.get("salary", j.get("salaryDesc", ""))
        item["salary_desc"] = salary_desc
        s_min, s_max = parse_liepin_salary(salary_desc)
        if s_min: item["salary_min"] = s_min
        if s_max: item["salary_max"] = s_max
        item["work_city"] = j.get("city", j.get("cityName", region_name))
        item["work_district"] = j.get("district", j.get("areaName", ""))
        item["education"] = j.get("edu", j.get("eduLevel", ""))
        item["experience"] = j.get("workYear", j.get("workExp", ""))
        item["keywords"] = j.get("labels", j.get("keyWords", []))
        item["publish_date"] = j.get("publishTime", j.get("startTime", ""))
        item["is_headhunt"] = j.get("isHeadhunt", False)
        c = job.get("comp", {})
        if c:
            item["company_id"] = str(c.get("compId", c.get("companyId", "")))
            item["company_name"] = c.get("compName", c.get("companyName", ""))
            item["company_type"] = c.get("compType", c.get("companyType", ""))
            item["company_scale"] = c.get("compScale", c.get("companySize", ""))
            item["company_industry"] = c.get("compIndustry", c.get("industryName", ""))
            item["company_stage"] = c.get("compStage", c.get("financingStage", ""))
        else:
            item["company_id"] = str(j.get("compId", j.get("companyId", "")))
            item["company_name"] = j.get("compName", j.get("companyName", ""))
            item["company_type"] = j.get("compType", "")
            item["company_scale"] = j.get("compScale", "")
            item["company_industry"] = j.get("compIndustry", "")
            item["company_stage"] = j.get("compStage", "")
        if item["job_id"]:
            item["source_url"] = f"https://www.liepin.com/job/{item['job_id']}.shtml"
        item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item["source_platform"] = "猎聘"
        return item

    # ---------- 职位详情解析 ----------

    def parse_job_detail(self, response):
        item = response.meta.get("item")
        if not item:
            return
        ssr_data = extract_ssr_data(response, variable_name=LIEPIN_SSR_VAR)
        if ssr_data:
            self._enrich_item_from_ssr(item, ssr_data)
        else:
            self._enrich_item_from_html(item, response)
        yield item

    def _enrich_item_from_ssr(self, item, ssr_data):
        job_detail = ssr_data.get("jobDetail", {})
        j = job_detail.get("job") or ssr_data.get("job", {})
        if j:
            if not item.get("job_description"):
                item["job_description"] = j.get("describe", j.get("jobDesc", ""))
            if not item.get("job_requirement"):
                item["job_requirement"] = j.get("require", j.get("jobRequire", ""))
            if not item.get("welfare"):
                w = j.get("welfare", j.get("benefit", ""))
                item["welfare"] = " | ".join(w) if isinstance(w, list) else w
            if not item.get("skills"):
                s = j.get("skills", j.get("skillLabels", []))
                item["skills"] = [x.strip() for x in s.split(",") if x.strip()] if isinstance(s, str) else s
            if not item.get("keywords"):
                l = j.get("labels", j.get("keyWords", []))
                item["keywords"] = [x.strip() for x in l.split(",") if x.strip()] if isinstance(l, str) else l
            if not item.get("work_address"):
                item["work_address"] = j.get("address", j.get("workAddress", ""))
            if not item.get("recruit_num"):
                item["recruit_num"] = j.get("recruitNum", None)
        comp = job_detail.get("comp", ssr_data.get("comp", {}))
        if comp and not item.get("company_description"):
            item["company_description"] = comp.get("compDesc", comp.get("description", ""))

    def _enrich_item_from_html(self, item, response):
        for field, selectors in [
            ("job_description", ["div.job-description div.content::text", "div.job-detail-section div.content::text"]),
            ("job_requirement", ["div.job-require div.content::text", "div.job-detail-section:nth-child(2) div.content::text"]),
            ("work_address", ["div.job-location span::text", "div.job-detail-address::text"]),
        ]:
            if not item.get(field):
                for sel in selectors:
                    v = response.css(sel).get("")
                    if v:
                        item[field] = v.strip()
                        break
        if not item.get("welfare"):
            wl = response.css("div.job-tags span::text").getall()
            if wl:
                item["welfare"] = " | ".join(w.strip() for w in wl if w.strip())

    # ---------- 公司详情解析 ----------

    def parse_company_detail(self, response):
        item = response.meta.get("item")
        if not item:
            return
        ssr_data = extract_ssr_data(response, variable_name=LIEPIN_SSR_VAR)
        if ssr_data:
            comp = ssr_data.get("compDetail", ssr_data.get("comp", {}))
            if comp:
                if not item.get("company_description"):
                    item["company_description"] = comp.get("compDesc", comp.get("description", ""))
                if not item.get("company_address"):
                    item["company_address"] = comp.get("address", "")
                if not item.get("company_website"):
                    item["company_website"] = comp.get("website", comp.get("compWebsite", ""))
                if not item.get("company_logo"):
                    item["company_logo"] = comp.get("logo", comp.get("compLogo", ""))
        else:
            for field, selectors in [
                ("company_description", ["div.company-description::text", "div.comp-description::text"]),
                ("company_address", ["div.company-address::text", "div.comp-address span::text"]),
            ]:
                if not item.get(field):
                    for sel in selectors:
                        v = response.css(sel).get("")
                        if v:
                            item[field] = v.strip()
                            break
        yield item
