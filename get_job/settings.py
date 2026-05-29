# Scrapy settings for get_job project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

BOT_NAME = "get_job"

SPIDER_MODULES = ["get_job.spiders"]
NEWSPIDER_MODULE = "get_job.spiders"

ADDONS = {}

# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Obey robots.txt rules (校园招聘网站通常需要关闭此选项以允许爬取)
ROBOTSTXT_OBEY = False

# Concurrency and throttling settings
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 2

# Enable cookies (需要 Cookie 来维持登录状态)
COOKIES_ENABLED = True
COOKIES_DEBUG = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://xiaoyuan.zhaopin.com/",
}

# Enable or disable spider middlewares
SPIDER_MIDDLEWARES = {
    "get_job.middlewares.GetJobSpiderMiddleware": 543,
}

# Enable or disable downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    # DrissionPage Cookie 注入中间件（优先级最高，确保所有请求都携带 Cookie）
    "get_job.middlewares.DrissionPageCookieMiddleware": 100,
    # 随机 User-Agent 中间件
    "get_job.middlewares.RandomUserAgentMiddleware": 400,
    # 默认下载中间件
    "get_job.middlewares.GetJobDownloaderMiddleware": 543,
}

# Enable or disable extensions
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
ITEM_PIPELINES = {
    # 数据清洗管道（优先执行）
    "get_job.pipelines.XiaoyuanDataCleanPipeline": 100,
    # 去重管道
    "get_job.pipelines.XiaoyuanDedupPipeline": 200,
    # MongoDB 存储管道
    "get_job.pipelines.XiaoyuanMongoPipeline": 300,
    # JSON 存储管道
    "get_job.pipelines.XiaoyuanJsonPipeline": 400,
    # CSV 存储管道
    "get_job.pipelines.XiaoyuanCsvPipeline": 401,
}

# Enable and configure the AutoThrottle extension (disabled by default)
AUTOTHROTTLE_ENABLED = True
# The initial download delay
AUTOTHROTTLE_START_DELAY = 2
# The maximum download delay to be set in case of high latencies
AUTOTHROTTLE_MAX_DELAY = 10
# The average number of requests Scrapy should be sending in parallel to
# each remote server
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
# Enable showing throttling stats for every response received:
AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

# ==========================================
# 自定义配置
# ==========================================

# 是否强制重新登录获取 Cookie（设为 True 则每次启动爬虫都会打开浏览器登录）
FORCE_LOGIN = False

# 登录超时时间（秒）
LOGIN_TIMEOUT = 120

# 浏览器池大小
BROWSER_POOL_SIZE = 3

# MongoDB 配置（从 .env 文件读取，此处为默认值）
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "job_analysis")

# MongoDB 数据存储集合
MONGODB_JOB_COLLECTION = os.getenv("MONGODB_JOB_COLLECTION", "jobs")
MONGODB_COMPANY_COLLECTION = os.getenv("MONGODB_COMPANY_COLLECTION", "companies")

# Redis 配置（Cookie 缓存）
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") or None
REDIS_DATABASE = int(os.getenv("REDIS_DATABASE", "0"))
REDIS_COOKIE_KEY_PREFIX = os.getenv("REDIS_COOKIE_KEY_PREFIX", "cookie")
COOKIE_EXPIRE_SECONDS = int(os.getenv("COOKIE_EXPIRE_SECONDS", "86400"))

# 日志级别
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

# 重试设置
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# 下载超时
DOWNLOAD_TIMEOUT = 30
