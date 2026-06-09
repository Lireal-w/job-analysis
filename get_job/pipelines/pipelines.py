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
# 原始数据保存管道（新增）
# ==========================================

class RawDataPipeline:
    """原始数据保存管道：将Spider返回的原始数据保存到MongoDB专用集合
    
    优先级：50（最高优先级，在其他处理之前执行）
    
    功能：
    - 检测 Item 是否包含 _raw_data 字段
    - 将原始数据保存到 raw_xiaoyuan_jobs 集合
    - 保留原始数据结构供后续审计和分析
    """
    
    def __init__(self):
        self.saved_count = 0
    
    def open_spider(self):
        """初始化MongoDB连接"""
        from get_job.utils.mongo_helper import get_mongo_client, get_database
        from scrapy.utils.project import get_project_settings
        
        try:
            get_mongo_client()
            self.db = get_database()
            settings = get_project_settings()
            self.raw_collection_name = settings.get('RAW_DATA_COLLECTION', 'raw_xiaoyuan_jobs')
            logger.info(f"RawDataPipeline 已初始化，原始数据集合: {self.raw_collection_name}")
        except Exception as e:
            logger.error(f"RawDataPipeline 初始化失败: {e}")
            raise
    
    def close_spider(self):
        """输出统计信息"""
        logger.info(f"RawDataPipeline 统计: 本次运行保存 {self.saved_count} 条原始数据")
    
    def process_item(self, item):
        """处理Item，保存原始数据"""
        # 只处理包含 _raw_data 的 dict 类型数据
        if not isinstance(item, dict) or '_raw_data' not in item:
            return item
        
        # 检查开关
        from scrapy.utils.project import get_project_settings
        settings = get_project_settings()
        if not settings.getbool('RAW_DATA_ENABLED', True):
            return item
        
        try:
            # 构建原始数据文档
            raw_doc = {
                '_platform': item.get('_platform', 'unknown'),
                '_data_source': item.get('_data_source', 'unknown'),
                '_crawl_time': item.get('crawl_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                '_raw_data': item['_raw_data'],  # 完整的原始数据
                '_extracted_fields': {
                    k: v for k, v in item.items() 
                    if not k.startswith('_')
                },  # 已提取的基础字段快照
            }
            
            # 保存到MongoDB
            collection = self.db[self.raw_collection_name]
            collection.insert_one(raw_doc)
            self.saved_count += 1
            
            if self.saved_count % 100 == 0:
                logger.info(f"RawDataPipeline 已保存 {self.saved_count} 条原始数据")
        
        except Exception as e:
            logger.error(f"RawDataPipeline 保存原始数据失败: {e}")
        
        # 继续传递 item 到下一个 Pipeline
        return item


# ==========================================
# 统一转换管道（新增）
# ==========================================

class UnifiedTransformPipeline:
    """统一数据转换管道：将原始数据dict转换为统一的BaseJobItem模型
    
    优先级：75（在RawDataPipeline之后，DataCleanPipeline之前）
    
    功能：
    - 根据 _platform 标识识别数据来源
    - 调用对应平台的转换函数
    - 将 dict 转换为 BaseJobItem 或其子类实例
    - 移除 _platform, _raw_data 等元字段
    """
    
    def __init__(self):
        # 平台转换函数注册表
        self.transformers = {
            'xiaoyuan': self._transform_xiaoyuan,
            # 未来可扩展其他平台
            # 'liepin': self._transform_liepin,
        }
    
    def process_item(self, item):
        """处理Item，转换为统一模型"""
        # 只处理 dict 类型且包含 _platform 的数据
        if not isinstance(item, dict) or '_platform' not in item:
            return item
        
        platform = item.get('_platform')
        transformer = self.transformers.get(platform)
        if not transformer:
            logger.warning(f"未找到平台 {platform} 的转换函数，跳过转换")
            return item
        
        try:
            # 执行转换
            transformed_item = transformer(item)
            logger.debug(f"成功转换 {platform} 平台数据: job_id={transformed_item.get('job_id')}")
            return transformed_item
        
        except Exception as e:
            logger.error(f"UnifiedTransformPipeline 转换失败 [{platform}]: {e}")
            # 转换失败时丢弃该Item
            raise DropItem(f"数据转换失败: {e}")
    
    def _transform_xiaoyuan(self, raw_dict: dict):
        """将智联校园招聘原始数据转换为 XiaoyuanJobItem"""
        from get_job.items import XiaoyuanJobItem
        
        item = XiaoyuanJobItem()
        raw_data = raw_dict.get('_raw_data', {})
        
        # 策略1：优先使用已提取的基础字段
        base_fields = [
            'job_id', 'job_title', 'job_category', 'job_type',
            'company_id', 'company_name', 'company_type', 'company_scale', 'company_industry',
            'salary_min', 'salary_max', 'salary_desc',
            'work_city', 'work_district', 'work_address',
            'education', 'experience', 'job_description', 'job_requirement',
            'skills', 'welfare', 'recruit_num', 'publish_date', 'deadline',
            'source_url', 'crawl_time', 'source_platform',
        ]
        
        for field in base_fields:
            if field in raw_dict and raw_dict[field]:
                item[field] = raw_dict[field]
        
        # 策略2：从原始数据中补充缺失字段
        if raw_data:
            self._enrich_from_raw_data(item, raw_data)
        
        # 移除元字段
        item.pop('_platform', None)
        item.pop('_raw_data', None)
        item.pop('_data_source', None)
        
        return item
    
    def _enrich_from_raw_data(self, item, raw_data: dict):
        """从原始SSR/API数据中补充缺失字段"""
        
        # 职位类别
        if not item.get('job_category'):
            item['job_category'] = raw_data.get('subJobTypeLevelName', '')
        
        # 工作类型
        if not item.get('job_type'):
            item['job_type'] = raw_data.get('workType', '')
        
        # 公司信息补充
        if not item.get('company_type'):
            item['company_type'] = raw_data.get('property', '') or raw_data.get('propertyName', '')
        
        if not item.get('company_scale'):
            item['company_scale'] = raw_data.get('companySize', '')
        
        if not item.get('company_industry'):
            item['company_industry'] = raw_data.get('industryName', '')
        
        # 薪资补充
        if not item.get('salary_desc'):
            item['salary_desc'] = raw_data.get('salary60', '') or raw_data.get('salaryReal', '')
        
        # 工作地点补充
        if not item.get('work_district'):
            item['work_district'] = raw_data.get('cityDistrict', '')
        
        # 招聘人数
        if not item.get('recruit_num'):
            item['recruit_num'] = raw_data.get('recruitNumber', None)
        
        # 发布日期
        if not item.get('publish_date'):
            item['publish_date'] = raw_data.get('publishTime', '')
        
        # 福利标签
        if not item.get('welfare'):
            welfare_labels = raw_data.get('welfareLabel', [])
            if isinstance(welfare_labels, list):
                item['welfare'] = " | ".join(welfare_labels)
        
        # 从嵌套结构中提取更多信息
        campus_detail = raw_data.get('campusJobDetail', {})
        if campus_detail:
            if not item.get('company_scale'):
                item['company_scale'] = campus_detail.get('orgSizeName', '')
            if not item.get('company_type'):
                item['company_type'] = campus_detail.get('orgTypeName', '')
        
        # 从 jobDetailData 中提取详细信息
        job_detail = raw_data.get('jobDetailData', {})
        if job_detail:
            position = job_detail.get('position', {})
            if position:
                base_info = position.get('base', {})
                if base_info:
                    if not item.get('salary_desc'):
                        item['salary_desc'] = base_info.get('salary', '')
                    if not item.get('education'):
                        item['education'] = base_info.get('education', '')
                    if not item.get('experience'):
                        item['experience'] = base_info.get('positionWorkingExp', '')
                    if not item.get('job_type'):
                        item['job_type'] = base_info.get('workType', '')
                
                desc_info = position.get('desc', {})
                if desc_info:
                    if not item.get('job_description'):
                        item['job_description'] = desc_info.get('description', '')
                    welfare_tags = desc_info.get('welfareTags', [])
                    if welfare_tags and not item.get('welfare'):
                        item['welfare'] = " | ".join(welfare_tags)
                
                work_location = position.get('workLocation', {})
                if work_location:
                    if not item.get('work_address'):
                        item['work_address'] = work_location.get('address', '')
                    if not item.get('work_city'):
                        item['work_city'] = work_location.get('positionWorkCity', '')
        
        # 技能标签
        if not item.get('skills'):
            skill_tags = raw_data.get('jobSkillTags', [])
            if isinstance(skill_tags, list):
                item['skills'] = [s.get('name', '') for s in skill_tags if s.get('name')]


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
