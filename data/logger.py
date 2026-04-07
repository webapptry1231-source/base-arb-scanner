import sys
import logging
from loguru import logger


LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

JSON_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
)


class InterceptHandler(logging.Handler):
    """BUG 10 FIX: Intercept stdlib logging and route to loguru."""

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(log_level: str = "INFO", json_logs: bool = False):
    """Configure loguru logging with rotation and stdlib interception."""
    logger.remove()

    if json_logs:
        logger.add(
            sys.stdout,
            format=JSON_LOG_FORMAT,
            level=log_level,
            rotation="1 day",
            retention="7 days",
            compression="zip",
            serialize=True,
        )
        logger.add(
            "logs/scanner_{time:YYYY-MM-DD}.log",
            format=JSON_LOG_FORMAT,
            level=log_level,
            rotation="1 day",
            retention="30 days",
            compression="zip",
            serialize=True,
        )
    else:
        logger.add(
            sys.stdout,
            format=LOG_FORMAT,
            level=log_level,
            colorize=True,
        )
        logger.add(
            "logs/scanner_{time:YYYY-MM-DD}.log",
            format=JSON_LOG_FORMAT,
            level=log_level,
            rotation="1 day",
            retention="30 days",
            compression="zip",
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    logger.info(f"Logging configured: level={log_level}, json={json_logs}")
    return logger
