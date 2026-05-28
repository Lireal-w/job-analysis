# 🔍 Job Analysis — 智能校园招聘数据爬虫

## 📌 Situation（项目背景）

在求职市场中，招聘信息分散在各大招聘网站上，求职者难以快速获取和对比不同平台的工作机会。为了高效收集公开招聘数据，进行职位趋势分析、薪资水平对比和技能需求挖掘，需要一个自动化的数据采集工具。

本项目基于 **Scrapy + DrissionPage** 框架，定向爬取智联校园招聘（https://xiaoyuan.zhaopin.com/）的职位信息，为后续数据分析提供结构化的数据支撑。

---

## 🎯 Task（项目目标）

- 从智联校园招聘网站自动采集职位数据，包括职位名称、薪资范围、工作地点、公司信息、技能要求等关键字段
- 使用 DrissionPage 启动浏览器登录获取 Cookie，突破登录限制
- 以结构化方式存储爬取结果（JSON + CSV），便于后续数据分析与可视化
- 控制请求频率，随机 User-Agent，做到负责任地爬取
- 提供可扩展的爬虫架构，方便接入更多招聘数据源

---

## ⚙️ Action（技术实现）

### 技术栈

| 技术 | 说明 |
|------|------|
| Python | 开发语言 |
| Scrapy | 爬虫框架，负责调度、下载、解析、存储的完整流程 |
| DrissionPage | 浏览器自动化工具，用于启动浏览器登录获取 Cookie |
| MongoDB | Cookie 缓存存储数据库 |
| python-dotenv | 环境变量管理，数据库配置通过 .env 文件管理 |
| itemadapter | Item 适配器，统一处理不同类型的数据项 |

### 项目结构

```
job-analysis/
├── scrapy.cfg                  # Scrapy 项目配置文件
├── run.py                      # 运行脚本（支持命令行参数）
├── requirements.txt            # 依赖列表
├── .env                        # 数据库配置文件（不纳入版本控制）
├── .env.example                # 数据库配置示例文件
├── get_job/                    # 主爬虫模块
│   ├── __init__.py
│   ├── items.py                # 数据模型定义（职位字段 + 公司字段）
│   ├── middlewares.py          # 中间件（Cookie注入 + 随机UA）
│   ├── pipelines.py            # 数据管道（清洗 + 去重 + JSON/CSV存储）
│   ├── settings.py             # 爬虫全局配置
│   ├── utils/                  # 工具模块
│   │   ├── __init__.py
│   │   └── drissionpage_login.py  # DrissionPage 登录工具
│   └── spiders/                # 爬虫目录
│       ├── __init__.py
│       └── xiaoyuan_spider.py  # 智联校园招聘爬虫
└── .gitignore
```

### 核心模块说明

- **items.py** — 定义 `XiaoyuanJobItem`（职位数据模型）和 `XiaoyuanCompanyItem`（公司数据模型）
- **middlewares.py** — 包含以下中间件：
  - `DrissionPageCookieMiddleware`：Spider 启动时自动通过 DrissionPage 登录获取 Cookie，注入到每个请求中
  - `RandomUserAgentMiddleware`：随机切换 User-Agent，防止被反爬
  - Cookie 过期自动重新登录机制
- **pipelines.py** — 数据处理管道：
  - `XiaoyuanDataCleanPipeline`：数据清洗（空白处理、薪资解析、字段补全）
  - `XiaoyuanDedupPipeline`：根据 job_id 去重
  - `XiaoyuanJsonPipeline`：JSON 文件存储
  - `XiaoyuanCsvPipeline`：CSV 文件存储
- **utils/drissionpage_login.py** — DrissionPage 登录工具：
  - 启动 Chromium 浏览器访问智联校园招聘
  - 等待用户手动完成登录
  - 自动检测登录状态
  - 获取 Cookie 并缓存到 MongoDB 数据库
- **utils/mongo_helper.py** — MongoDB 工具模块：
  - MongoDB 连接管理（单例模式）
  - Cookie 的保存、加载、删除操作
  - Cookie 过期检测
  - 数据库配置通过 `.env` 文件管理
