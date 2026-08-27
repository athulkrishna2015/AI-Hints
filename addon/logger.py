import logging
import os
import threading
from logging.handlers import RotatingFileHandler

log_context = threading.local()

LOG_FILENAME = "ai_hints.log"


class ContextFilter(logging.Filter):
    def filter(self, record):
        source = getattr(log_context, "source", None)
        if source:
            record.msg = f"[{source.upper()}] {record.msg}"
        return True


def _log_path() -> str:
    """Log file lives in the profile data dir so it survives addon updates."""
    try:
        from .config_io import resolve_data_file

        return resolve_data_file(LOG_FILENAME)
    except Exception:
        return os.path.join(os.path.dirname(__file__), LOG_FILENAME)


def _build_file_handler(log_file: str) -> RotatingFileHandler:
    # 3 rotations: ai_hints.log, ai_hints.log.1, ai_hints.log.2, ai_hints.log.3 (4 files total)
    handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    return handler


def _detect_initial_level() -> int:
    try:
        from aqt import mw

        if mw is not None and mw.addonManager is not None:
            addon_package = __name__.split(".")[0]
            config = mw.addonManager.getConfig(addon_package)
            if config and config.get("debug_logging", False):
                return logging.DEBUG
    except Exception:
        pass
    return logging.INFO


def get_logger():
    logger = logging.getLogger("AI-Hints")
    if not logger.handlers:
        logger.setLevel(_detect_initial_level())

        # Check if we are running in a test environment to avoid polluting production logs
        import sys

        is_testing = (
            any("unittest" in m or "pytest" in m for m in sys.modules)
            or (len(sys.argv) > 0 and any(t in sys.argv[0] for t in ["tests", "unittest", "pytest"]))
        )

        if is_testing:
            logger.addHandler(logging.NullHandler())
            _add_context_filter(logger)
            return logger

        # NOTE: no file handler here! At import time the profile is not open
        # yet, so _log_path() would resolve to the addon folder and every log
        # stream (handler vs Logs tab vs Clear button) would split across two
        # different files. The file handler is attached once the profile opens
        # via rebind_file_logging().
        _add_context_filter(logger)

    return logger


def _add_context_filter(log: logging.Logger) -> None:
    if not any(isinstance(f, ContextFilter) for f in log.filters):
        log.addFilter(ContextFilter())


def rebind_file_logging():
    """(Re)attach the rotating file handler at the CURRENT _log_path().

    Called when the profile opens — the earliest moment the profile-scoped
    data directory is known. Closes any previously-bound file handlers (e.g.
    ones created by older builds at import time, or pointing at another
    profile) so the handler, the Logs tab and Clear Log all operate on the
    exact same file. Rolls the previous session's content over so each
    session starts with a fresh ai_hints.log.
    """
    # Detach existing file handlers first.
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)
    _add_context_filter(logger)

    log_file = _log_path()
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    except Exception:
        pass
    handler = _build_file_handler(log_file)
    logger.addHandler(handler)

    # Force a rotation on startup so each Anki session starts with a fresh ai_hints.log
    try:
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            handler.doRollover()
    except Exception:
        pass
    return log_file


logger = get_logger()


class SharedState:
    def __init__(self):
        self.GLOBAL_STOP = False


state = SharedState()


def clear_log_file():
    """Actually clears the log files (called on startup when the option is on).

    Previously this was a no-op that only logged a message; now it removes
    ai_hints.log and its rotations and reinstalls a fresh handler so logging
    keeps working afterwards.
    """
    # Detach file handlers before deleting their files.
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)

    base = _log_path()
    removed = False
    for p in (base, base + ".1", base + ".2", base + ".3"):
        try:
            if os.path.exists(p):
                os.remove(p)
                removed = True
        except OSError:
            pass

    try:
        logger.addHandler(_build_file_handler(base))
    except Exception:
        pass
    logger.info("New session started. Log cleared." if removed else "New session started. Log rotated.")


def info(msg, parent=None):
    from aqt.utils import showInfo

    logger.info(f"Notification: {msg}")
    showInfo(msg, parent=parent)


def tooltip(msg, period=3000):
    from aqt.utils import tooltip as aqt_tooltip

    logger.info(f"Notification: {msg}")
    aqt_tooltip(msg, period=period)
