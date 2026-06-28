import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        handler = logging.FileHandler(log_dir / f"{timestamp}_{name}.log")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    return logger
