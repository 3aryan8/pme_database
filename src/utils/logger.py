# src/utils/logger.py
import logging, sys, os

def setup_logger(name: str = "pipeline") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logger.addHandler(h)
    return logger