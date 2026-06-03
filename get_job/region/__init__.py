
"""
地区策略模块

提供招聘网站的地区解析能力，使用策略模式 + 工厂模式。
支持按网站扩展，每个网站对应独立的地区表和策略文件。

目录结构：
    region/
    ├── __init__.py              # 公共接口导出
    ├── base.py                  # 策略抽象基类 + 工厂 + 环境变量读取
    ├── xiaoyuan_table.py        # 智联校园地区表（纯数据）
    └── xiaoyuan_strategy.py     # 智联校园策略工厂构建

使用示例：
    from get_job.region import create_xiaoyuan_region_factory

    factory = create_xiaoyuan_region_factory()
    result = factory.resolve("北京")       # ("北京", 530)
    result = factory.resolve("530")        # ("北京", 530)
    result = factory.resolve("广东")       # ("广东", 548)
"""

# 基础类
from get_job.region.base import (
    RegionStrategy,
    RegionStrategyFactory,
    CityNameStrategy,
    ProvinceNameStrategy,
    RegionIdStrategy,
    get_search_keywords_from_env,
    get_target_regions_from_env,
    get_max_page_from_env,
)

# 智联校园招聘
from get_job.region.xiaoyuan_strategy import (
    create_xiaoyuan_region_factory,
    get_xiaoyuan_region_table,
)
from get_job.region.xiaoyuan_table import (
    XIAOYUAN_REGION_TABLE,
    XIAOYUAN_PROVINCE_TABLE,
)

# 猎聘
from get_job.region.liepin_strategy import (
    create_liepin_region_factory,
    get_liepin_region_table,
)
from get_job.region.liepin_table import (
    LIEPIN_REGION_TABLE,
    LIEPIN_PROVINCE_TABLE,
)

__all__ = [
    # 基础类
    "RegionStrategy",
    "RegionStrategyFactory",
    "CityNameStrategy",
    "ProvinceNameStrategy",
    "RegionIdStrategy",
    # 环境变量读取
    "get_search_keywords_from_env",
    "get_target_regions_from_env",
    "get_max_page_from_env",
    # 智联校园招聘
    "create_xiaoyuan_region_factory",
    "get_xiaoyuan_region_table",
    "XIAOYUAN_REGION_TABLE",
    "XIAOYUAN_PROVINCE_TABLE",
    # 猎聘
    "create_liepin_region_factory",
    "get_liepin_region_table",
    "LIEPIN_REGION_TABLE",
    "LIEPIN_PROVINCE_TABLE",
]
