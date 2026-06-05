"""智联校园招聘（小园）相关 Pipeline"""

import json
import os
import logging
import re
from datetime import datetime
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class XiaoyuanDataCleanPipeline:
    """数据清洗管道：清理空值、格式化字段"""

    def process_item(self, item):
        adapter = ItemAdapter(item)

        # 清理所有字符串字段的空白字符
        for field_name in adapter.field_names():
            value = adapter.get(field_name)
            if isinstance(value, str):
                # 去除首尾空白
                value = value.strip()
                # 将多个连续空白替换为单个空格
                value = re.sub(r'\s+', ' ', value)
                adapter[field_name] = value
            elif isinstance(value, list):
                # 清理列表中的字符串
                cleaned_list = []
                for v in value:
                    if isinstance(v, str):
                        v = v.strip()
                        if v:
                            cleaned_list.append(v)
                    elif v:
                        cleaned_list.append(v)
                adapter[field_name] = cleaned_list

        # 设置爬取时间
        if not adapter.get('crawl_time'):
            adapter['crawl_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 设置来源平台
        if not adapter.get('source_platform'):
            adapter['source_platform'] = '智联校园招聘'

        # 薪资解析
        salary_desc = adapter.get('salary_desc', '')
        if salary_desc and not adapter.get('salary_min'):
            salary_min, salary_max = self._parse_salary(salary_desc)
            if salary_min:
                adapter['salary_min'] = salary_min
            if salary_max:
                adapter['salary_max'] = salary_max

        return item

    @staticmethod
    def _parse_salary(salary_desc: str):
        """
        解析薪资描述，返回 (最低月薪, 最高月薪)，单位统一为 元/月。

        支持的格式：
        - "8000-12000元/月"        -> (8000, 12000)
        - "8K-12K"                 -> (8000, 12000)
        - "1-1.5万"                -> (10000, 15000)
        - "1.5-3万·14薪"           -> (15000, 30000)
        - "100-120元/天"           -> (2200, 2640)   按22个工作日换算
        - "15-20元/时"             -> (2640, 3520)   按8h/天、22天/月换算
        - "5000元/月"              -> (5000, 5000)
        - "面议"                   -> (None, None)
        """
        if not salary_desc:
            return None, None

        salary_desc = salary_desc.strip()
        if not salary_desc or salary_desc in ("面议", " negotiable", "薪资面议"):
            return None, None

        try:
            # 提取年终奖月数（如 "·14薪" -> annual_months=14）
            annual_months = None
            bonus_match = re.search(r'[·\-\s](\d+)薪', salary_desc)
            if bonus_match:
                annual_months = int(bonus_match.group(1))
                # 移除年终奖标记，避免干扰后续解析
                salary_desc = salary_desc[:bonus_match.start()].strip()

            # ---- 按天计薪：X-Y元/天 ----
            day_match = re.match(
                r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*元\s*/\s*天',
                salary_desc,
            )
            if day_match:
                min_daily = float(day_match.group(1))
                max_daily = float(day_match.group(2))
                # 按 22 个工作日换算为月薪
                min_monthly = round(min_daily * 22)
                max_monthly = round(max_daily * 22)
                return min_monthly, max_monthly

            # ---- 按小时计薪：X-Y元/时(小时) ----
            hour_match = re.match(
                r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*元\s*/\s*(?:时|小时)',
                salary_desc,
            )
            if hour_match:
                min_hourly = float(hour_match.group(1))
                max_hourly = float(hour_match.group(2))
                # 按 8小时/天、22天/月 换算为月薪
                min_monthly = round(min_hourly * 8 * 22)
                max_monthly = round(max_hourly * 8 * 22)
                return min_monthly, max_monthly

            # ---- 万单位：X-Y万 ----
            wan_match = re.match(
                r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*万',
                salary_desc,
            )
            if wan_match:
                min_val = int(float(wan_match.group(1)) * 10000)
                max_val = int(float(wan_match.group(2)) * 10000)
                # 如果有年终奖，折算到月薪
                if annual_months and annual_months > 12:
                    min_val = round(min_val * annual_months / 12)
                    max_val = round(max_val * annual_months / 12)
                return min_val, max_val

            # ---- K/千单位：XK-YK 或 XK-YK/月 ----
            k_match = re.match(
                r'([\d.]+)\s*[kK千]\s*[-~至到]\s*([\d.]+)\s*[kK千]',
                salary_desc,
            )
            if k_match:
                min_val = int(float(k_match.group(1)) * 1000)
                max_val = int(float(k_match.group(2)) * 1000)
                return min_val, max_val

            # ---- 元/月：X-Y元/月 或 X-Y元 ----
            yuan_month_match = re.match(
                r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*元(?:\s*/\s*月)?',
                salary_desc,
            )
            if yuan_month_match:
                min_val = int(float(yuan_month_match.group(1)))
                max_val = int(float(yuan_month_match.group(2)))
                return min_val, max_val

            # ---- 纯数字范围：X-Y（无单位，默认元/月） ----
            pure_match = re.match(
                r'([\d.]+)\s*[-~至到]\s*([\d.]+)',
                salary_desc,
            )
            if pure_match:
                min_val = float(pure_match.group(1))
                max_val = float(pure_match.group(2))
                # 如果值小于100，认为是K单位
                if min_val < 100:
                    min_val = int(min_val * 1000)
                    max_val = int(max_val * 1000)
                else:
                    min_val = int(min_val)
                    max_val = int(max_val)
                return min_val, max_val

            # ---- 单一数值：X元/月 / XK / X万 ----
            single_yuan = re.match(r'([\d.]+)\s*元(?:\s*/\s*月)?', salary_desc)
            if single_yuan:
                val = int(float(single_yuan.group(1)))
                return val, val

            single_k = re.match(r'([\d.]+)\s*[kK千]', salary_desc)
            if single_k:
                val = int(float(single_k.group(1)) * 1000)
                return val, val

            single_wan = re.match(r'([\d.]+)\s*万', salary_desc)
            if single_wan:
                val = int(float(single_wan.group(1)) * 10000)
                return val, val

        except (ValueError, AttributeError):
            pass

        return None, None


class XiaoyuanJsonPipeline:
    """JSON 文件存储管道"""

    def __init__(self):
        self.file = None
        self.items = []

    def open_spider(self):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'xiaoyuan_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        self.filepath = filepath
        logger.info(f"JSON 输出文件: {filepath}")

    def close_spider(self):
        if self.items:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.items)} 条数据到 {self.filepath}")
        else:
            logger.warning("没有数据需要保存")

    def process_item(self, item):
        adapter = ItemAdapter(item)
        self.items.append(dict(adapter))
        return item


