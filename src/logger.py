"""
结构化日志：控制台 + 本地文件，按天轮转
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
_DATE_FMT = "%m-%d %H:%M:%S"

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FMT))

_file_handler = RotatingFileHandler(
    LOG_DIR / "ruanks.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=7,
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FMT))


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_console_handler)
        logger.addHandler(_file_handler)
    return logger
