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
        log_level = logging.INFO
        try:
            from aqt import mw
            if mw is not None and mw.addonManager is not None:
                addon_package = __name__.split(".")[0]
                config = mw.addonManager.getConfig(addon_package)
                if config and config.get("debug_logging", False):
                    log_level = logging.DEBUG
        except Exception:
            pass
        logger.setLevel(log_level)
        
        # Check if we are running in a test environment to avoid polluting production logs
        import sys
        is_testing = (
            any("unittest" in m or "pytest" in m for m in sys.modules) or
            (len(sys.argv) > 0 and any(t in sys.argv[0] for t in ["tests", "unittest", "pytest"]))
        )
        
        if is_testing:
            logger.addHandler(logging.NullHandler())
            return logger

        addon_dir = os.path.dirname(__file__)
        log_file = os.path.join(addon_dir, "ai_hints.log")
        # 3 levels: ai_hints.log, ai_hints.log.1, ai_hints.log.2
        handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addFilter(ContextFilter())
        
        # Force a rotation on startup so each Anki session starts with a fresh ai_hints.log
        try:
            if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
                handler.doRollover()
        except Exception:
            pass
            
    return logger

logger = get_logger()

class SharedState:
    def __init__(self):
        self.GLOBAL_STOP = False

state = SharedState()

def clear_log_file():
    """No longer strictly needed as get_logger() handles rotation on startup."""
    logger.info("New session started. Log rotated.")

def info(msg, parent=None):
    from aqt.utils import showInfo
    logger.info(f"Notification: {msg}")
    showInfo(msg, parent=parent)

def tooltip(msg, period=3000):
    from aqt.utils import tooltip as aqt_tooltip
    logger.info(f"Notification: {msg}")
    aqt_tooltip(msg, period=period)
