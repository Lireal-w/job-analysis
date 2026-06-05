"""Pipeline 包：统一导出所有 Pipeline 类

合并多平台同类管道，根据 Item 类型自动分发到对应分支。
同时保留旧类名别名，确保 settings.py 中的路径引用仍然有效。
"""

from get_job.pipelines.pipelines import (
    DataCleanPipeline,
    JsonPipeline,
    DedupPipeline,
    MongoPipeline,
)

# 兼容旧配置的别名
XiaoyuanDataCleanPipeline = DataCleanPipeline
XiaoyuanJsonPipeline = JsonPipeline
XiaoyuanDedupPipeline = DedupPipeline
XiaoyuanMongoPipeline = MongoPipeline
LiepinDataCleanPipeline = DataCleanPipeline
LiepinJsonPipeline = JsonPipeline
LiepinDedupPipeline = DedupPipeline
LiepinMongoPipeline = MongoPipeline

__all__ = [
    # 统一管道
    'DataCleanPipeline',
    'JsonPipeline',
    'DedupPipeline',
    'MongoPipeline',
    # 兼容旧配置的别名
    'XiaoyuanDataCleanPipeline',
    'XiaoyuanJsonPipeline',
    'XiaoyuanDedupPipeline',
    'XiaoyuanMongoPipeline',
    'LiepinDataCleanPipeline',
    'LiepinJsonPipeline',
    'LiepinDedupPipeline',
    'LiepinMongoPipeline',
]
