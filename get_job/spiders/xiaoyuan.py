"""智联校园招聘爬虫 - Spider / Parsers / Utils 合并模块"""

import json
import logging
import re
import uuid
from datetime import datetime
from urllib.parse import urlencode, urljoin
from typing import List, Tuple

from scrapy.http import Request

from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem
from get_job.region import XIAOYUAN_REGION_TABLE, create_xiaoyuan_region_factory
from get_job.spiders.base import BaseSpider
from get_job.utils.spider_helpers import extract_ssr_data, extract_full_text, save_debug_page

logger = logging.getLogger(__name__)

# ==================== Utils ====================

XIAOYUAN_SSR_VAR = "window.__INITIAL_DATA__"


def extract_xiaoyuan_ssr_data(response):
    return extract_ssr_data(response, variable_name=XIAOYUAN_SSR_VAR)


def extract_auth_params(ssr_data, response):
    """从 Cookie 和 SSR 数据中提取 API 分页请求所需的认证参数"""
    cookies = {}
    for cookie in response.headers.getlist("Set-Cookie"):
        parts = cookie.decode("utf-8", errors="ignore").split(";")[0]
        if "=" in parts:
            k, v = parts.split("=", 1)
            cookies[k.strip()] = v.strip()
    req_cookies = {}
    cookie_header = response.request.headers.get("Cookie", b"").decode("utf-8", errors="ignore")
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            req_cookies[k.strip()] = v.strip()
    at = req_cookies.get("at", "") or cookies.get("at", "")
    rt = req_cookies.get("rt", "") or cookies.get("rt", "")
    rp = ssr_data.get("position", {}).get("requestParams", {})
    bd = ssr_data.get("basedata", {})
    ui = ssr_data.get("main", {}).get("userInfo", {})
    d = rp.get("d", "") or bd.get("d", "")
    if not d:
        d = req_cookies.get("x-zp-client-id", "") or cookies.get("x-zp-client-id", "")
    resumes = ui.get("resumes", [])
    cv_number = resumes[0].get("number", "") if resumes and isinstance(resumes, list) else ""
    if not at or not rt:
        logger.warning(f"未找到完整认证参数 at/rt")
        return None
    params = {"at": at, "rt": rt, "d": d, "order": rp.get("order", 12), "cvNumber": cv_number}
    logger.info(f"提取到认证参数: at={at[:8]}..., rt={rt[:8]}...")
    return params


# ==================== Spider ====================

