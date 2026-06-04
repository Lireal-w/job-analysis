"""
爬虫通用工具模块

包含 SSR 数据提取、登录检测、薪资解析、调试页面保存等通用工具方法。
从各爬虫模块中抽离的共用逻辑，避免代码重复。
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


# ==========================================
# SSR 数据提取
# ==========================================

def extract_ssr_data(response, variable_name: str = "window.__INITIAL_DATA__") -> dict:
    """
    从 Vue SSR 页面提取内嵌的 JavaScript 变量数据

    许多网站使用 Vue SSR，将数据内嵌在 HTML 的 script 标签中，例如：
    - <script>window.__INITIAL_DATA__ = {...}</script>
    - <script>window.__INITIAL_STATE__ = {...}</script>

    使用括号平衡法提取完整的 JSON 数据，确保正确处理嵌套结构。

    Args:
        response: Scrapy Response 对象
        variable_name: 要提取的 JavaScript 变量名，例如 "window.__INITIAL_DATA__" 或 "window.__INITIAL_STATE__"

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    # 构建正则表达式，匹配变量赋值语句
    pattern = re.escape(variable_name) + r"\s*=\s*"
    match = re.search(pattern, response.text)
    if match:
        start = match.end()
        json_str = response.text[start:]
        # 使用括号平衡法提取完整 JSON
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
                logger.info(f"成功提取 SSR 内嵌数据 ({variable_name})，键: {list(data.keys())}")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"解析 SSR 内嵌数据 ({variable_name}) 失败: {e}")

    return None


def extract_ssr_data_from_text(text: str, variable_name: str) -> dict:
    """
    从文本中提取内嵌的 JavaScript 变量数据（不需要 Scrapy Response 对象）

    Args:
        text: 包含 JavaScript 变量的文本
        variable_name: 要提取的 JavaScript 变量名

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    pattern = re.escape(variable_name) + r"\s*=\s*"
    match = re.search(pattern, text)
    if match:
        start = match.end()
        json_str = text[start:]
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
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"解析 SSR 内嵌数据 ({variable_name}) 失败: {e}")

    return None


# ==========================================
# API / JSON 数据提取
# ==========================================

def extract_json_data(response) -> dict:
    """
    从 API 响应中提取 JSON 数据

    Args:
        response: Scrapy Response 对象

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    try:
        json_data = json.loads(response.text)
        if isinstance(json_data, dict):
            return json_data
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"解析 JSON 数据失败: {e}")
    return None


# ==========================================
# 登录状态检测
# ==========================================

# 登录页面 URL 中常见的关键词
LOGIN_URL_KEYWORDS = ("login", "passport", "signin", "register")

# 登录页面标题中常见的关键词
LOGIN_TITLE_KEYWORDS = ("用户登录", "登录", "Login", "Sign In")

# 登录页面常见的 CSS 选择器
LOGIN_CSS_SELECTORS = [
    'div[class*="login-box"]',
    'div[id*="passport"]',
    'div[id*="login"]',
    'form[action*="login"]',
    'input[name*="password"]',
]


def is_login_required(response) -> bool:
    """
    检测响应是否为登录页面（Cookie 已失效）

    通过多种方式检测：
    1. 检查 URL 是否包含登录相关路径
    2. 检查页面 title 是否包含登录相关文字
    3. 检查页面是否存在登录表单组件

    Args:
        response: Scrapy Response 对象

    Returns:
        bool: 是否需要重新登录
    """
    # 方式1：检查 URL 是否包含登录相关路径
    url_lower = response.url.lower()
    if any(kw in url_lower for kw in LOGIN_URL_KEYWORDS):
        return True

    # 方式2：检查页面 title 是否包含登录相关文字
    try:
        page_title = response.css("title::text").get("")
        if any(kw in page_title for kw in LOGIN_TITLE_KEYWORDS):
            return True

        # 方式3：检查页面是否存在登录表单组件
        for selector in LOGIN_CSS_SELECTORS:
            if response.css(selector):
                return True
    except ValueError:
        # JSON 响应不支持 CSS 选择器
        pass

    return False


def is_login_page_by_content(response) -> bool:
    """
    检测200状态码响应是否实际为登录页面（更全面的检测）

    与 is_login_required 相比，额外支持 JSON 响应的检测。
    某些网站在 Cookie 失效时不会返回 302 重定向，
    而是返回 200 状态码但页面内容是登录页。

    Args:
        response: Scrapy Response 对象

    Returns:
        bool: 是否为登录页面
    """
    # 检查 URL 是否包含登录相关路径
    url_lower = response.url.lower()
    if any(kw in url_lower for kw in LOGIN_URL_KEYWORDS):
        return True

    # JSON 响应：检查是否返回了未登录的错误码
    content_type = response.headers.get(b"Content-Type", b"").decode("utf-8", errors="ignore").lower()
    if "json" in content_type:
        try:
            data = json.loads(response.text)
            status_code = data.get("statusCode", 0)
            if status_code in (401, 403):
                return True
        except (json.JSONDecodeError, TypeError):
            pass
        return False

    # 非 JSON 响应：复用通用检测逻辑
    return is_login_required(response)


