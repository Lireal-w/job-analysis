"""
智联校园招聘爬虫运行脚本

使用方法：
    # 默认运行（使用缓存Cookie）
    python run.py

    # 强制重新登录获取Cookie
    python run.py --force-login

    # 指定搜索关键词和城市
    python run.py --keyword="Python,Java" --city="北京,上海"

    # 指定最大翻页数
    python run.py --max-page=5

    # 仅登录获取Cookie（不启动爬虫）
    python run.py --login-only
"""

import argparse
import sys
import os
import logging

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="智联校园招聘爬虫")
    parser.add_argument("--force-login", action="store_true", help="强制重新登录获取Cookie")
    parser.add_argument("--keyword", type=str, default=None, help="搜索关键词，多个用逗号分隔")
    parser.add_argument("--city", type=str, default=None, help="城市名称，多个用逗号分隔")
    parser.add_argument("--max-page", type=int, default=None, help="最大翻页数")
    parser.add_argument("--login-only", action="store_true", help="仅登录获取Cookie，不启动爬虫")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径（支持json/csv）")

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # 仅登录模式
    if args.login_only:
        logger.info("仅登录模式：启动浏览器池获取Cookie...")
        from get_job.utils.browser_pool import BrowserPool
        from get_job.utils.drissionpage_login import refresh_cookie_via_browser
        from get_job.utils.mongo_helper import close_mongo_client
        pool = None
        try:
            pool = BrowserPool(pool_size=1, headless=False)
            cookies = refresh_cookie_via_browser(pool=pool, timeout=120)
            if cookies:
                logger.info(f"成功获取 {len(cookies)} 个Cookie，已保存到MongoDB")
            else:
                logger.error("获取Cookie失败")
        finally:
            if pool:
                pool.shutdown()
            close_mongo_client()
        return

    # 构建爬虫运行命令
    from scrapy.cmdline import execute

    cmd_args = ["scrapy", "crawl", "xiaoyuan"]

    # 传递参数给爬虫
    spider_args = []
    if args.keyword:
        spider_args.append(f"keyword={args.keyword}")
    if args.city:
        spider_args.append(f"city={args.city}")
    if args.max_page:
        spider_args.append(f"max_page={args.max_page}")

    if spider_args:
        cmd_args.extend(["-a", ",".join(spider_args)])

    # 输出文件
    if args.output:
        cmd_args.extend(["-o", args.output])

    # 强制登录设置
    if args.force_login:
        os.environ["FORCE_LOGIN"] = "True"

    logger.info(f"启动爬虫，命令: {' '.join(cmd_args)}")
    execute(cmd_args)


if __name__ == "__main__":
    main()
