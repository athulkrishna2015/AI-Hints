from .reviewer_hooks import init_hooks
from .config_ui import init_config_ui, ADDON_PACKAGE
from .logger import clear_log_file
from aqt import mw

# Clear logs on startup if enabled
config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
if config.get("auto_clear_logs", True):
    clear_log_file()

init_hooks()
init_config_ui()
