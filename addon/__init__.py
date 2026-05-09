ADDON_PACKAGE = __name__.split(".")[0]

try:
    from aqt import mw
except Exception:
    mw = None

if mw is not None and getattr(mw, "addonManager", None) is not None:
    from .reviewer_hooks import init_hooks
    from .config_ui import init_config_ui
    from .logger import clear_log_file

    # Clear logs on startup if enabled
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    if config.get("auto_clear_logs", True):
        clear_log_file()

    init_hooks()
    init_config_ui()
