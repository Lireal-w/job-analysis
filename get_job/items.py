# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class XiaoyuanJobItem(scrapy.Item):
    """智联校园招聘职位数据模型"""

    # 基本信息
    job_id = scrapy.Field()            # 职位ID
    job_title = scrapy.Field()         # 职位名称
    job_category = scrapy.Field()      # 职位类别
    job_type = scrapy.Field()          # 工作类型（全职/兼职/实习）

    # 公司信息
    company_id = scrapy.Field()        # 公司ID
    company_name = scrapy.Field()      # 公司名称
    company_type = scrapy.Field()      # 公司类型（国企/外企/民营等）
    company_scale = scrapy.Field()     # 公司规模
    company_industry = scrapy.Field()  # 公司行业

    # 薪资与地点
    salary_min = scrapy.Field()        # 最低薪资（元/月）
    salary_max = scrapy.Field()        # 最高薪资（元/月）
    salary_desc = scrapy.Field()       # 薪资描述（原始文本）
    work_city = scrapy.Field()         # 工作城市
    work_district = scrapy.Field()     # 工作区域
    work_address = scrapy.Field()      # 详细工作地址

    # 职位详情
    education = scrapy.Field()         # 学历要求
    experience = scrapy.Field()        # 经验要求
    job_description = scrapy.Field()   # 职位描述
    job_requirement = scrapy.Field()   # 任职要求
    skills = scrapy.Field()            # 技能要求列表
    welfare = scrapy.Field()           # 福利待遇

    # 招聘信息
    recruit_num = scrapy.Field()       # 招聘人数
    publish_date = scrapy.Field()      # 发布日期
    deadline = scrapy.Field()          # 截止日期
    is_urgent = scrapy.Field()         # 是否急聘

    # 元数据
    source_url = scrapy.Field()        # 来源URL
    crawl_time = scrapy.Field()        # 爬取时间
    source_platform = scrapy.Field()   # 来源平台


class XiaoyuanCompanyItem(scrapy.Item):
    """智联校园招聘公司数据模型"""

    company_id = scrapy.Field()        # 公司ID
    company_name = scrapy.Field()      # 公司名称
    company_short_name = scrapy.Field() # 公司简称
    company_type = scrapy.Field()      # 公司类型
    company_scale = scrapy.Field()     # 公司规模
    company_industry = scrapy.Field()  # 公司行业
    company_description = scrapy.Field() # 公司简介
    company_address = scrapy.Field()   # 公司地址
    company_website = scrapy.Field()   # 公司网站
    company_logo = scrapy.Field()      # 公司Logo URL

    # 元数据
    source_url = scrapy.Field()        # 来源URL
    crawl_time = scrapy.Field()        # 爬取时间
    source_platform = scrapy.Field()   # 来源平台