class XiaoyuanCsvPipeline:
    """CSV 文件存储管道"""

    def __init__(self):
        self.file = None
        self.writer = None
        self.headers_written = False

    def open_spider(self):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'xiaoyuan_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        self.filepath = filepath
        self.file = open(filepath, 'w', encoding='utf-8-sig', newline='')
        logger.info(f"CSV 输出文件: {filepath}")

    def close_spider(self):
        if self.file:
            self.file.close()
            logger.info(f"CSV 文件已关闭: {self.filepath}")

    def process_item(self, item):
        import csv
        from get_job.items import XiaoyuanJobItem

        adapter = ItemAdapter(item)
        data = dict(adapter)

        if not self.headers_written:
            # 使用 Item 类定义的所有字段作为 fieldnames，确保所有字段都有列
            all_fields = list(XiaoyuanJobItem.fields.keys())
            self.writer = csv.DictWriter(self.file, fieldnames=all_fields, extrasaction='ignore')
            self.writer.writeheader()
            self.headers_written = True

        self.writer.writerow(data)
        return item


class XiaoyuanDedupPipeline:
    """去重管道：根据 job_id 去重"""

    def __init__(self):
        self.seen_ids = set()

    def process_item(self, item):
        adapter = ItemAdapter(item)
        job_id = adapter.get('job_id')

        if job_id:
            if job_id in self.seen_ids:
                logger.debug(f"重复职位，已跳过: {job_id}")
                raise DropItem(f"重复职位: {job_id}")
            self.seen_ids.add(job_id)

        return item


