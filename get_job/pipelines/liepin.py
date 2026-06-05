"""猎聘相关 Pipeline"""

import json
import os
import logging
import re
from datetime import datetime
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class LiepinDataCleanPipeline:
    """猎聘数据清洗管道：清理空值、格式化字段"""

    def process_item(self, item):
        from get_job.items import LiepinJobItem, LiepinCompanyItem

        # 仅处理猎聘 Item
        if not isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
            return item

        adapter = ItemAdapter(item)

        # 清理所有字符串字段的空白字符
        for field_name in adapter.field_names():
            value = adapter.get(field_name)
            if isinstance(value, str):
                value = value.strip()
                value = re.sub(r'\s+', ' ', value)
                adapter[field_name] = value
            elif isinstance(value, list):
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
            adapter['source_platform'] = '猎聘'

        # 薪资解析
        salary_desc = adapter.get('salary_desc', '')
        if salary_desc and not adapter.get('salary_min'):
            from get_job.spiders.liepin import parse_liepin_salary
            salary_min, salary_max = parse_liepin_salary(salary_desc)
            if salary_min:
                adapter['salary_min'] = salary_min
            if salary_max:
                adapter['salary_max'] = salary_max

        return item


class LiepinJsonPipeline:
    """猎聘 JSON 文件存储管道"""

    def __init__(self):
        self.file = None
        self.items = []

    def open_spider(self):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'liepin_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        self.filepath = filepath
        logger.info(f"猎聘 JSON 输出文件: {filepath}")

    def close_spider(self):
        if self.items:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.items)} 条猎聘数据到 {self.filepath}")
        else:
            logger.warning("没有猎聘数据需要保存")

    def process_item(self, item):
        from get_job.items import LiepinJobItem, LiepinCompanyItem

        if not isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
            return item

        adapter = ItemAdapter(item)
        self.items.append(dict(adapter))
        return item


class LiepinCsvPipeline:
    """猎聘 CSV 文件存储管道"""

    def __init__(self):
        self.file = None
        self.writer = None
        self.headers_written = False

    def open_spider(self):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'liepin_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        self.filepath = filepath
        self.file = open(filepath, 'w', encoding='utf-8-sig', newline='')
        logger.info(f"猎聘 CSV 输出文件: {filepath}")

    def close_spider(self):
        if self.file:
            self.file.close()
            logger.info(f"猎聘 CSV 文件已关闭: {self.filepath}")

    def process_item(self, item):
        import csv
        from get_job.items import LiepinJobItem, LiepinCompanyItem

        if not isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
            return item

        adapter = ItemAdapter(item)
        data = dict(adapter)

        if not self.headers_written:
            all_fields = list(LiepinJobItem.fields.keys())
            self.writer = csv.DictWriter(self.file, fieldnames=all_fields, extrasaction='ignore')
            self.writer.writeheader()
            self.headers_written = True

        self.writer.writerow(data)
        return item


class LiepinDedupPipeline:
    """猎聘去重管道：根据 job_id 去重"""

    def __init__(self):
        self.seen_ids = set()

    def process_item(self, item):
        from get_job.items import LiepinJobItem, LiepinCompanyItem

        if not isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
            return item

        adapter = ItemAdapter(item)
        job_id = adapter.get('job_id')

        if job_id:
            if job_id in self.seen_ids:
                logger.debug(f"猎聘重复职位，已跳过: {job_id}")
                raise DropItem(f"猎聘重复职位: {job_id}")
            self.seen_ids.add(job_id)

        return item


class LiepinMongoPipeline:
    """猎聘 MongoDB 存储管道：将职位和公司数据分别存储到 MongoDB 对应集合"""

    def __init__(self):
        self.job_count = 0
        self.company_count = 0
        self._job_ids = set()
        self._company_ids = set()

    def open_spider(self):
        """Spider 启动时初始化 MongoDB 连接"""
        from get_job.utils.mongo_helper import (
            get_mongo_client,
            get_database,
            MONGO_JOB_COLLECTION,
            MONGO_COMPANY_COLLECTION,
        )

        try:
            get_mongo_client()
            self.db = get_database()
            self.job_collection_name = MONGO_JOB_COLLECTION
            self.company_collection_name = MONGO_COMPANY_COLLECTION
            logger.info(f"猎聘 MongoDB 存储管道已初始化（职位集合: {self.job_collection_name}, 公司集合: {self.company_collection_name}）")
        except Exception as e:
            logger.error(f"猎聘 MongoDB 存储管道初始化失败: {e}")
            raise

    def close_spider(self):
        """Spider 关闭时输出统计信息"""
        from get_job.utils.mongo_helper import close_mongo_client, get_collection_count, MONGO_JOB_COLLECTION, MONGO_COMPANY_COLLECTION

        job_total = get_collection_count(MONGO_JOB_COLLECTION)
        company_total = get_collection_count(MONGO_COMPANY_COLLECTION)

        logger.info(
            f"猎聘 MongoDB 存储统计 - 本次运行: 职位 {self.job_count} 条, 公司 {self.company_count} 条"
        )
        logger.info(
            f"MongoDB 集合总量 - 职位: {job_total}, 公司: {company_total}"
        )

        close_mongo_client()

    def process_item(self, item):
        """根据 Item 类型存储到对应集合"""
        from get_job.items import LiepinJobItem, LiepinCompanyItem
        from get_job.utils.mongo_helper import save_item_to_mongo

        if not isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
            return item

        adapter = ItemAdapter(item)
        data = dict(adapter)

        if isinstance(item, LiepinJobItem):
            return self._process_job(data)
        elif isinstance(item, LiepinCompanyItem):
            return self._process_company(data)
        else:
            return self._process_job(data)

    def _process_job(self, data: dict) -> dict:
        """处理职位数据"""
        from get_job.utils.mongo_helper import save_item_to_mongo, MONGO_JOB_COLLECTION

        job_id = data.get('job_id')

        if job_id and job_id in self._job_ids:
            logger.debug(f"猎聘 MongoDB 管道：重复职位已跳过: {job_id}")
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
                logger.info(f"猎聘 MongoDB 已存储 {self.job_count} 条职位数据")

        return data

    def _process_company(self, data: dict) -> dict:
        """处理公司数据"""
        from get_job.utils.mongo_helper import save_item_to_mongo, MONGO_COMPANY_COLLECTION

        company_id = data.get('company_id')

        if company_id and company_id in self._company_ids:
            logger.debug(f"猎聘 MongoDB 管道：重复公司已跳过: {company_id}")
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
                logger.info(f"猎聘 MongoDB 已存储 {self.company_count} 条公司数据")

        return data
