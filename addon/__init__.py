ADDON_PACKAGE = __name__.split(".")[0]

try:
    from aqt import mw
except Exception:
    mw = None

if mw is not None and getattr(mw, "addonManager", None) is not None:
    from .reviewer_hooks import init_hooks
    from .config_ui import init_config_ui
    from aqt import gui_hooks

    def on_profile_loaded():
        from .logger import clear_log_file
        from .proxy_manager import proxy_manager
        from .mobile_sync import auto_update_mobile_setup
        
        # Clear logs on startup if enabled
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("auto_clear_logs", True):
            clear_log_file()

        proxy_manager.start(config)
        auto_update_mobile_setup()

    gui_hooks.profile_did_open.append(on_profile_loaded)
    init_hooks()
    init_config_ui()
