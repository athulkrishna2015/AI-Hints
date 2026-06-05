import logging
import os
import threading
from logging.handlers import RotatingFileHandler

log_context = threading.local()

class ContextFilter(logging.Filter):
    def filter(self, record):
        source = getattr(log_context, "source", None)
        if source:
            record.msg = f"[{source.upper()}] {record.msg}"
        return True

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
        logger.addFilter(ContextFilter())
    return logger

logger = get_logger()

class SharedState:
    def __init__(self):
        self.GLOBAL_STOP = False

state = SharedState()

def clear_log_file():
    """Wipes the log file content and removes backup logs."""
    addon_dir = os.path.dirname(__file__)
    log_file = os.path.join(addon_dir, "ai_hints.log")
    log_backup = os.path.join(addon_dir, "ai_hints.log.1")
    try:
        if os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("Log file cleared on startup.")
        if os.path.exists(log_backup):
            try:
                os.remove(log_backup)
            except Exception as e:
                with open(log_backup, "w", encoding="utf-8") as f:
                    f.write("")
    except Exception as e:
        print(f"AI-Hints: Failed to clear log file: {e}")

def info(msg, parent=None):
    from aqt.utils import showInfo
    logger.info(f"Notification: {msg}")
    showInfo(msg, parent=parent)

def tooltip(msg, period=3000):
    from aqt.utils import tooltip as aqt_tooltip
    logger.info(f"Notification: {msg}")
    aqt_tooltip(msg, period=period)
