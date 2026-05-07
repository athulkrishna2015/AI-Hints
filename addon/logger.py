import logging
import os
from logging.handlers import RotatingFileHandler

def get_logger():
    logger = logging.getLogger("AI-Hints")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        addon_dir = os.path.dirname(__file__)
        log_file = os.path.join(addon_dir, "ai_hints.log")
        handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=1)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = get_logger()
