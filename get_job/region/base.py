
"""
地区策略基础模块

定义地区解析策略的抽象基类和工厂类。
不同招聘网站的地区策略实现应继承 RegionStrategy 基类。
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class RegionStrategy(ABC):
    """地区解析策略抽象基类"""

    @abstractmethod
    def resolve(self, region_input: str) -> Optional[Tuple[str, int]]:
        """
        将地区输入解析为 (地区名称, 地区ID) 元组

        Args:
            region_input: 地区输入（城市名、省份名或地区ID字符串）

        Returns:
            解析成功返回 (地区名称, 地区ID)，失败返回 None
        """
        pass

    @abstractmethod
    def get_region_table(self) -> Dict[str, int]:
        """获取当前策略对应的地区映射表"""
        pass


class RegionStrategyFactory:
    """
    地区策略工厂

    根据输入自动选择合适的解析策略，按优先级依次尝试。
    支持注册不同招聘网站的策略组合。
    """

    def __init__(self, strategies: Optional[List[RegionStrategy]] = None):
        """
        初始化工厂

        Args:
            strategies: 策略列表，按优先级排序。若为 None 则使用空列表。
        """
        self._strategies: List[RegionStrategy] = strategies or []

    def register(self, strategy: RegionStrategy) -> "RegionStrategyFactory":
        """
        注册策略（支持链式调用）

        Args:
            strategy: 策略实例

        Returns:
            self，支持链式调用
        """
        self._strategies.append(strategy)
        return self

    def resolve(self, region_input: str) -> Optional[Tuple[str, int]]:
        """
        自动选择策略解析地区输入

        Args:
            region_input: 地区输入（城市名、省份名或地区ID）

        Returns:
            解析成功返回 (地区名称, 地区ID)，失败返回 None
        """
        region_input = region_input.strip()
        for strategy in self._strategies:
            result = strategy.resolve(region_input)
            if result is not None:
                return result
        return None

    def resolve_all(self, region_inputs: List[str]) -> List[Tuple[str, int]]:
        """
        批量解析地区输入列表

        Args:
            region_inputs: 地区输入列表

        Returns:
            成功解析的 (地区名称, 地区ID) 列表
        """
        results = []
        for region_input in region_inputs:
            result = self.resolve(region_input)
            if result is not None:
                results.append(result)
                logger.info(f"地区解析成功: '{region_input}' -> (名称: {result[0]}, ID: {result[1]})")
            else:
                logger.warning(f"地区解析失败: '{region_input}'，未在地区表中找到匹配项")
        return results

    def get_region_table(self) -> Dict[str, int]:
        """获取第一个策略的地区映射表"""
        if self._strategies:
            return self._strategies[0].get_region_table()
        return {}


# ==========================================
# 通用策略实现（可被各网站复用）
# ==========================================

class CityNameStrategy(RegionStrategy):
    """城市名称解析策略：通过城市名称查找地区ID"""

    def __init__(self, region_table: Dict[str, int]):
        self._region_table = region_table

    def resolve(self, region_input: str) -> Optional[Tuple[str, int]]:
        region_id = self._region_table.get(region_input)
        if region_id is not None:
            return (region_input, region_id)
        return None

    def get_region_table(self) -> Dict[str, int]:
        return self._region_table


class ProvinceNameStrategy(RegionStrategy):
    """省份名称解析策略：通过省份全称或 "全XX" 查找地区ID"""

    def __init__(self, region_table: Dict[str, int], province_table: Dict[str, int]):
        self._region_table = region_table
        self._province_table = province_table

    def resolve(self, region_input: str) -> Optional[Tuple[str, int]]:
        # 先尝试省份全称
        region_id = self._province_table.get(region_input)
        if region_id is not None:
            return (region_input, region_id)
        # 再尝试 "全XX" 格式
        if not region_input.startswith("全"):
            full_name = f"全{region_input}"
            region_id = self._region_table.get(full_name)
            if region_id is not None:
                return (region_input, region_id)
        return None

    def get_region_table(self) -> Dict[str, int]:
        return self._province_table


class RegionIdStrategy(RegionStrategy):
    """地区ID解析策略：直接使用数字ID，反查地区名称"""

    _id_to_name_cache: Dict[int, Dict[int, str]] = {}

    def __init__(self, region_table: Dict[str, int]):
        self._region_table = region_table
        table_id = id(region_table)
        if table_id not in self._id_to_name_cache:
            self._id_to_name_cache[table_id] = {v: k for k, v in region_table.items()}
        self._id_to_name = self._id_to_name_cache[table_id]

    def resolve(self, region_input: str) -> Optional[Tuple[str, int]]:
        try:
            region_id = int(region_input)
        except (ValueError, TypeError):
            return None

        name = self._id_to_name.get(region_id)
        if name is not None:
            return (name, region_id)
        return None

    def get_region_table(self) -> Dict[str, int]:
        return self._region_table


# ==========================================
# 环境变量配置读取
# ==========================================

def get_search_keywords_from_env() -> List[str]:
    """从 .env 读取搜索关键词配置"""
    keywords_str = os.getenv("SEARCH_KEYWORDS", "")
    if keywords_str:
        return [k.strip() for k in keywords_str.split(",") if k.strip()]
    # 默认关键词
    return ["Python", "Java", "前端", "数据分析", "产品经理", "运营"]


def get_target_regions_from_env(factory: RegionStrategyFactory) -> List[Tuple[str, int]]:
    """
    从 .env 读取目标地区配置，返回 (地区名称, 地区ID) 列表

    .env 中 SEARCH_REGIONS 支持以下格式（逗号分隔）：
    - 城市名称：北京,上海,深圳
    - 省份名称：广东,浙江
    - 地区ID：530,538,765
    - 混合使用：北京,538,广东
    """
    regions_str = os.getenv("SEARCH_REGIONS", "")
    if not regions_str:
        # 默认城市
        default_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京"]
        return factory.resolve_all(default_cities)

    region_inputs = [r.strip() for r in regions_str.split(",") if r.strip()]
    return factory.resolve_all(region_inputs)


def get_max_page_from_env() -> int:
    """从 .env 读取最大翻页数"""
    try:
        return int(os.getenv("SEARCH_MAX_PAGE", "10"))
    except (ValueError, TypeError):
        return 10
