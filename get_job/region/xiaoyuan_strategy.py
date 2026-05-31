
"""
智联校园招聘地区策略

组合基础策略类，为智联校园招聘提供地区解析能力。
"""

from typing import Dict, List, Tuple

from get_job.region.base import (
    RegionStrategyFactory,
    CityNameStrategy,
    ProvinceNameStrategy,
    RegionIdStrategy,
)
from get_job.region.xiaoyuan_table import XIAOYUAN_REGION_TABLE, XIAOYUAN_PROVINCE_TABLE


def create_xiaoyuan_region_factory() -> RegionStrategyFactory:
    """
    创建智联校园招聘的地区策略工厂

    策略优先级：
    1. 城市名称策略（如 "北京" -> 530）
    2. 省份名称策略（如 "广东" -> 548, "广东省" -> 548）
    3. 地区ID策略（如 "530" -> 北京）

    Returns:
        配置好的 RegionStrategyFactory 实例
    """
    factory = RegionStrategyFactory()
    factory.register(CityNameStrategy(XIAOYUAN_REGION_TABLE))
    factory.register(ProvinceNameStrategy(XIAOYUAN_REGION_TABLE, XIAOYUAN_PROVINCE_TABLE))
    factory.register(RegionIdStrategy(XIAOYUAN_REGION_TABLE))
    return factory


def get_xiaoyuan_region_table() -> Dict[str, int]:
    """获取智联校园招聘地区映射表"""
    return XIAOYUAN_REGION_TABLE
