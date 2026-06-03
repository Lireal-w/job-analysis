"""
招聘网站爬虫运行脚本

支持平台：智联校园招聘(xiaoyuan)、猎聘(liepin)

使用方法：
    # 默认运行智联校园招聘爬虫
    python run.py

    # 运行猎聘爬虫
    python run.py --spider liepin

    # 强制重新登录获取Cookie
    python run.py --force-login
    python run.py --spider liepin --force-login

    # 指定搜索关键词和地区（支持城市名、省份名、地区ID）
    python run.py --keyword="Python,Java" --region="北京,上海,530"
    python run.py --spider liepin --keyword="Python,Java" --region="北京,上海"

    # 指定最大翻页数
    python run.py --max-page=5

    # 仅登录获取Cookie（不启动爬虫）
    python run.py --login-only
    python run.py --spider liepin --login-only
"""

import argparse
import sys
import os
import logging

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 将项目根目录添加到 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 日志文件路径
LOG_FILE = os.path.join(PROJECT_ROOT, "main.log")


def setup_file_logging():
    """配置日志同时输出到控制台和 main.log 文件"""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 控制台 Handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(console_handler)

    # 文件 Handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(file_handler)


# 爬虫名称与对应的 Spider 类映射
SPIDER_MAP = {
    "xiaoyuan": "get_job.spiders.xiaoyuan_spider.XiaoyuanSpider",
    "liepin": "get_job.spiders.liepin_spider.LiepinSpider",
}


def _get_spider_class(spider_name: str):
    """根据爬虫名称动态导入并返回 Spider 类"""
    import importlib
    module_path = SPIDER_MAP[spider_name]
    module_name, class_name = module_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def main():
    parser = argparse.ArgumentParser(description="招聘网站爬虫（支持智联校园招聘、猎聘等平台）")
    parser.add_argument("--spider", type=str, default="xiaoyuan",
                        choices=list(SPIDER_MAP.keys()),
                        help="选择爬虫：xiaoyuan(智联校园招聘)、liepin(猎聘)，默认 xiaoyuan")
    parser.add_argument("--force-login", action="store_true", help="强制重新登录获取Cookie")
    parser.add_argument("--keyword", type=str, default=None, help="搜索关键词，多个用逗号分隔")
    parser.add_argument("--region", type=str, default=None, help="目标地区，多个用逗号分隔（支持城市名、省份名、地区ID）")
    parser.add_argument("--max-page", type=int, default=None, help="最大翻页数")
    parser.add_argument("--login-only", action="store_true", help="仅登录获取Cookie，不启动爬虫")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径（支持json/csv）")

    args = parser.parse_args()

    # 仅登录模式
    if args.login_only:
        setup_file_logging()
        logger = logging.getLogger(__name__)

        spider_class = _get_spider_class(args.spider)

        logger.info(f"仅登录模式：启动浏览器获取 {args.spider} Cookie...")
        from get_job.utils.drissionpage_login import get_cookies_with_login
        from get_job.utils.redis_helper import close_redis_client
        try:
            cookies = get_cookies_with_login(
                url=spider_class.site_url,
                is_logged_in=spider_class.is_logged_in,
                force_login=True,
            )
            if cookies:
                logger.info(f"成功获取 {len(cookies)} 个Cookie，已保存到Redis")
            else:
                logger.error("获取Cookie失败")
        except Exception as e:
            logger.error(f"获取Cookie时发生错误：{e}")
        finally:
            close_redis_client()
        return

    # 爬虫模式：通过环境变量传递日志文件路径给 Scrapy Extension
    # Extension 会在 Scrapy 日志配置完成后再添加 FileHandler
    os.environ["LOG_FILE_PATH"] = LOG_FILE

    # 构建爬虫运行命令
    from scrapy.cmdline import execute

    cmd_args = ["scrapy", "crawl", args.spider]

    # 传递参数给爬虫
    spider_args = []
    if args.keyword:
        spider_args.append(f"keyword={args.keyword}")
    if args.region:
        spider_args.append(f"region={args.region}")
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

    execute(cmd_args)


if __name__ == "__main__":
    main()
