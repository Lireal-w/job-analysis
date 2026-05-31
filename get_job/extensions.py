"""
Scrapy 扩展模块
"""

import logging
import os

from scrapy import signals

logger = logging.getLogger(__name__)


class LogFileExtension:
    """
    日志文件扩展
    在 Scrapy 日志配置完成后，给 root logger 添加 FileHandler，
    使日志同时输出到控制台和 main.log 文件。

    为什么不在 run.py 中直接添加 FileHandler？
    因为 Scrapy 的 execute() 内部会调用 configure_logging()，
    该函数会清除之前添加的所有 handler 并替换为 Scrapy 自己的 handler。
    所以必须在 Scrapy 日志配置完成后再添加 FileHandler。
    """

    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        self.file_handler = None

    @classmethod
    def from_crawler(cls, crawler):
        log_file_path = os.getenv("LOG_FILE_PATH", None)
        if not log_file_path:
            # 返回一个不添加 FileHandler 的空实例，避免 Scrapy 报错
            ext = cls(None)
            return ext

        ext = cls(log_file_path)

        # 在 from_crawler 阶段就添加 FileHandler
        # 此时 Scrapy 的 configure_logging() 已完成，root logger 已就绪
        # 且 start_requests 尚未执行，确保所有日志都能写入文件
        log_format = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        ext.file_handler = logging.FileHandler(ext.log_file_path, encoding="utf-8")
        ext.file_handler.setLevel(logging.DEBUG)
        ext.file_handler.setFormatter(log_format)

        root_logger = logging.getLogger()
        root_logger.addHandler(ext.file_handler)

        logger.info(f"日志文件扩展已启用，日志输出到: {ext.log_file_path}")

        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_closed(self, spider, reason):
        """Spider 关闭时关闭 FileHandler"""
        if self.file_handler:
            self.file_handler.close()
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.file_handler)
            logger.info(f"日志文件扩展已关闭: {self.log_file_path}")