class XiaoyuanMongoPipeline:
    """MongoDB 存储管道：将职位和公司数据分别存储到 MongoDB 对应集合"""

    def __init__(self):
        self.job_count = 0
        self.company_count = 0
        self._job_ids = set()  # 用于单次运行内的去重
        self._company_ids = set()

    def open_spider(self):
        """Spider 启动时初始化 MongoDB 连接"""
        from get_job.utils.mongo_helper import (
            get_mongo_client,
            get_database,
            MONGO_JOB_COLLECTION,
            MONGO_COMPANY_COLLECTION,
        )

        # 触发连接
        try:
            get_mongo_client()
            self.db = get_database()
            self.job_collection_name = MONGO_JOB_COLLECTION
            self.company_collection_name = MONGO_COMPANY_COLLECTION
            logger.info(f"MongoDB 存储管道已初始化（职位集合: {self.job_collection_name}, 公司集合: {self.company_collection_name}）")
        except Exception as e:
            logger.error(f"MongoDB 存储管道初始化失败: {e}")
            raise

    def close_spider(self):
        """Spider 关闭时输出统计信息"""
        from get_job.utils.mongo_helper import close_mongo_client, get_collection_count, MONGO_JOB_COLLECTION, MONGO_COMPANY_COLLECTION

        job_total = get_collection_count(MONGO_JOB_COLLECTION)
        company_total = get_collection_count(MONGO_COMPANY_COLLECTION)

        logger.info(
            f"MongoDB 存储统计 - 本次运行: 职位 {self.job_count} 条, 公司 {self.company_count} 条"
        )
        logger.info(
            f"MongoDB 集合总量 - 职位: {job_total}, 公司: {company_total}"
        )

        close_mongo_client()

    def process_item(self, item):
        """根据 Item 类型存储到对应集合"""
        from get_job.items import XiaoyuanJobItem, XiaoyuanCompanyItem
        from get_job.utils.mongo_helper import save_item_to_mongo

        adapter = ItemAdapter(item)
        data = dict(adapter)

        if isinstance(item, XiaoyuanJobItem):
            return self._process_job(data)
        elif isinstance(item, XiaoyuanCompanyItem):
            return self._process_company(data)
        else:
            # 未知类型，尝试按职位处理
            return self._process_job(data)

    def _process_job(self, data: dict) -> dict:
        """处理职位数据"""
        from get_job.utils.mongo_helper import save_item_to_mongo, MONGO_JOB_COLLECTION

        job_id = data.get('job_id')

        # 单次运行内去重
        if job_id and job_id in self._job_ids:
            logger.debug(f"MongoDB 管道：重复职位已跳过: {job_id}")
            return data
        if job_id:
            self._job_ids.add(job_id)

        success = save_item_to_mongo(
            item=data,
            collection_name=MONGO_JOB_COLLECTION,
            unique_key='job_id',
        )

        if success:
            self.job_count += 1
            if self.job_count % 50 == 0:
                logger.info(f"MongoDB 已存储 {self.job_count} 条职位数据")

        return data

    def _process_company(self, data: dict) -> dict:
        """处理公司数据"""
        from get_job.utils.mongo_helper import save_item_to_mongo, MONGO_COMPANY_COLLECTION

        company_id = data.get('company_id')

        # 单次运行内去重
        if company_id and company_id in self._company_ids:
            logger.debug(f"MongoDB 管道：重复公司已跳过: {company_id}")
            return data
        if company_id:
            self._company_ids.add(company_id)

        success = save_item_to_mongo(
            item=data,
            collection_name=MONGO_COMPANY_COLLECTION,
            unique_key='company_id',
        )

        if success:
            self.company_count += 1
            if self.company_count % 20 == 0:
                logger.info(f"MongoDB 已存储 {self.company_count} 条公司数据")

        return data
