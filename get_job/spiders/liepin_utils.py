
"""
猎聘爬虫 - 工具方法模块

包含 SSR 数据提取、调试页面保存等工具方法。
"""

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def extract_liepin_ssr_data(response) -> dict:
    """
    从猎聘页面提取 window.__INITIAL_STATE__ 数据

    猎聘使用 Vue SSR，职位数据内嵌在 HTML 的 script 标签中：
    <script>window.__INITIAL_STATE__ = {...}</script>

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*",
        response.text,
    )
    if match:
        start = match.end()
        json_str = response.text[start:]
        # 找到 JSON 的结束位置（括号平衡）
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
                logger.info(f"成功提取猎聘 SSR 内嵌数据，键: {list(data.keys())}")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"解析猎聘 SSR 内嵌数据失败: {e}")

    return None


def extract_liepin_api_data(response) -> dict:
    """
    从猎聘 API 响应中提取数据

    猎聘搜索 API 返回 JSON 格式数据，结构为：
    {
        "flag": 1,
        "data": {
            "data": { ... }
        }
    }

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    try:
        json_data = json.loads(response.text)
        if isinstance(json_data, dict):
            return json_data
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"解析猎聘 API 数据失败: {e}")
    return None


def parse_liepin_salary(salary_desc: str):
    """
    解析猎聘薪资描述，返回 (最低月薪, 最高月薪)，单位统一为 元/月。

    猎聘常见薪资格式：
    - "15-25K"               -> (15000, 25000)
    - "15-25K·13薪"          -> (16250, 27083)
    - "150-250元/天"         -> (3300, 5500)
    - "面议"                 -> (None, None)
    - "8-12万"               -> (80000, 120000) 按年薪，折算月薪
    """
    if not salary_desc:
        return None, None

    salary_desc = salary_desc.strip()
    if not salary_desc or salary_desc in ("面议", "negotiable", "薪资面议"):
        return None, None

    try:
        # 提取年终奖月数
        annual_months = None
        bonus_match = re.search(r'[·\-\s](\d+)薪', salary_desc)
        if bonus_match:
            annual_months = int(bonus_match.group(1))
            salary_desc = salary_desc[:bonus_match.start()].strip()

        # K 单位：X-YK
        k_match = re.match(r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*[kK]', salary_desc)
        if k_match:
            min_val = int(float(k_match.group(1)) * 1000)
            max_val = int(float(k_match.group(2)) * 1000)
            if annual_months and annual_months > 12:
                min_val = round(min_val * annual_months / 12)
                max_val = round(max_val * annual_months / 12)
            return min_val, max_val

        # 万单位：X-Y万（猎聘中万通常表示年薪）
        wan_match = re.match(r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*万', salary_desc)
        if wan_match:
            min_val = int(float(wan_match.group(1)) * 10000)
            max_val = int(float(wan_match.group(2)) * 10000)
            # 万单位按年薪折算月薪
            min_val = round(min_val / 12)
            max_val = round(max_val / 12)
            if annual_months and annual_months > 12:
                min_val = round(min_val * annual_months / 12)
                max_val = round(max_val * annual_months / 12)
            return min_val, max_val

        # 按天计薪：X-Y元/天
        day_match = re.match(
            r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*元\s*/\s*天',
            salary_desc,
        )
        if day_match:
            min_daily = float(day_match.group(1))
            max_daily = float(day_match.group(2))
            min_monthly = round(min_daily * 22)
            max_monthly = round(max_daily * 22)
            return min_monthly, max_monthly

        # 元/月：X-Y元/月
        yuan_month_match = re.match(
            r'([\d.]+)\s*[-~至到]\s*([\d.]+)\s*元(?:\s*/\s*月)?',
            salary_desc,
        )
        if yuan_month_match:
            min_val = int(float(yuan_month_match.group(1)))
            max_val = int(float(yuan_month_match.group(2)))
            return min_val, max_val

        # 纯数字范围
        pure_match = re.match(
            r'([\d.]+)\s*[-~至到]\s*([\d.]+)',
            salary_desc,
        )
        if pure_match:
            min_val = float(pure_match.group(1))
            max_val = float(pure_match.group(2))
            if min_val < 100:
                min_val = int(min_val * 1000)
                max_val = int(max_val * 1000)
            else:
                min_val = int(min_val)
                max_val = int(max_val)
            return min_val, max_val

    except (ValueError, AttributeError):
        pass

    return None, None


def save_debug_page(response, filename: str):
    """保存页面用于调试"""
    try:
        output_dir = "debug_pages"
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{filename}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(response.text)
        logger.info(f"调试页面已保存: {filepath}")
    except Exception as e:
        logger.error(f"保存调试页面失败: {e}")
