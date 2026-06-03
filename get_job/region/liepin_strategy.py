
"""
猎聘地区策略

组合基础策略类，为猎聘提供地区解析能力。
"""

from typing import Dict

from get_job.region.base import (
    RegionStrategyFactory,
    CityNameStrategy,
    ProvinceNameStrategy,
    RegionIdStrategy,
)
from get_job.region.liepin_table import LIEPIN_REGION_TABLE, LIEPIN_PROVINCE_TABLE


def create_liepin_region_factory() -> RegionStrategyFactory:
    """
    创建猎聘的地区策略工厂

    策略优先级：
    1. 城市名称策略（如 "北京" -> 410）
    2. 省份名称策略（如 "广东" -> 410, "广东省" -> 410）
    3. 地区ID策略（如 "410" -> 北京）

    注意：猎聘搜索API使用城市名称字符串进行查询，
    地区ID仅用于策略模式接口兼容。

    Returns:
        配置好的 RegionStrategyFactory 实例
    """
    factory = RegionStrategyFactory()
    factory.register(CityNameStrategy(LIEPIN_REGION_TABLE))
    factory.register(ProvinceNameStrategy(LIEPIN_REGION_TABLE, LIEPIN_PROVINCE_TABLE))
    factory.register(RegionIdStrategy(LIEPIN_REGION_TABLE))
    return factory


def get_liepin_region_table() -> Dict[str, int]:
    """获取猎聘地区映射表"""
    return LIEPIN_REGION_TABLE
