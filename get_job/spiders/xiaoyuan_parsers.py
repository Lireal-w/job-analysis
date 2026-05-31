"""
智联校园招聘爬虫 - 解析器模块

包含职位列表解析、API 解析、职位详情解析、公司详情解析等 Mixin 类。
通过 Mixin 模式将解析逻辑从 Spider 类中拆分出来，保持代码清晰。
"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import scrapy
from scrapy.http import Request

from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem
from get_job.spiders.xiaoyuan_utils import (
    extract_ssr_data,
    extract_auth_params,
    extract_full_text,
    save_debug_page,
)

logger = logging.getLogger(__name__)


class JobListParserMixin:
    """职位列表解析 Mixin - 处理搜索结果列表页"""

    def parse_job_list(self, response):
        """
        解析职位列表页（搜索页）
        第一页从 SSR 数据提取，并提取认证参数用于后续 API 分页请求。
        """
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        region_id = response.meta.get("region_id", 0)
        page = response.meta.get("page", 1)

        logger.info(f"正在解析职位列表 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")

        # 检查是否被重定向到登录页面
        if self._is_login_required(response):
            logger.warning(f"职位列表页返回登录页面 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")
            return

        # 优先从 SSR 内嵌数据提取
        ssr_data = extract_ssr_data(response)
        if ssr_data:
            yield from self._parse_ssr_job_list(ssr_data, keyword, region_name)

            # 从 SSR 数据和 Cookie 中提取认证参数，用于后续 API 分页请求
            auth_params = extract_auth_params(ssr_data, response)
            if auth_params and self.max_page > 1:
                # 检查是否还有更多页（通过总数判断）
                position_data = ssr_data.get("position", {})
                position_state = position_data.get("positionState", {})
                total_count = position_state.get("count", 0)
                if not total_count:
                    total_count = position_data.get("count", 0)
                page_size = position_state.get("pageSize", 20)
                if not page_size:
                    page_size = 20
                max_available_page = (total_count + page_size - 1) // page_size if total_count else self.max_page

                for next_page in range(2, min(self.max_page, max_available_page) + 1):
                    yield self._build_api_request(
                        keyword=keyword,
                        region_id=region_id,
                        region_name=region_name,
                        page=next_page,
                        auth_params=auth_params,
                    )
            return

        # 尝试解析纯 JSON 响应（API 接口返回）
        try:
            json_data = json.loads(response.text)
            if isinstance(json_data, dict):
                yield from self._parse_json_job_list(json_data, keyword, region_name)
                return
        except (json.JSONDecodeError, TypeError):
            pass

        # 回退：解析 HTML 响应 - 使用 CSS 选择器
        sel = self.SEARCH_SELECTORS
        job_items = response.css(sel["job_item"])

        if not job_items:
            logger.warning(f"未找到职位列表项 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")
            save_debug_page(response, f"job_list_{keyword}_{region_name}_{page}")
            return

        logger.info(f"找到 {len(job_items)} 个职位项 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")

        for job_item in job_items:
            item = XiaoyuanJobItem()

            detail_link = job_item.css(f'{sel["job_link"]}::attr(href)').get()
            if not detail_link:
                continue

            detail_url = urljoin(response.url, detail_link)

            item["job_title"] = job_item.css(f'{sel["job_title"]}::text').get("").strip()
            item["company_name"] = job_item.css(f'{sel["company_name"]}::text').get("").strip()
            item["salary_desc"] = job_item.css(f'{sel["salary"]}::text').get("").strip()
            item["work_city"] = job_item.css(f'{sel["location"]}::text').get("").strip()
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

    def _parse_ssr_job_list(self, ssr_data: dict, keyword: str, region_name: str):
        """
        解析 Vue SSR 内嵌的职位列表数据

        数据路径: ssr_data -> position -> positionState -> list
        """
        position_data = ssr_data.get("position", {})
        position_state = position_data.get("positionState", {})
        job_list = position_state.get("list", [])

        if not job_list:
            logger.warning(f"SSR 数据中未找到职位列表 - 关键词: {keyword}, 地区: {region_name}")
            return

        logger.info(f"SSR 数据中找到 {len(job_list)} 个职位 - 关键词: {keyword}, 地区: {region_name}")

        for job in job_list:
            item = XiaoyuanJobItem()

            # 基本信息
            item["job_id"] = str(job.get("jobId", ""))
            item["job_title"] = job.get("name", "")
            item["job_category"] = job.get("subJobTypeLevelName", "")

            # 公司信息
            item["company_name"] = job.get("companyName", "")
            item["company_id"] = job.get("companyNumber", "")
            item["company_type"] = job.get("property", "")
            item["company_scale"] = job.get("companySize", "")
            item["company_industry"] = job.get("industryName", "")

            # 薪资与地点
            item["salary_desc"] = job.get("salary60", "") or job.get("salaryReal", "")
            item["work_city"] = job.get("workCity", region_name)
            item["work_district"] = job.get("cityDistrict", "")

            # 职位详情
            item["education"] = job.get("education", "")
            item["experience"] = job.get("workingExp", "")
            item["welfare"] = " | ".join(job.get("welfareLabel", []))
            item["publish_date"] = job.get("publishTime", "")
            item["recruit_num"] = job.get("recruitNumber", None)

            # 从 campusJobDetail 提取更详细信息
            campus_detail = job.get("campusJobDetail", {})
            if campus_detail:
                if not item["company_scale"]:
                    item["company_scale"] = campus_detail.get("orgSizeName", "")
                if not item["company_type"]:
                    item["company_type"] = campus_detail.get("orgTypeName", "")
                if not item["company_industry"]:
                    item["company_industry"] = campus_detail.get("industryName", "")

            # 从 jobDetailData.position 提取更详细信息
            job_detail = job.get("jobDetailData", {})
            if job_detail:
                position_detail = job_detail.get("position", {})
                if position_detail:
                    base = position_detail.get("base", {})
                    if base:
                        if not item["salary_desc"]:
                            item["salary_desc"] = base.get("salary", "")
                        if not item["education"]:
                            item["education"] = base.get("education", "")
                        if not item["experience"]:
                            item["experience"] = base.get("positionWorkingExp", "")
                        item["job_type"] = base.get("workType", "")

                    desc = position_detail.get("desc", {})
                    if desc:
                        item["job_description"] = desc.get("description", "")
                        item["welfare"] = " | ".join(desc.get("welfareTags", [])) or item.get("welfare", "")

                    work_loc = position_detail.get("workLocation", {})
                    if work_loc:
                        item["work_address"] = work_loc.get("address", "")
                        if not item["work_city"]:
                            item["work_city"] = work_loc.get("positionWorkCity", "")

            # 来源 URL
            number = job.get("number", "")
            if number:
                item["source_url"] = f"https://xiaoyuan.zhaopin.com/position/{number}"

            # 元数据
            item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["source_platform"] = "智联校园招聘"

            yield item

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


class ApiParserMixin:
    """API 解析 Mixin - 处理第2页起的 API POST 请求"""

    def _build_api_request(self, keyword: str, region_id: int, region_name: str,
                           page: int, auth_params: dict) -> Request:
        """
        构建第2页起的 API POST 请求

        API URL: https://cgate.zhaopin.com/positionbusiness/searchrecommend/searchPositions
        请求方式: POST JSON
        """
        import uuid

        # 生成 x-zp-page-request-id
        page_request_id = str(uuid.uuid4()).replace("-", "") + str(int(datetime.now().timestamp() * 1000)) + str(
            int(uuid.uuid4().int % 1000000)
        )

        # 构建请求体
        city_ids = str(region_id)
        body = {
            "identity": "1",
            "filterMinSalary": 1,
            "version": "8.2.6",
            "pageIndex": page,
            "pageSize": 20,
            "cvNumber": auth_params["cvNumber"],
            "order": auth_params["order"],
            "at": auth_params["at"],
            "rt": auth_params["rt"],
            "S_SOU_WORK_CITY": city_ids,
            "S_SOU_FULL_INDEX": keyword,
            "d": auth_params["d"],
            "channel": "xiaoyuan",
            "platform": "14",
        }

        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://xiaoyuan.zhaopin.com",
            "Referer": "https://xiaoyuan.zhaopin.com/",
            "x-zp-at": auth_params["at"],
            "x-zp-rt": auth_params["rt"],
            "x-zp-business-system": "40",
            "x-zp-platform": "14",
        }

        url = f"{self.SEARCH_API_URL}?x-zp-page-request-id={page_request_id}&x-zp-client-id={auth_params['d']}"

        logger.info(f"构建 API 请求 - 关键词: {keyword}, 地区: {region_name}(ID:{region_id}), 页码: {page}")

        return Request(
            url=url,
            method="POST",
            body=json.dumps(body, ensure_ascii=False),
            headers=headers,
            callback=self.parse_api_job_list,
            meta={
                "keyword": keyword,
                "region_name": region_name,
                "region_id": region_id,
                "page": page,
            },
            dont_filter=True,
        )

    def parse_api_job_list(self, response):
        """
        解析 API 返回的职位列表 JSON 数据

        API 响应格式:
        {
            "data": { "list": [...], "count": N, "isEndPage": 0/1 },
            "statusCode": 200
        }
        """
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        page = response.meta.get("page", 1)

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.error(f"API 响应 JSON 解析失败 - 页码: {page}, 错误: {e}")
            save_debug_page(response, f"api_job_list_{keyword}_{region_name}_{page}")
            return

        status_code = result.get("statusCode", 0)
        if status_code != 200:
            logger.warning(f"API 返回非200状态 - statusCode: {status_code}, 页码: {page}")
            save_debug_page(response, f"api_job_list_{keyword}_{region_name}_{page}")
            return

        data = result.get("data", {})
        job_list = data.get("list", [])
        is_end_page = data.get("isEndPage", 0)

        if not job_list:
            logger.warning(f"API 返回空职位列表 - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")
            return

        logger.info(f"API 返回 {len(job_list)} 个职位 - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")

        for job in job_list:
            item = self._build_job_item_from_api(job, keyword, region_name)
            if item:
                yield item

        if is_end_page == 1:
            logger.info(f"API 返回 isEndPage=1，已到最后一页 - 关键词: {keyword}, 地区: {region_name}")

    @staticmethod
    def _build_job_item_from_api(job: dict, keyword: str, region_name: str):
        """从 API 返回的职位数据构建 Item（数据结构与 SSR 的 list 项相同）"""
        item = XiaoyuanJobItem()

        # 基本信息
        item["job_id"] = str(job.get("jobId", ""))
        item["job_title"] = job.get("name", "")
        item["job_category"] = job.get("subJobTypeLevelName", "")

        # 工作类型
        item["job_type"] = job.get("workType", "")

        # 公司信息
        item["company_name"] = job.get("companyName", "")
        item["company_id"] = job.get("companyNumber", "")
        item["company_type"] = job.get("property", "") or job.get("propertyName", "")
        item["company_scale"] = job.get("companySize", "")
        item["company_industry"] = job.get("industryName", "")

        # 薪资
        item["salary_desc"] = job.get("salary60", "") or job.get("salaryReal", "")

        # 地点
        item["work_city"] = job.get("workCity", "")
        item["work_district"] = job.get("cityDistrict", "")

        # 地址
        work_location = job.get("jobDetailData", {}).get("position", {}).get("workLocation", {})
        item["work_address"] = work_location.get("address", "")

        # 职位详情
        item["education"] = job.get("education", "")
        item["experience"] = job.get("workingExp", "")
        item["publish_date"] = job.get("publishTime", "")
        item["recruit_num"] = job.get("recruitNumber", 0)

        # 职位描述
        description = ""
        job_detail_data = job.get("jobDetailData", {})
        if job_detail_data:
            position_desc = job_detail_data.get("position", {}).get("desc", {})
            description = position_desc.get("description", "")
        item["job_description"] = description

        # 技能标签
        skill_labels = [s.get("name", "") for s in job.get("jobSkillTags", []) if s.get("name")]
        item["skills"] = skill_labels

        # 福利
        welfare_labels = job.get("welfareLabel", [])
        item["welfare"] = ", ".join(welfare_labels) if isinstance(welfare_labels, list) else str(welfare_labels)

        # 来源 URL
        number = job.get("number", "")
        if number:
            item["source_url"] = f"https://xiaoyuan.zhaopin.com/position/{number}"
        else:
            item["source_url"] = ""

        # 元数据
        item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item["source_platform"] = "智联校园招聘"

        return item


class JobDetailParserMixin:
    """职位详情解析 Mixin"""

    # 职位详情页选择器
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

    def parse_job_detail(self, response):
        """解析职位详情页"""
        item = response.meta.get("item", XiaoyuanJobItem())
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")

        logger.info(f"正在解析职位详情 - {item.get('job_title', 'Unknown')}")

        sel = self.JOB_DETAIL_SELECTORS

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

        # 职位描述
        job_desc = response.css(sel["job_description"])
        if job_desc:
            item["job_description"] = extract_full_text(job_desc)
        else:
            item["job_description"] = ""

        # 任职要求
        job_req = response.css(sel["job_requirements"])
        if job_req:
            item["job_requirement"] = extract_full_text(job_req)
        else:
            item["job_requirement"] = ""

        # 福利待遇
        if not item.get("welfare"):
            welfare_items = response.css(f'{sel["welfare"]}::text').getall()
            item["welfare"] = " | ".join([w.strip() for w in welfare_items if w.strip()])

        # 工作地址
        if not item.get("work_address"):
            item["work_address"] = response.css(f'{sel["location"]}::text').get("").strip()

        # 设置来源 URL
        item["source_url"] = response.url
        item["source_platform"] = "智联校园招聘"

        yield item

        # 提取公司详情链接
        company_url = response.css(f'{sel["company_name"]}::attr(href)').get()
        if not company_url:
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


class CompanyDetailParserMixin:
    """公司详情解析 Mixin"""

    # 公司详情页选择器
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

    def parse_company_detail(self, response):
        """解析公司详情页"""
        item = XiaoyuanCompanyItem()

        sel = self.COMPANY_DETAIL_SELECTORS

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

        # 公司简介
        company_desc = response.css(sel["company_description"])
        if company_desc:
            item["company_description"] = extract_full_text(company_desc)
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
