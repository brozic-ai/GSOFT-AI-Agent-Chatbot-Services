"""
Cấu hình Logging tập trung cho toàn bộ ứng dụng.

Cách dùng:
    # Trong main.py (gọi 1 lần duy nhất khi khởi động)
    from app.core.logging import setup_logging
    setup_logging()

    # Trong bất kỳ module nào
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Hello")
"""

import sys
import logging
from typing import Optional

from app.core.config import settings

# Mapping tên environment → log level
_ENV_LOG_LEVELS = {
    "local": logging.DEBUG,
    "development": logging.DEBUG,
    "staging": logging.INFO,
    "production": logging.WARNING,
}

# Format cho từng môi trường
_DEV_FORMAT = (
    "%(asctime)s │ %(levelname)-8s │ %(name)s:%(lineno)d │ %(message)s"
)
_PROD_FORMAT = (
    "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s"
)


def setup_logging(
    level: Optional[int] = None,
    log_format: Optional[str] = None,
) -> None:
    """
    Thiết lập logging cho toàn bộ ứng dụng. Gọi 1 lần trong main.py.

    Args:
        level: Ghi đè log level (mặc định tự chọn theo ENVIRONMENT).
        log_format: Ghi đè format string (mặc định tự chọn theo ENVIRONMENT).
    """
    env = settings.ENVIRONMENT.lower()

    # Xác định log level
    if level is None:
        level = _ENV_LOG_LEVELS.get(env, logging.INFO)

    # Xác định format
    if log_format is None:
        log_format = _DEV_FORMAT if env in ("local", "development") else _PROD_FORMAT

    # Reset root logger (tránh duplicate handlers khi reload)
    root = logging.getLogger()
    root.setLevel(level)

    # Xóa handlers cũ nếu có (do uvicorn --reload)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler — ghi ra stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(console_handler)

    # Giảm noise từ các thư viện bên thứ ba
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Log thông tin khởi tạo
    root.info(
        "📋 Logging configured: level=%s, environment=%s",
        logging.getLevelName(level),
        env,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Trả về logger theo tên module. Tiện ích thay thế logging.getLogger().

    Dùng:
        logger = get_logger(__name__)
        logger.info("Processing request...")
    """
    return logging.getLogger(name)
