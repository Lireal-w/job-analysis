# Job Analysis — 智能校园招聘数据爬虫

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 📋 项目简介

Job Analysis 是一个基于 **Scrapy + DrissionPage** 框架的校园招聘数据爬虫系统，专门用于采集智联校园招聘网站（https://xiaoyuan.zhaopin.com/）的职位信息。

**核心能力**：
- 🔐 **自动化登录**：使用 DrissionPage 浏览器自动化工具，自动完成登录并获取有效的 Cookie
- 🕷️ **高效采集**：基于 Scrapy 框架的异步架构，支持大规模职位数据的高效抓取
- 🧹 **数据清洗**：内置薪资解析、字段补全、数据去重等 Pipeline 处理
- 💾 **多格式存储**：支持 JSON 和 CSV 两种格式的数据导出
- 🛡️ **反爬对抗**：随机 User-Agent、Cookie 过期自动续期、请求频率控制

## 🔧 技术栈

| 技术 | 说明 |
|------|------|
| **Python 3.10+** | 开发语言 |
| **Scrapy** | 爬虫框架，负责调度、下载、解析、存储的完整流程 |
| **DrissionPage** | 浏览器自动化工具，用于启动浏览器登录获取 Cookie |
| **MongoDB** | Cookie 缓存存储数据库 |
| **python-dotenv** | 环境变量管理，数据库配置通过 `.env` 文件管理 |

## 📁 项目结构

```
job-analysis/
├── scrapy.cfg               # Scrapy 项目配置文件
├── run.py                   # 运行脚本（支持命令行参数）
├── requirements.txt         # 依赖列表
├── .env                     # 数据库配置文件（不纳入版本控制）
├── .env.example             # 数据库配置示例文件
├── get_job/                 # 主爬虫模块
│   ├── __init__.py
│   ├── items.py             # 数据模型定义（职位字段 + 公司字段）
│   ├── middlewares.py       # 中间件（Cookie注入 + 随机UA）
│   ├── pipelines.py         # 数据管道（清洗 + 去重 + JSON/CSV存储）
│   ├── settings.py          # 爬虫全局配置
│   ├── utils/
│   │   ├── __init__.py
│   │   └── drissionpage_login.py   # DrissionPage 登录工具
│   └── spiders/
│       ├── __init__.py
│       └── xiaoyuan_spider.py      # 智联校园招聘爬虫
└── .gitignore
```

## 🧩 核心模块说明

### items.py
定义 `XiaoyuanJobItem`（职位数据模型）和 `XiaoyuanCompanyItem`（公司数据模型），包含以下关键字段：
- 职位名称、薪资范围、工作地点
- 公司名称、公司 ID
- 学历要求、经验要求
- 职位标签、技能关键词
- 职位描述、发布日期等

### middlewares.py
包含以下中间件：
- **DrissionPageCookieMiddleware**：Spider 启动时自动通过 DrissionPage 登录获取 Cookie，注入到每个请求中
- **RandomUserAgentMiddleware**：随机切换 User-Agent，防止被反爬
- Cookie 过期自动重新登录机制

### pipelines.py
数据处理管道：
- `XiaoyuanDataCleanPipeline`：数据清洗（空白处理、薪资解析、字段补全）
- `XiaoyuanDedupPipeline`：根据 `job_id` 去重
- `XiaoyuanJsonPipeline`：JSON 文件存储
- `XiaoyuanCsvPipeline`：CSV 文件存储

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Lireal-w/job-analysis.git
cd job-analysis
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置 MongoDB 连接信息
```

`.env` 配置示例：
```
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DB=job_analysis
MONGODB_COLLECTION=cookies
```

### 4. 运行爬虫

```bash
# 直接运行
scrapy crawl xiaoyuan

# 或使用 run.py 脚本
python run.py
```

### 5. 查看结果

爬取完成后，数据会保存在项目根目录下的 `output.json` 和 `output.csv` 文件中。

## 🔧 配置说明

### Scrapy 配置（`settings.py`）
- `CONCURRENT_REQUESTS = 16`：并发请求数
- `DOWNLOAD_DELAY = 1`：下载延迟（秒）
- `RETRY_TIMES = 3`：重试次数

### Cookie 管理
系统通过 DrissionPage 启动 Chrome 浏览器，自动完成登录流程，将获取到的 Cookie 存入 MongoDB 并作为持久化凭证。若 Cookie 过期，中间件会自动触发重新登录。

## 📄 License

MIT License

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进本项目。
