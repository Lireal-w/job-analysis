"""
智联校园招聘爬虫 - 工具方法模块

包含 SSR 数据提取、认证参数提取、调试页面保存等工具方法。
"""

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def extract_ssr_data(response) -> dict:
    """
    从 Vue SSR 页面提取 window.__INITIAL_DATA__ 数据

    智联校园招聘使用 Vue SSR，职位数据内嵌在 HTML 的 script 标签中：
    <script>window.__INITIAL_DATA__ = {...}</script>

    Returns:
        解析后的字典数据，提取失败返回 None
    """
    # 从完整响应文本中提取 window.__INITIAL_DATA__ = {...};
    # 使用括号平衡匹配来正确提取嵌套 JSON
    match = re.search(
        r"window\.__INITIAL_DATA__\s*=\s*",
        response.text,
    )
    if match:
        # 找到起始位置后，使用括号平衡法提取完整 JSON
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
                logger.info(f"成功提取 SSR 内嵌数据，键: {list(data.keys())}")
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"解析 SSR 内嵌数据失败: {e}")

    return None


def extract_auth_params(ssr_data: dict, response) -> dict:
    """
    从 Cookie 和 SSR 数据中提取 API 分页请求所需的认证参数

    at/rt 来自请求 Cookie，d (client-id) 和 cvNumber 来自 SSR 数据。

    Returns:
        认证参数字典，提取失败返回 None
    """
    # 从 Cookie 中提取 at 和 rt
    cookies = {}
    for cookie in response.headers.getlist("Set-Cookie"):
        parts = cookie.decode("utf-8", errors="ignore").split(";")[0]
        if "=" in parts:
            k, v = parts.split("=", 1)
            cookies[k.strip()] = v.strip()

    # 也从请求 Cookie 头中提取（可能 Set-Cookie 没有这些值）
    request_cookies = {}
    cookie_header = response.request.headers.get("Cookie", b"").decode("utf-8", errors="ignore")
    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                request_cookies[k.strip()] = v.strip()

    # 优先从请求 Cookie 获取 at/rt
    at = request_cookies.get("at", "") or cookies.get("at", "")
    rt = request_cookies.get("rt", "") or cookies.get("rt", "")

    # 从 SSR 数据中提取 d (client-id) 和 cvNumber
    request_params = ssr_data.get("position", {}).get("requestParams", {})
    basedata = ssr_data.get("basedata", {})
    user_info = ssr_data.get("main", {}).get("userInfo", {})

    d = request_params.get("d", "") or basedata.get("d", "")
    order = request_params.get("order", 12)
    cv_number = ""
    resumes = user_info.get("resumes", [])
    if resumes and isinstance(resumes, list):
        cv_number = resumes[0].get("number", "")

    # d 也可能来自 Cookie 中的 x-zp-client-id
    if not d:
        d = request_cookies.get("x-zp-client-id", "") or cookies.get("x-zp-client-id", "")

    if not at or not rt:
        logger.warning(f"未找到完整的认证参数 at/rt (at={'有' if at else '无'}, rt={'有' if rt else '无'})")
        return None

    auth_params = {
        "at": at,
        "rt": rt,
        "d": d,
        "order": order,
        "cvNumber": cv_number,
    }
    logger.info(f"提取到认证参数: at={at[:8]}..., rt={rt[:8]}..., d={d[:8] if d else '无'}...")
    return auth_params


def extract_full_text(element) -> str:
    """
    提取元素及其所有子元素的文本内容，并清理多余空白
    """
    texts = element.css('*::text').getall()
    combined = " ".join([t.strip() for t in texts if t.strip()])
    return re.sub(r'\s+', ' ', combined)


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
