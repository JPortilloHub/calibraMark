"""Centralized logging configuration for CalibraMark."""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from config import get_settings


def setup_logging(log_level: Optional[str] = None) -> None:
    """
    Set up logging with both file and console handlers.

    Args:
        log_level: Optional override for log level (defaults to settings)
    """
    settings = get_settings()
    level = log_level or settings.log_level

    # Ensure log directory exists
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    simple_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler (INFO and above, simple format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Main log file (rotating)
    main_log_file = settings.log_dir / "calibramark.log"
    main_file_handler = RotatingFileHandler(
        main_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    main_file_handler.setLevel(getattr(logging, level.upper()))
    main_file_handler.setFormatter(detailed_formatter)

    # Error log file (ERROR and above only)
    error_log_file = settings.log_dir / "calibramark_errors.log"
    error_file_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(main_file_handler)
    root_logger.addHandler(error_file_handler)

    # Log startup message
    logger = logging.getLogger("calibramark")
    logger.info("=" * 80)
    logger.info(f"CalibraMark logging initialized at {datetime.now().isoformat()}")
    logger.info(f"Log level: {level}")
    logger.info(f"Log directory: {settings.log_dir.absolute()}")
    logger.info("=" * 80)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def create_agent_logger(agent_name: str) -> logging.Logger:
    """
    Create a specialized logger for an agent with its own log file.

    Args:
        agent_name: Name of the agent (e.g., "market_scanner")

    Returns:
        Logger instance for the agent
    """
    settings = get_settings()
    logger = logging.getLogger(f"agent.{agent_name}")

    # Create agent-specific log file
    agent_log_file = settings.log_dir / f"agent_{agent_name}.log"
    agent_file_handler = RotatingFileHandler(
        agent_log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    agent_file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    agent_file_handler.setFormatter(formatter)

    logger.addHandler(agent_file_handler)

    return logger