class XiaoyuanSpider(BaseSpider):
    """智联校园招聘爬虫"""
    name = "xiaoyuan"
    source_platform = "智联校园招聘"
    allowed_domains = ["xiaoyuan.zhaopin.com", "zhaopin.com", "cgate.zhaopin.com"]
    start_urls = ["https://xiaoyuan.zhaopin.com/search/index"]
    custom_settings = {"DOWNLOAD_DELAY": 2, "CONCURRENT_REQUESTS_PER_DOMAIN": 2}
    region_factory = create_xiaoyuan_region_factory()
    search_keywords = []
    target_regions: List[Tuple[str, int]] = []
    max_page = 0
    REGION_TABLE = XIAOYUAN_REGION_TABLE
    site_url = "https://xiaoyuan.zhaopin.com/"
    SEARCH_URL = "https://xiaoyuan.zhaopin.com/search/index"
    SEARCH_API_URL = "https://cgate.zhaopin.com/positionbusiness/searchrecommend/searchPositions"
    COMPANY_DETAIL_URL = "https://www.zhaopin.com/companydetail/{company_id}"
    SEARCH_SELECTORS = {
        "job_item": "div.job-item", "job_title": "div.job-item h3 a", "job_link": "div.job-item h3 a",
        "company_name": "div.job-item div.company-name", "salary": "div.job-item span.salary",
        "location": "div.job-item span.location", "publish_time": "div.job-item span.publish-time",
        "education": "div.job-item span.education", "experience": "div.job-item span.experience",
    }
    JOB_DETAIL_SELECTORS = {
        "job_title": "h1.job-title", "salary": "div.job-info span.salary", "location": "div.job-info span.location",
        "experience": "div.job-info span.experience", "education": "div.job-info span.education",
        "company_name": "div.company-info a.company-name", "company_scale": "div.company-info span.scale",
        "company_industry": "div.company-info span.industry", "job_description": "div.job-description",
        "job_requirements": "div.job-requirements", "welfare": "div.job-welfare span",
    }
    COMPANY_DETAIL_SELECTORS = {
        "company_name": "h1.company-name", "company_logo": "div.company-header img.logo",
        "company_scale": "div.company-info span.scale", "company_founded": "div.company-info span.founded",
        "company_industry": "div.company-info span.industry", "company_address": "div.company-info span.address",
        "company_description": "div.company-description", "job_list": "div.job-list div.job-item",
    }

    @staticmethod
    def is_logged_in(page) -> bool:
        """智联校园招聘平台登录状态检测"""
        try:
            if page.ele("xpath://div[@class='user-info']//img[@class='avatar']/@src", timeout=3):
                return True
            if page.ele("xpath://div[@class='user-info']", timeout=3):
                return True
        except Exception:
            pass
        return False

    def __init__(self, keyword=None, region=None, max_page=None, *args, **kwargs):
        super().__init__(keyword=keyword, region=region, max_page=max_page, *args, **kwargs)
        self.log_start_info()

    def start_requests(self):
        logger.info("开始爬取智联校园招聘职位信息")
        yield Request(url=self.SEARCH_URL, callback=self.parse, dont_filter=True, meta={"dont_redirect": False})

    def parse(self, response):
        logger.info(f"首页响应状态码: {response.status}, URL: {response.url}")
        if self.check_login_required(response):
            return
        for keyword in self.search_keywords:
            for region_name, region_id in self.target_regions:
                yield Request(url=self._build_search_url(keyword, region_id, 1),
                              callback=self.parse_job_list,
                              meta={"keyword": keyword, "region_name": region_name, "region_id": region_id, "page": 1},
                              dont_filter=True)

    def _build_search_url(self, keyword, region_id, page):
        return f"{self.SEARCH_URL}?{urlencode({'keyword': keyword, 'city': region_id, 'pageIndex': page})}"

    # ---------- 职位列表解析 ----------

    def parse_job_list(self, response):
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        region_id = response.meta.get("region_id", 0)
        page = response.meta.get("page", 1)
        if self.check_login_required(response):
            logger.warning(f"职位列表页返回登录页 - {keyword}/{region_name}")
            return
        logger.info(f"职位列表页响应状态码: {response.status}, URL: {response.url}")
        ssr_data = extract_xiaoyuan_ssr_data(response)
        if ssr_data:
            yield from self._parse_ssr_job_list(ssr_data, keyword, region_name)
            auth = extract_auth_params(ssr_data, response)
            if auth and self.max_page > 1:
                pos = ssr_data.get("position", {})
                ps = pos.get("positionState", {})
                total = ps.get("count", 0) or pos.get("count", 0)
                ps_size = ps.get("pageSize", 20) or 20
                max_page = (total + ps_size - 1) // ps_size if total else self.max_page
                for p in range(2, min(self.max_page, max_page) + 1):
                    yield self._build_api_request(keyword, region_id, region_name, p, auth)
            return
        try:
            jd = json.loads(response.text)
            if isinstance(jd, dict):
                yield from self._parse_json_job_list(jd, keyword, region_name)
                return
        except (json.JSONDecodeError, TypeError):
            pass
        sel = self.SEARCH_SELECTORS
        job_items = response.css(sel["job_item"])
        if not job_items:
            save_debug_page(response, f"job_list_{keyword}_{region_name}_{page}")
            return
        for ji in job_items:
            link = ji.css(f'{sel["job_link"]}::attr(href)').get()
            if not link:
                continue
            item = XiaoyuanJobItem()
            item["job_title"] = ji.css(f'{sel["job_title"]}::text').get("").strip()
            item["company_name"] = ji.css(f'{sel["company_name"]}::text').get("").strip()
            item["salary_desc"] = ji.css(f'{sel["salary"]}::text').get("").strip()
            item["work_city"] = ji.css(f'{sel["location"]}::text').get("").strip()
            item["education"] = ji.css(f'{sel["education"]}::text').get("").strip()
            item["experience"] = ji.css(f'{sel["experience"]}::text').get("").strip()
            item["source_url"] = urljoin(response.url, link)
            m = re.search(r'/(\d+)', link)
            if m:
                item["job_id"] = m.group(1)
            yield Request(url=urljoin(response.url, link), callback=self.parse_job_detail,
                          meta={"item": item, "keyword": keyword, "region_name": region_name, "region_id": region_id},
                          dont_filter=True)

    def _parse_ssr_job_list(self, ssr_data, keyword, region_name):
        job_list = ssr_data.get("position", {}).get("positionState", {}).get("list", [])
        if not job_list:
            logger.warning(f"SSR 数据中未找到职位 - {keyword}/{region_name}")
            return
        logger.info(f"SSR 找到 {len(job_list)} 个职位 - {keyword}/{region_name}")
        for job in job_list:
            item = XiaoyuanJobItem()
            item["job_id"] = str(job.get("jobId", ""))
            item["job_title"] = job.get("name", "")
            item["job_category"] = job.get("subJobTypeLevelName", "")
            item["company_name"] = job.get("companyName", "")
            item["company_id"] = job.get("companyNumber", "")
            item["company_type"] = job.get("property", "")
            item["company_scale"] = job.get("companySize", "")
            item["company_industry"] = job.get("industryName", "")
            item["salary_desc"] = job.get("salary60", "") or job.get("salaryReal", "")
            item["work_city"] = job.get("workCity", region_name)
            item["work_district"] = job.get("cityDistrict", "")
            item["education"] = job.get("education", "")
            item["experience"] = job.get("workingExp", "")
            item["welfare"] = " | ".join(job.get("welfareLabel", []))
            item["publish_date"] = job.get("publishTime", "")
            item["recruit_num"] = job.get("recruitNumber", None)
            cd = job.get("campusJobDetail", {})
            if cd:
                if not item["company_scale"]: item["company_scale"] = cd.get("orgSizeName", "")
                if not item["company_type"]: item["company_type"] = cd.get("orgTypeName", "")
                if not item["company_industry"]: item["company_industry"] = cd.get("industryName", "")
            jd = job.get("jobDetailData", {})
            if jd:
                pos = jd.get("position", {})
                if pos:
                    base = pos.get("base", {})
                    if base:
                        if not item["salary_desc"]: item["salary_desc"] = base.get("salary", "")
                        if not item["education"]: item["education"] = base.get("education", "")
                        if not item["experience"]: item["experience"] = base.get("positionWorkingExp", "")
                        item["job_type"] = base.get("workType", "")
                    desc = pos.get("desc", {})
                    if desc:
                        item["job_description"] = desc.get("description", "")
                        item["welfare"] = " | ".join(desc.get("welfareTags", [])) or item.get("welfare", "")
                    wl = pos.get("workLocation", {})
                    if wl:
                        item["work_address"] = wl.get("address", "")
                        if not item["work_city"]: item["work_city"] = wl.get("positionWorkCity", "")
            number = job.get("job_id", "")
            if number:
                item["source_url"] = f"https://xiaoyuan.zhaopin.com/job/{number}"
            item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["source_platform"] = "智联校园招聘"
            number = job.get("number", "")
            request = None
            if number:
                
                item["source_url"] = f"https://xiaoyuan.zhaopin.com/job/{number}"
                logger.info(f"准备发出请求 - {item['source_url']}")
                request = Request(
                    url=item["source_url"], 
                    callback=self.parse_job_detail,
                    meta={"item": item, "keyword": keyword, "region_name": region_name}, 
                    dont_filter=True
                )
            else:
                item["source_url"] = ""
            # yield item
            if request:
                yield request

    def _parse_json_job_list(self, json_data, keyword, region_name):
        data = json_data.get("data", {})
        job_list = data.get("list", []) or data.get("result", []) or json_data.get("resultList", [])
        for job in job_list:
            item = XiaoyuanJobItem()
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
            job_id = item["job_id"]
            if job_id:
                item["source_url"] = f"https://www.zhaopin.com/companydetail/{job_id}"
                yield Request(url=item["source_url"], callback=self.parse_job_detail,
                              meta={"item": item, "keyword": keyword, "region_name": region_name}, dont_filter=True)
            else:
                item["source_url"] = ""
                item["source_platform"] = "智联校园招聘"
                yield item

    # ---------- API 分页请求 ----------

    def _build_api_request(self, keyword, region_id, region_name, page, auth_params):
        page_request_id = str(uuid.uuid4()).replace("-", "") + str(int(datetime.now().timestamp() * 1000)) + str(int(uuid.uuid4().int % 1000000))
        body = {"identity": "1", "filterMinSalary": 1, "version": "8.2.6", "pageIndex": page, "pageSize": 20,
                "cvNumber": auth_params["cvNumber"], "order": auth_params["order"], "at": auth_params["at"],
                "rt": auth_params["rt"], "S_SOU_WORK_CITY": str(region_id), "S_SOU_FULL_INDEX": keyword,
                "d": auth_params["d"], "channel": "xiaoyuan", "platform": "14"}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                   "Origin": "https://xiaoyuan.zhaopin.com", "Referer": "https://xiaoyuan.zhaopin.com/",
                   "x-zp-at": auth_params["at"], "x-zp-rt": auth_params["rt"],
                   "x-zp-business-system": "40", "x-zp-platform": "14"}
        url = f"{self.SEARCH_API_URL}?x-zp-page-request-id={page_request_id}&x-zp-client-id={auth_params['d']}"
        return Request(url=url, method="POST", body=json.dumps(body, ensure_ascii=False), headers=headers,
                       callback=self.parse_api_job_list,
                       meta={"keyword": keyword, "region_name": region_name, "region_id": region_id, "page": page},
                       dont_filter=True)

    def parse_api_job_list(self, response):
        keyword, region_name, page = response.meta.get("keyword", ""), response.meta.get("region_name", ""), response.meta.get("page", 1)
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError:
            save_debug_page(response, f"api_job_list_{keyword}_{region_name}_{page}")
            return
        if result.get("statusCode", 0) != 200:
            save_debug_page(response, f"api_job_list_{keyword}_{region_name}_{page}")
            return
        job_list = result.get("data", {}).get("list", [])
        if not job_list:
            return
        logger.info(f"API 返回 {len(job_list)} 个职位 - {keyword}/{region_name}/{page}")
        for job in job_list:
            item = self._build_job_item_from_api(job, keyword, region_name)
            if item:
                yield item

    @staticmethod
    def _build_job_item_from_api(job, keyword, region_name):
        item = XiaoyuanJobItem()
        item["job_id"] = str(job.get("jobId", ""))
        item["job_title"] = job.get("name", "")
        item["job_category"] = job.get("subJobTypeLevelName", "")
        item["job_type"] = job.get("workType", "")
        item["company_name"] = job.get("companyName", "")
        item["company_id"] = job.get("companyNumber", "")
        item["company_type"] = job.get("property", "") or job.get("propertyName", "")
        item["company_scale"] = job.get("companySize", "")
        item["company_industry"] = job.get("industryName", "")
        item["salary_desc"] = job.get("salary60", "") or job.get("salaryReal", "")
        item["work_city"] = job.get("workCity", "")
        item["work_district"] = job.get("cityDistrict", "")
        item["work_address"] = job.get("jobDetailData", {}).get("position", {}).get("workLocation", {}).get("address", "")
        item["education"] = job.get("education", "")
        item["experience"] = job.get("workingExp", "")
        item["publish_date"] = job.get("publishTime", "")
        item["recruit_num"] = job.get("recruitNumber", 0)
        jd = job.get("jobDetailData", {})
        item["job_description"] = jd.get("position", {}).get("desc", {}).get("description", "") if jd else ""
        item["skills"] = [s.get("name", "") for s in job.get("jobSkillTags", []) if s.get("name")]
        wl = job.get("welfareLabel", [])
        item["welfare"] = ", ".join(wl) if isinstance(wl, list) else str(wl)
        number = job.get("number", "")
        item["source_url"] = f"https://xiaoyuan.zhaopin.com/position/{number}" if number else ""
        item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item["source_platform"] = "智联校园招聘"
        return item

    # ---------- 职位详情解析 ----------

    def parse_job_detail(self, response):
        item = response.meta.get("item", XiaoyuanJobItem())
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        sel = self.JOB_DETAIL_SELECTORS
        if not item.get("job_id"):
            m = re.search(r'/companydetail/(\d+)', response.url)
            item["job_id"] = m.group(1) if m else ""
        for field, key in [("job_title", "job_title"), ("salary_desc", "salary"), ("work_city", "location"),
                           ("experience", "experience"), ("education", "education"),
                           ("company_name", "company_name"), ("company_scale", "company_scale"),
                           ("company_industry", "company_industry")]:
            if not item.get(field):
                item[field] = response.css(f'{sel[key]}::text').get("").strip()
        jd = response.css(sel["job_description"])
        item["job_description"] = extract_full_text(jd) if jd else ""
        jr = response.css(sel["job_requirements"])
        item["job_requirement"] = extract_full_text(jr) if jr else ""
        if not item.get("welfare"):
            wi = response.css(f'{sel["welfare"]}::text').getall()
            item["welfare"] = " | ".join(w.strip() for w in wi if w.strip())
        if not item.get("work_address"):
            item["work_address"] = response.css(f'{sel["location"]}::text').get("").strip()
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"
        yield item
        save_debug_page(response, f"job_detail_{response.url.split('/')[-1]}")
        company_url = response.css(f'{sel["company_name"]}::attr(href)').get()
        if not company_url and item.get("company_id"):
            company_url = self.COMPANY_DETAIL_URL.format(company_id=item["company_id"])
        if company_url:
            yield Request(url=urljoin(response.url, company_url), callback=self.parse_company_detail,
                          meta={"region_name": region_name, "company_name": item.get("company_name", "")}, dont_filter=True)

    # ---------- 公司详情解析 ----------

    def parse_company_detail(self, response):
        item = XiaoyuanCompanyItem()
        sel = self.COMPANY_DETAIL_SELECTORS
        
        # 1. 基础信息提取
        m = re.search(r'/companydetail/(\d+)', response.url)
        item["company_id"] = m.group(1) if m else ""
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"
        item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 2. 优先尝试从 SSR 数据中提取公司信息（精准且稳定）
        ssr_data = extract_xiaoyuan_ssr_data(response)
        if ssr_data:
            comp = ssr_data.get("companyDetail", ssr_data.get("company", {}))
            if comp:
                item["company_name"] = comp.get("companyName", "")
                item["company_logo"] = comp.get("companyLogo", "")
                item["company_scale"] = comp.get("companySize", comp.get("orgSizeName", ""))
                item["company_type"] = comp.get("companyType", comp.get("orgTypeName", ""))
                item["company_industry"] = comp.get("industryName", "")
                item["company_address"] = comp.get("companyAddress", "")
                item["company_description"] = comp.get("companyDescription", comp.get("compDesc", ""))
                item["company_website"] = comp.get("companyWebsite", "")
                item["company_short_name"] = comp.get("companyShortName", "")

        # 3. 降级策略：若 SSR 无数据或字段缺失，使用更精准的 CSS 选择器补全
        if not item.get("company_name"):
            item["company_name"] = response.css('div.company-header h1::text, h1.company-name::text').get("").strip()
        if not item.get("company_logo"):
            item["company_logo"] = response.css('div.company-header img.logo::attr(src), img.company-logo::attr(src)').get("")
        if not item.get("company_scale"):
            item["company_scale"] = response.css('div.company-info span.scale::text, li:contains("规模") span::text').get("").strip()
        if not item.get("company_type"):
            item["company_type"] = response.css('div.company-info span.type::text, li:contains("类型") span::text').get("").strip()
        if not item.get("company_industry"):
            item["company_industry"] = response.css('div.company-info span.industry::text, li:contains("行业") span::text').get("").strip()
        if not item.get("company_address"):
            item["company_address"] = response.css('div.company-info span.address::text, li:contains("地址") span::text').get("").strip()
        if not item.get("company_description"):
            cd = response.css('div.company-description, div.comp-description')
            item["company_description"] = extract_full_text(cd) if cd else ""
        if not item.get("company_website"):
            item["company_website"] = response.css('a[class*="website"]::attr(href), a[class*="url"]::attr(href)').get("")

        save_debug_page(response, f"company_detail_{item['company_id']}")
        yield item
        
        # 4. 提取公司页内的在招职位列表
        job_items = response.css('div.job-list div.job-item, div.position-list div.position-item')
        if job_items:
            ss = self.SEARCH_SELECTORS
            for ji in job_items:
                link = ji.css(f'{ss["job_link"]}::attr(href), a::attr(href)').get()
                if not link:
                    continue
                job = XiaoyuanJobItem()
                job["job_title"] = ji.css(f'{ss["job_title"]}::text, a::text').get("").strip()
                job["company_name"] = item.get("company_name", "")
                job["company_id"] = item.get("company_id", "")
                job["salary_desc"] = ji.css(f'{ss["salary"]}::text, span.salary::text').get("").strip()
                job["work_city"] = response.meta.get("region_name", "")
                job["source_url"] = urljoin(response.url, link)
                jm = re.search(r'/(\d+)', link)
                if jm:
                    job["job_id"] = jm.group(1)
                yield Request(url=urljoin(response.url, link), callback=self.parse_job_detail,
                              meta={"item": job, "keyword": "", "region_name": response.meta.get("region_name", "")},
                              dont_filter=True)

