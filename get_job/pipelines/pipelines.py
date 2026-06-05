"""统一 Pipeline：合并多平台同类管道，根据 Item 类型分发到不同分支"""

import json
import os
import logging
from datetime import datetime
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from get_job.utils.spider_helpers import clean_item_fields, parse_salary

logger = logging.getLogger(__name__)


# ==========================================
# 平台配置注册表
# ==========================================

PLATFORM_CONFIG = {
    'xiaoyuan': {
        'name': '智联校园招聘',
        'file_prefix': 'xiaoyuan_jobs',
        'job_item': 'get_job.items.XiaoyuanJobItem',
        'company_item': 'get_job.items.XiaoyuanCompanyItem',
        'salary_parser': None,  # 使用通用 parse_salary
    },
    'liepin': {
        'name': '猎聘',
        'file_prefix': 'liepin_jobs',
        'job_item': 'get_job.items.LiepinJobItem',
        'company_item': 'get_job.items.LiepinCompanyItem',
        'salary_parser': 'get_job.spiders.liepin.parse_liepin_salary',
    },
}


def _get_item_platform(item) -> str:
    """根据 Item 实例判断所属平台，返回平台 key 或 None"""
    from get_job.items import (
        XiaoyuanJobItem, XiaoyuanCompanyItem,
        LiepinJobItem, LiepinCompanyItem,
    )
    if isinstance(item, (XiaoyuanJobItem, XiaoyuanCompanyItem)):
        return 'xiaoyuan'
    elif isinstance(item, (LiepinJobItem, LiepinCompanyItem)):
        return 'liepin'
    # 兜底：通过 source_platform 字段判断
    adapter = ItemAdapter(item)
    platform = adapter.get('source_platform', '')
    if '智联' in platform or '校园' in platform:
        return 'xiaoyuan'
    elif '猎聘' in platform:
        return 'liepin'
    return None


def _import_object(dotted_path: str):
    """根据点分路径动态导入对象"""
    module_path, obj_name = dotted_path.rsplit('.', 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, obj_name)


def _is_job_item(item) -> bool:
    """判断是否为职位 Item（基于 BaseJobItem 统一基类）"""
    from get_job.items import BaseJobItem
    return isinstance(item, BaseJobItem)


def _is_company_item(item) -> bool:
    """判断是否为公司 Item（基于 BaseCompanyItem 统一基类）"""
    from get_job.items import BaseCompanyItem
    return isinstance(item, BaseCompanyItem)


# ==========================================
# 数据清洗管道
# ==========================================

class DataCleanPipeline:
    """统一数据清洗管道：根据 Item 类型分发到对应平台的清洗逻辑"""

    def process_item(self, item):
        platform = _get_item_platform(item)
        if platform is None:
            return item

        adapter = ItemAdapter(item)
        config = PLATFORM_CONFIG[platform]

        # 清理所有字段的空白字符
        clean_item_fields(adapter)

        # 设置爬取时间
        if not adapter.get('crawl_time'):
            adapter['crawl_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 设置来源平台
        if not adapter.get('source_platform'):
            adapter['source_platform'] = config['name']

        # 薪资解析（仅职位 Item）
        if _is_job_item(item):
            salary_desc = adapter.get('salary_desc', '')
            if salary_desc and not adapter.get('salary_min'):
                parser_path = config.get('salary_parser')
                parser = _import_object(parser_path) if parser_path else parse_salary
                salary_min, salary_max = parser(salary_desc)
                if salary_min:
                    adapter['salary_min'] = salary_min
                if salary_max:
                    adapter['salary_max'] = salary_max

        return item


# ==========================================
# JSON 存储管道
# ==========================================

class JsonPipeline:
    """统一 JSON 文件存储管道：按平台分文件存储"""

    def __init__(self):
        self.items = {}  # {platform_key: [item_dict, ...]}
        self.filepaths = {}

    def open_spider(self):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        for key, config in PLATFORM_CONFIG.items():
            filepath = os.path.join(
                output_dir,
                f'{config["file_prefix"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            )
            self.filepaths[key] = filepath
            self.items[key] = []
            logger.info(f"JSON 输出文件 [{config['name']}]: {filepath}")

    def close_spider(self):
        for key, config in PLATFORM_CONFIG.items():
            items = self.items.get(key, [])
            filepath = self.filepaths.get(key)
            if items:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(items, f, ensure_ascii=False, indent=2)
                logger.info(f"[{config['name']}] 已保存 {len(items)} 条数据到 {filepath}")
            else:
                logger.debug(f"[{config['name']}] 没有数据需要保存")

    def process_item(self, item):
        platform = _get_item_platform(item)
        if platform is None:
            return item

        adapter = ItemAdapter(item)
        self.items[platform].append(dict(adapter))
        return item


# ==========================================
# 去重管道
# ==========================================

class DedupPipeline:
    """统一去重管道：按平台分别根据 job_id 去重"""

    def __init__(self):
        self.seen_ids = {}  # {platform_key: set()}

    def open_spider(self):
        for key in PLATFORM_CONFIG:
            self.seen_ids[key] = set()

    def process_item(self, item):
        platform = _get_item_platform(item)
        if platform is None:
            return item

        adapter = ItemAdapter(item)
        job_id = adapter.get('job_id')

        if job_id:
            if job_id in self.seen_ids[platform]:
                config = PLATFORM_CONFIG[platform]
                logger.debug(f"[{config['name']}] 重复职位，已跳过: {job_id}")
                raise DropItem(f"[{config['name']}] 重复职位: {job_id}")
            self.seen_ids[platform].add(job_id)

        return item


# ==========================================
# MongoDB 存储管道
# ==========================================

class MongoPipeline:
    """统一 MongoDB 存储管道：将职位和公司数据分别存储到 MongoDB 对应集合"""

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
            logger.info(
                f"MongoDB 存储管道已初始化（职位集合: {self.job_collection_name}, 公司集合: {self.company_collection_name}）"
            )
        except Exception as e:
            logger.error(f"MongoDB 存储管道初始化失败: {e}")
            raise

    def close_spider(self):
        """Spider 关闭时输出统计信息"""
        from get_job.utils.mongo_helper import (
            close_mongo_client, get_collection_count,
            MONGO_JOB_COLLECTION, MONGO_COMPANY_COLLECTION,
        )

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
        adapter = ItemAdapter(item)
        data = dict(adapter)

        if _is_job_item(item):
            return self._process_job(data)
        elif _is_company_item(item):
            return self._process_company(data)
        else:
            return self._process_job(data)

    def _process_job(self, data: dict) -> dict:
        """处理职位数据"""
        from get_job.utils.mongo_helper import save_item_to_mongo, MONGO_JOB_COLLECTION

        job_id = data.get('job_id')

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
