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
        from .mobile_sync import auto_update_mobile_setup, sync_mobile_script
        from aqt.qt import QTimer
        
        # Clear logs on startup if enabled
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("auto_clear_logs", True):
            clear_log_file()

        # 1. Sync script immediately as it is fast and fixes potential ghosting/rendering issues
        # only if it has changed from the version in the addon folder.
        sync_mobile_script()

        # 2. Delay heavy startup tasks to avoid resource contention and potential crashes
        def _delayed_startup():
            if not mw or not mw.col:
                return
            proxy_manager.start(config)
            auto_update_mobile_setup()
            
        QTimer.singleShot(2000, _delayed_startup)

    def on_profile_will_close():
        # Stop proxy manager daemon cleanly
        try:
            from .proxy_manager import proxy_manager
            proxy_manager.stop()
        except Exception:
            pass

        # Stop and release any active batch/polling timers to avoid exit-time Qt SEGV
        try:
            from .batch_manager import batch_manager
            if batch_manager.timer:
                batch_manager.timer.stop()
                batch_manager.timer = None
        except Exception:
            pass

    gui_hooks.profile_did_open.append(on_profile_loaded)
    gui_hooks.profile_will_close.append(on_profile_will_close)
    init_hooks()
    init_config_ui()
