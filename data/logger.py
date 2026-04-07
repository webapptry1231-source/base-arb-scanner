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
    """Intercept stdlib logging and route to loguru."""

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
    """Configure loguru logging with rotation and stdlib interception.

    Free-tier mode: JSON logs enabled by default for rich schema tracking.
    """
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


def log_opportunity_entry(
    timestamp: str,
    block_number: int,
    rpc_provider: str,
    rpc_latency_ms: float,
    estimated_cu_used: float,
    route: dict,
    borrow_amount_usd: float,
    gross_profit_usd: float,
    net_profit_usd: float,
    net_after_25pct_buffer: float,
    simulation_success: bool,
    stress_test_passed: bool,
    false_positive_flags: list,
    free_tier_throttled: bool,
):
    """Log a full free-tier opportunity entry with enhanced schema (Section 11)."""
    entry = {
        "timestamp": timestamp,
        "block_number": block_number,
        "rpc_provider": rpc_provider,
        "rpc_latency_ms": rpc_latency_ms,
        "estimated_cu_used": estimated_cu_used,
        "route": route,
        "borrow_amount_usd": borrow_amount_usd,
        "gross_profit_usd": gross_profit_usd,
        "net_profit_usd": net_profit_usd,
        "net_after_25pct_buffer": net_after_25pct_buffer,
        "simulation_success": simulation_success,
        "stress_test_passed": stress_test_passed,
        "false_positive_flags": false_positive_flags,
        "free_tier_throttled": free_tier_throttled,
    }
    logger.info(f"OPPORTUNITY_LOG: {entry}")
    return entry


def log_discard_entry(
    timestamp: str,
    block_number: int,
    rpc_provider: str,
    rpc_latency_ms: float,
    estimated_cu_used: float,
    route: dict,
    reason: str,
    free_tier_throttled: bool,
):
    """Log a discarded candidate (every simulation, even discards)."""
    entry = {
        "timestamp": timestamp,
        "block_number": block_number,
        "rpc_provider": rpc_provider,
        "rpc_latency_ms": rpc_latency_ms,
        "estimated_cu_used": estimated_cu_used,
        "route": route,
        "discard_reason": reason,
        "free_tier_throttled": free_tier_throttled,
    }
    logger.debug(f"DISCARD_LOG: {entry}")
    return entry
