import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("capital_saas")
    if logger.handlers:
        return logger
    app_env = os.getenv("APP_ENV", "development")
    level = logging.DEBUG if app_env == "development" else logging.INFO
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "capital_saas.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)
    security_handler = RotatingFileHandler(
        logs_dir / "security.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(
        logging.Formatter("%(asctime)s SECURITY %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(security_handler)
    return logger


logger = configure_logging()
