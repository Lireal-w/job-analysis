# 🔍 Job Analysis — 公开招聘数据爬虫

## 📌 Situation（项目背景）

在求职市场中，招聘信息分散在各大招聘网站上，求职者难以快速获取和对比不同平台的工作机会。为了高效收集公开招聘数据，进行职位趋势分析、薪资水平对比和技能需求挖掘，需要一个自动化的数据采集工具。

本项目基于 **Scrapy** 框架，定向爬取公开招聘网站的职位信息，为后续数据分析提供结构化的数据支撑。

---

## 🎯 Task（项目目标）

- 从公开招聘网站自动采集职位数据，包括职位名称、薪资范围、工作地点、公司信息、技能要求等关键字段
- 以结构化方式存储爬取结果，便于后续数据分析与可视化
- 遵守网站爬取规则，控制请求频率，做到负责任地爬取
- 提供可扩展的爬虫架构，方便接入更多招聘数据源

---

## ⚙️ Action（技术实现）

### 技术栈

| 技术 | 说明 |
|------|------|
| Python | 开发语言 |
| Scrapy | 爬虫框架，负责调度、下载、解析、存储的完整流程 |
| itemadapter | Item 适配器，统一处理不同类型的数据项 |

### 项目结构

```
job-analysis/
├── scrapy.cfg                  # Scrapy 项目配置文件
├── get_job/                    # 主爬虫模块
│   ├── __init__.py
│   ├── items.py                # 数据模型定义（职位字段）
│   ├── middlewares.py          # 中间件（Spider中间件 + Downloader中间件）
│   ├── pipelines.py            # 数据管道（清洗、验证、持久化存储）
│   ├── settings.py             # 爬虫全局配置
│   └── spiders/                # 爬虫目录
│       └── __init__.py
└── .gitignore
```

### 核心模块说明

- **items.py** — 定义 `GetJobItem` 数据模型，声明需要采集的职位字段（职位名称、薪资、地点、公司等）
- **pipelines.py** — 数据处理管道，负责对爬取到的原始数据进行清洗、验证和持久化存储
- **middlewares.py** — 包含 Spider 中间件与 Downloader 中间件，可用于请求拦截、响应处理、异常捕获等
- **settings.py** — 全局配置，已设置以下关键策略：
  - `ROBOTSTXT_OBEY = True`：遵守 robots.txt 协议
  - `CONCURRENT_REQUESTS_PER_DOMAIN = 1`：每域名并发请求数为 1，避免对目标站点造成压力
  - `DOWNLOAD_DELAY = 1`：请求间隔 1 秒，控制爬取速率
  - `FEED_EXPORT_ENCODING = "utf-8"`：导出编码为 UTF-8，确保中文数据正确输出
- **spiders/** — 爬虫实现目录，每个招聘网站的爬虫作为独立模块存放

---

## 📊 Result（项目成果）

- ✅ 搭建了基于 Scrapy 的完整爬虫项目骨架，模块职责清晰，易于扩展
- ✅ 内置请求限速与合规配置，确保对目标网站的友好访问
- ✅ 支持通过 Pipeline 灵活扩展数据存储方式（JSON / CSV / 数据库等）
- ✅ 可通过添加新的 Spider 快速接入更多招聘数据源

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Scrapy 2.x

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
pip install scrapy
```

### 运行爬虫

```bash
# 运行指定爬虫，结果导出为 JSON
scrapy crawl <spider_name> -o output.json

# 运行指定爬虫，结果导出为 CSV
scrapy crawl <spider_name> -o output.csv
```

---

## 📜 免责声明

本项目仅供学习与技术研究使用，请遵守目标网站的 `robots.txt` 协议及相关法律法规。使用者需自行承担因不当使用而产生的法律责任。
