
"""
猎聘爬虫 - 解析器模块

包含职位列表解析、职位详情解析、公司详情解析等 Mixin 类。
通过 Mixin 模式将解析逻辑从 Spider 类中拆分出来，保持代码清晰。
"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import scrapy
from scrapy.http import Request

from get_job.items import LiepinJobItem, LiepinCompanyItem
from get_job.spiders.liepin_utils import (
    extract_liepin_api_data,
    parse_liepin_salary,
    save_debug_page,
)

logger = logging.getLogger(__name__)


class JobListParserMixin:
    """职位列表解析 Mixin - 处理搜索结果列表页"""

    def parse_job_list(self, response):
        """
        解析猎聘职位搜索 API 的 JSON 响应

        猎聘搜索 API 返回格式：
        {
            "flag": 1,
            "data": {
                "data": {
                    "jobList": [...],
                    "totalCount": 100
                }
            }
        }
        """
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")
        page = response.meta.get("page", 1)

        logger.info(f"正在解析猎聘职位列表 - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")

        api_data = extract_liepin_api_data(response)
        if not api_data:
            logger.warning(f"猎聘 API 数据解析失败 - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")
            save_debug_page(response, f"liepin_api_{keyword}_{region_name}_{page}")
            return

        # 检查 API 返回状态
        flag = api_data.get("flag", 0)
        if flag != 1:
            logger.warning(f"猎聘 API 返回错误 (flag={flag}): {api_data.get('msg', '未知错误')}")
            return

        # 提取职位列表
        data_section = api_data.get("data", {})
        if isinstance(data_section, dict):
            inner_data = data_section.get("data", {})
            if isinstance(inner_data, dict):
                job_list = inner_data.get("jobList", [])
                total_count = inner_data.get("totalCount", 0)
            else:
                job_list = data_section.get("jobList", [])
                total_count = data_section.get("totalCount", 0)
        else:
            job_list = []
            total_count = 0

        if not job_list:
            logger.warning(f"猎聘 API 未返回职位列表 - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")
            return

        logger.info(f"猎聘 API 返回 {len(job_list)} 个职位 (总计: {total_count}) - 关键词: {keyword}, 地区: {region_name}, 页码: {page}")

        for job in job_list:
            item = self._parse_api_job_item(job, keyword, region_name)
            if item:
                # 获取职位详情
                job_id = item.get("job_id", "")
                if job_id:
                    detail_url = f"https://www.liepin.com/job/{job_id}.shtml"
                    yield Request(
                        url=detail_url,
                        callback=self.parse_job_detail,
                        meta={"item": item, "keyword": keyword, "region_name": region_name},
                        dont_filter=True,
                    )
                else:
                    yield item

    def _parse_api_job_item(self, job: dict, keyword: str, region_name: str):
        """
        解析猎聘 API 返回的单个职位数据

        猎聘搜索 API 中每个职位的数据结构：
        {
            "job": {
                "jobId": "...",
                "title": "...",
                "salary": "15-25K",
                ...
            },
            "comp": {
                "compId": "...",
                "compName": "...",
                ...
            },
            "recruiter": { ... }
        }
        """
        item = LiepinJobItem()

        # 职位信息 - 猎聘数据可能在 job 字段下或直接在顶层
        job_info = job.get("job", job)

        # 基本信息
        item["job_id"] = str(job_info.get("jobId", job_info.get("id", "")))
        item["job_title"] = job_info.get("title", job_info.get("jobName", ""))
        item["job_category"] = job_info.get("jobCategory", job_info.get("categoryName", ""))
        item["job_type"] = job_info.get("jobType", "")

        # 薪资
        salary_desc = job_info.get("salary", job_info.get("salaryDesc", ""))
        item["salary_desc"] = salary_desc
        salary_min, salary_max = parse_liepin_salary(salary_desc)
        if salary_min:
            item["salary_min"] = salary_min
        if salary_max:
            item["salary_max"] = salary_max

        # 地点
        item["work_city"] = job_info.get("city", job_info.get("cityName", region_name))
        item["work_district"] = job_info.get("district", job_info.get("areaName", ""))

        # 职位详情
        item["education"] = job_info.get("edu", job_info.get("eduLevel", ""))
        item["experience"] = job_info.get("workYear", job_info.get("workExp", ""))
        item["keywords"] = job_info.get("labels", job_info.get("keyWords", []))

        # 招聘信息
        item["publish_date"] = job_info.get("publishTime", job_info.get("startTime", ""))
        item["is_headhunt"] = job_info.get("isHeadhunt", False)

        # 公司信息
        comp_info = job.get("comp", {})
        if comp_info:
            item["company_id"] = str(comp_info.get("compId", comp_info.get("companyId", "")))
            item["company_name"] = comp_info.get("compName", comp_info.get("companyName", ""))
            item["company_type"] = comp_info.get("compType", comp_info.get("companyType", ""))
            item["company_scale"] = comp_info.get("compScale", comp_info.get("companySize", ""))
            item["company_industry"] = comp_info.get("compIndustry", comp_info.get("industryName", ""))
            item["company_stage"] = comp_info.get("compStage", comp_info.get("financingStage", ""))
        else:
            # 公司信息可能在顶层
            item["company_id"] = str(job_info.get("compId", job_info.get("companyId", "")))
            item["company_name"] = job_info.get("compName", job_info.get("companyName", ""))
            item["company_type"] = job_info.get("compType", "")
            item["company_scale"] = job_info.get("compScale", "")
            item["company_industry"] = job_info.get("compIndustry", "")
            item["company_stage"] = job_info.get("compStage", "")

        # 来源 URL
        job_id = item.get("job_id", "")
        if job_id:
            item["source_url"] = f"https://www.liepin.com/job/{job_id}.shtml"

        # 元数据
        item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item["source_platform"] = "猎聘"

        return item


class JobDetailParserMixin:
    """职位详情解析 Mixin - 处理职位详情页"""

    def parse_job_detail(self, response):
        """
        解析猎聘职位详情页

        猎聘职位详情页包含完整的职位描述、任职要求、公司信息等。
        数据可能通过 SSR 内嵌或 API 加载。
        """
        item = response.meta.get("item")
        keyword = response.meta.get("keyword", "")
        region_name = response.meta.get("region_name", "")

        if not item:
            logger.warning("职位详情页缺少 item 元数据")
            return

        # 尝试从 SSR 数据提取详情
        ssr_data = self._extract_detail_ssr_data(response)
        if ssr_data:
            self._enrich_item_from_ssr(item, ssr_data)
        else:
            # 回退：从 HTML 页面解析
            self._enrich_item_from_html(item, response)

        yield item

    def _extract_detail_ssr_data(self, response) -> dict:
        """从职位详情页提取 SSR 内嵌数据"""
        match = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*",
            response.text,
        )
        if match:
            start = match.end()
            json_str = response.text[start:]
            brace_count = 0
            end = -1
            for i, ch in enumerate(json_str):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end > 0:
                json_str = json_str[:end]
                try:
                    data = json.loads(json_str)
                    return data
                except json.JSONDecodeError as e:
                    logger.warning(f"解析猎聘详情页 SSR 数据失败: {e}")
        return None

    def _enrich_item_from_ssr(self, item, ssr_data: dict):
        """从 SSR 数据补充职位详情信息"""
        # 猎聘详情页 SSR 数据路径：jobDetail -> job
        job_detail = ssr_data.get("jobDetail", {})
        job_info = job_detail.get("job", {})

        if not job_info:
            # 尝试其他路径
            job_info = ssr_data.get("job", {})

        if job_info:
            # 职位描述
            if not item.get("job_description"):
                item["job_description"] = job_info.get("describe", job_info.get("jobDesc", ""))

            # 任职要求
            if not item.get("job_requirement"):
                item["job_requirement"] = job_info.get("require", job_info.get("jobRequire", ""))

            # 福利待遇
            if not item.get("welfare"):
                welfare = job_info.get("welfare", job_info.get("benefit", ""))
                if isinstance(welfare, list):
                    welfare = " | ".join(welfare)
                item["welfare"] = welfare

            # 技能要求
            if not item.get("skills"):
                skills = job_info.get("skills", job_info.get("skillLabels", []))
                if isinstance(skills, str):
                    skills = [s.strip() for s in skills.split(",") if s.strip()]
                item["skills"] = skills

            # 关键词标签
            if not item.get("keywords"):
                labels = job_info.get("labels", job_info.get("keyWords", []))
                if isinstance(labels, str):
                    labels = [l.strip() for l in labels.split(",") if l.strip()]
                item["keywords"] = labels

            # 工作地址
            if not item.get("work_address"):
                item["work_address"] = job_info.get("address", job_info.get("workAddress", ""))

            # 招聘人数
            if not item.get("recruit_num"):
                item["recruit_num"] = job_info.get("recruitNum", None)

        # 公司详情
        comp_detail = job_detail.get("comp", ssr_data.get("comp", {}))
        if comp_detail:
            if not item.get("company_description"):
                item["company_description"] = comp_detail.get("compDesc", comp_detail.get("description", ""))

    def _enrich_item_from_html(self, item, response):
        """从 HTML 页面补充职位详情信息"""
        # 职位描述
        if not item.get("job_description"):
            desc = response.css("div.job-description div.content::text").get("")
            if not desc:
                desc = response.css("div.job-detail-section div.content::text").get("")
            if desc:
                item["job_description"] = desc.strip()

        # 任职要求
        if not item.get("job_requirement"):
            require = response.css("div.job-require div.content::text").get("")
            if not require:
                require = response.css("div.job-detail-section:nth-child(2) div.content::text").get("")
            if require:
                item["job_requirement"] = require.strip()

        # 福利待遇
        if not item.get("welfare"):
            welfare_list = response.css("div.job-tags span::text").getall()
            if welfare_list:
                item["welfare"] = " | ".join([w.strip() for w in welfare_list if w.strip()])

        # 工作地址
        if not item.get("work_address"):
            address = response.css("div.job-location span::text").get("")
            if not address:
                address = response.css("div.job-detail-address::text").get("")
            if address:
                item["work_address"] = address.strip()


class CompanyDetailParserMixin:
    """公司详情解析 Mixin - 处理公司详情页"""

    def parse_company_detail(self, response):
        """
        解析猎聘公司详情页

        提取公司的详细信息：简介、规模、行业、融资阶段等。
        """
        item = response.meta.get("item")
        if not item:
            logger.warning("公司详情页缺少 item 元数据")
            return

        # 尝试从 SSR 数据提取
        ssr_data = self._extract_company_ssr_data(response)
        if ssr_data:
            self._enrich_company_from_ssr(item, ssr_data)
        else:
            self._enrich_company_from_html(item, response)

        yield item

    def _extract_company_ssr_data(self, response) -> dict:
        """从公司详情页提取 SSR 数据"""
        match = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*",
            response.text,
        )
        if match:
            start = match.end()
            json_str = response.text[start:]
            brace_count = 0
            end = -1
            for i, ch in enumerate(json_str):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end > 0:
                json_str = json_str[:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
        return None

    def _enrich_company_from_ssr(self, item, ssr_data: dict):
        """从 SSR 数据补充公司信息"""
        comp_info = ssr_data.get("compDetail", ssr_data.get("comp", {}))
        if comp_info:
            if not item.get("company_description"):
                item["company_description"] = comp_info.get("compDesc", comp_info.get("description", ""))
            if not item.get("company_address"):
                item["company_address"] = comp_info.get("address", "")
            if not item.get("company_website"):
                item["company_website"] = comp_info.get("website", comp_info.get("compWebsite", ""))
            if not item.get("company_logo"):
                item["company_logo"] = comp_info.get("logo", comp_info.get("compLogo", ""))

    def _enrich_company_from_html(self, item, response):
        """从 HTML 页面补充公司信息"""
        if not item.get("company_description"):
            desc = response.css("div.company-description::text").get("")
            if not desc:
                desc = response.css("div.comp-description::text").get("")
            if desc:
                item["company_description"] = desc.strip()

        if not item.get("company_address"):
            address = response.css("div.company-address::text").get("")
            if not address:
                address = response.css("div.comp-address span::text").get("")
            if address:
                item["company_address"] = address.strip()
