# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


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

    def process_item(self, item, spider):
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
        """解析薪资描述，返回最低和最高薪资"""
        if not salary_desc:
            return None, None

        try:
            # 匹配类似 "8000-12000元/月" 或 "8K-12K" 的格式
            pattern = r'(\d+)\s*[kK千]?\s*[-~至到]\s*(\d+)\s*[kK千]?'
            match = re.search(pattern, salary_desc)
            if match:
                min_val = int(match.group(1))
                max_val = int(match.group(2))
                # 如果值小于100，认为是K单位
                if min_val < 100:
                    min_val *= 1000
                if max_val < 100:
                    max_val *= 1000
                return min_val, max_val
        except (ValueError, AttributeError):
            pass

        return None, None


class XiaoyuanJsonPipeline:
    """JSON 文件存储管道"""

    def __init__(self):
        self.file = None
        self.items = []

    def open_spider(self, spider):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'xiaoyuan_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        self.filepath = filepath
        logger.info(f"JSON 输出文件: {filepath}")

    def close_spider(self, spider):
        if self.items:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.items)} 条数据到 {self.filepath}")
        else:
            logger.warning("没有数据需要保存")

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        self.items.append(dict(adapter))
        return item


class XiaoyuanCsvPipeline:
    """CSV 文件存储管道"""

    def __init__(self):
        self.file = None
        self.writer = None
        self.headers_written = False

    def open_spider(self, spider):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'xiaoyuan_jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        self.filepath = filepath
        self.file = open(filepath, 'w', encoding='utf-8-sig', newline='')
        logger.info(f"CSV 输出文件: {filepath}")

    def close_spider(self, spider):
        if self.file:
            self.file.close()
            logger.info(f"CSV 文件已关闭: {self.filepath}")

    def process_item(self, item, spider):
        import csv
        adapter = ItemAdapter(item)
        data = dict(adapter)

        if not self.headers_written:
            self.writer = csv.DictWriter(self.file, fieldnames=data.keys())
            self.writer.writeheader()
            self.headers_written = True

        self.writer.writerow(data)
        return item


class XiaoyuanDedupPipeline:
    """去重管道：根据 job_id 去重"""

    def __init__(self):
        self.seen_ids = set()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        job_id = adapter.get('job_id')

        if job_id:
            if job_id in self.seen_ids:
                logger.debug(f"重复职位，已跳过: {job_id}")
                raise DropItem(f"重复职位: {job_id}")
            self.seen_ids.add(job_id)

        return item