- **spiders/xiaoyuan_spider.py** — 智联校园招聘爬虫：
  - 支持按关键词、城市搜索职位
  - 支持自动翻页
  - 解析职位列表页和详情页
  - 同时爬取公司信息
- **settings.py** — 全局配置：
  - `ROBOTSTXT_OBEY = False`：允许爬取
  - `CONCURRENT_REQUESTS_PER_DOMAIN = 2`：控制并发
  - `DOWNLOAD_DELAY = 2`：请求间隔
  - `AUTOTHROTTLE_ENABLED = True`：自动限速
  - Cookie 注入和随机 UA 中间件已启用

### 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    启动爬虫 (scrapy crawl xiaoyuan)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  DrissionPageCookieMiddleware 初始化                         │
│  ├── 检查 MongoDB 中的 Cookie 缓存                            │
│  ├── 如果缓存存在且未过期 → 直接使用                           │
│  └── 如果缓存不存在或已过期 → 启动浏览器登录获取 Cookie           │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  访问首页验证 Cookie 有效性                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  按关键词 × 城市 × 页码 构建搜索请求                           │
│  每个请求自动注入 Cookie 和随机 User-Agent                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  解析职位列表页 → 提取职位基本信息和详情链接                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  访问职位详情页 → 提取完整职位信息和公司信息                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  数据管道处理：清洗 → 去重 → 存储 (JSON + CSV)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Result（项目成果）

- ✅ 搭建了基于 Scrapy + DrissionPage 的完整爬虫项目，支持浏览器登录获取 Cookie
- ✅ 内置 Cookie 自动注入和过期重新登录机制
- ✅ 内置请求限速、随机 UA、自动限速等反反爬策略
- ✅ 支持数据清洗、去重、JSON/CSV 多格式存储
- ✅ 可通过命令行参数灵活控制搜索关键词、城市、翻页数
- ✅ 可通过添加新的 Spider 快速接入更多招聘数据源

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Chrome 浏览器（DrissionPage 依赖）

### 安装步骤

```bash
# 克隆项目
git clone <repository-url>
cd job-analysis

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 首次登录获取 Cookie

```bash
# 方式1：仅登录获取Cookie（推荐首次使用）
python run.py --login-only

# 方式2：运行爬虫时自动登录
python run.py --force-login
```

> 首次运行会打开 Chrome 浏览器，请在浏览器中手动完成登录操作，登录成功后程序会自动获取并缓存 Cookie。

### 运行爬虫

```bash
# 默认运行（使用缓存Cookie）
python run.py

# 指定搜索关键词和城市
python run.py --keyword="Python,数据分析" --city="北京,上海,深圳"

# 指定最大翻页数
python run.py --max-page=5

# 强制重新登录
python run.py --force-login

# 输出到指定文件
python run.py --output=result.json

# 使用 Scrapy 命令直接运行
scrapy crawl xiaoyuan
scrapy crawl xiaoyuan -a keyword=Python -a city=北京 -a max_page=5
```

### 输出文件

爬取结果自动保存到 `get_job/output/` 目录下：
- `xiaoyuan_jobs_YYYYMMDD_HHMMSS.json` — JSON 格式
- `xiaoyuan_jobs_YYYYMMDD_HHMMSS.csv` — CSV 格式

---

## ⚠️ 注意事项

1. 首次使用需要手动登录，程序会打开浏览器等待你完成登录操作
2. Cookie 会缓存到 MongoDB 数据库，后续运行无需重复登录
3. 如果 Cookie 过期（默认24小时），中间件会自动检测并重新登录
4. 数据库配置通过 `.env` 文件管理，首次使用请复制 `.env.example` 为 `.env` 并修改配置
4. 请合理控制爬取频率，避免对目标网站造成过大压力
5. 如需修改搜索关键词和城市，可编辑 `settings.py` 或通过命令行参数指定

---

## 📜 免责声明

本项目仅供学习与技术研究使用，请遵守目标网站的 `robots.txt` 协议及相关法律法规。使用者需自行承担因不当使用而产生的法律责任。
