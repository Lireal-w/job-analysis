"""Pipeline 包：统一导出所有 Pipeline 类

保持与 settings.py 中 ITEM_PIPELINES 配置的兼容性，
使得 get_job.pipelines.ClassName 的路径引用仍然有效。
"""

from get_job.pipelines.xiaoyuan import (
    XiaoyuanDataCleanPipeline,
    XiaoyuanJsonPipeline,
    XiaoyuanCsvPipeline,
    XiaoyuanDedupPipeline,
    XiaoyuanMongoPipeline,
)

from get_job.pipelines.liepin import (
    LiepinDataCleanPipeline,
    LiepinJsonPipeline,
    LiepinCsvPipeline,
    LiepinDedupPipeline,
    LiepinMongoPipeline,
)

__all__ = [
    # 智联校园招聘
    'XiaoyuanDataCleanPipeline',
    'XiaoyuanJsonPipeline',
    'XiaoyuanCsvPipeline',
    'XiaoyuanDedupPipeline',
    'XiaoyuanMongoPipeline',
    # 猎聘
    'LiepinDataCleanPipeline',
    'LiepinJsonPipeline',
    'LiepinCsvPipeline',
    'LiepinDedupPipeline',
    'LiepinMongoPipeline',
]