# ==========================================
# 薪资解析
# ==========================================

# 面议类关键词
SALARY_NEGOTIABLE_KEYWORDS = ("面议", "negotiable", "薪资面议")

# 分隔符正则（支持 - ~ 至 到）
RANGE_SEPARATOR = r"\s*[-~至到]\s*"


def parse_salary(salary_desc: str):
    """
    通用薪资描述解析，返回 (最低月薪, 最高月薪)，单位统一为 元/月。

    支持的格式：
    - "8000-12000元/月"        -> (8000, 12000)
    - "8K-12K"                 -> (8000, 12000)
    - "8-12K"                  -> (8000, 12000)
    - "15-25K·13薪"            -> (16250, 27083)
    - "1-1.5万"                -> (10000, 15000)
    - "1.5-3万·14薪"           -> (17500, 35000)
    - "150-250元/天"           -> (3300, 5500)   按22个工作日换算
    - "15-20元/时"             -> (2640, 3520)   按8h/天、22天/月换算
    - "5000元/月"              -> (5000, 5000)
    - "面议"                   -> (None, None)

    Args:
        salary_desc: 薪资描述字符串

    Returns:
        tuple: (最低月薪, 最高月薪)，解析失败返回 (None, None)
    """
    if not salary_desc:
        return None, None

    salary_desc = salary_desc.strip()
    if not salary_desc or salary_desc in SALARY_NEGOTIABLE_KEYWORDS:
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
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)\s*元\s*/\s*天',
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
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)\s*元\s*/\s*(?:时|小时)',
            salary_desc,
        )
        if hour_match:
            min_hourly = float(hour_match.group(1))
            max_hourly = float(hour_match.group(2))
            # 按 8小时/天、22天/月 换算为月薪
            min_monthly = round(min_hourly * 8 * 22)
            max_monthly = round(max_hourly * 8 * 22)
            return min_monthly, max_monthly

        # ---- K 单位：X-YK 或 X K-YK ----
        k_match = re.match(
            r'([\d.]+)\s*[kK千]\s*' + RANGE_SEPARATOR + r'([\d.]+)\s*[kK千]',
            salary_desc,
        )
        if k_match:
            min_val = int(float(k_match.group(1)) * 1000)
            max_val = int(float(k_match.group(2)) * 1000)
            if annual_months and annual_months > 12:
                min_val = round(min_val * annual_months / 12)
                max_val = round(max_val * annual_months / 12)
            return min_val, max_val

        # ---- K 单位（简写）：X-YK（如 "15-25K"） ----
        k_short_match = re.match(
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)\s*[kK]',
            salary_desc,
        )
        if k_short_match:
            min_val = int(float(k_short_match.group(1)) * 1000)
            max_val = int(float(k_short_match.group(2)) * 1000)
            if annual_months and annual_months > 12:
                min_val = round(min_val * annual_months / 12)
                max_val = round(max_val * annual_months / 12)
            return min_val, max_val

        # ---- 万单位：X-Y万（万通常表示年薪或月薪，根据上下文判断） ----
        wan_match = re.match(
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)\s*万',
            salary_desc,
        )
        if wan_match:
            min_val = int(float(wan_match.group(1)) * 10000)
            max_val = int(float(wan_match.group(2)) * 10000)
            if annual_months and annual_months > 12:
                min_val = round(min_val * annual_months / 12)
                max_val = round(max_val * annual_months / 12)
            return min_val, max_val

        # ---- 元/月：X-Y元/月 或 X-Y元 ----
        yuan_month_match = re.match(
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)\s*元(?:\s*/\s*月)?',
            salary_desc,
        )
        if yuan_month_match:
            min_val = int(float(yuan_month_match.group(1)))
            max_val = int(float(yuan_month_match.group(2)))
            return min_val, max_val

        # ---- 纯数字范围：X-Y（无单位，默认元/月） ----
        pure_match = re.match(
            r'([\d.]+)' + RANGE_SEPARATOR + r'([\d.]+)',
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


# ==========================================
# 文本提取
# ==========================================

def extract_full_text(element) -> str:
    """
    提取元素及其所有子元素的文本内容，并清理多余空白

    Args:
        element: Scrapy Selector 元素

    Returns:
        清理后的文本字符串
    """
    texts = element.css('*::text').getall()
    combined = " ".join([t.strip() for t in texts if t.strip()])
    return re.sub(r'\s+', ' ', combined)


# ==========================================
# 调试工具
# ==========================================

def save_debug_page(response, filename: str, output_dir: str = "debug_pages"):
    """
    保存页面用于调试

    Args:
        response: Scrapy Response 对象
        filename: 保存的文件名（不含扩展名）
        output_dir: 输出目录，默认为 "debug_pages"
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{filename}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(response.text)
        logger.info(f"调试页面已保存: {filepath}")
    except Exception as e:
        logger.error(f"保存调试页面失败: {e}")
