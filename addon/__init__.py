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
        from .mobile_sync import auto_update_mobile_setup, sync_mobile_script
        from aqt.qt import QTimer
        import os
        
        # Clear logs on startup if enabled
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        if config.get("auto_clear_logs", True):
            clear_log_file()

        # Dynamically set log level based on user config
        from .logger import logger
        import logging
        if config.get("debug_logging", False):
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        # Migrate batch_state.json to profile folder
        try:
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            profile_dir = mw.pm.profileFolder()
            if profile_dir:
                # 1. Batch state migration
                addon_batch_state = os.path.join(addon_dir, "batch_state.json")
                root_batch_state = os.path.join(profile_dir, "ai_hints_batch_state.json")
                dest_bin_dir = os.path.join(profile_dir, "ai_hints_bin")
                os.makedirs(dest_bin_dir, exist_ok=True)
                dest = os.path.join(dest_bin_dir, "ai_hints_batch_state.json")
                
                if os.path.exists(addon_batch_state):
                    if not os.path.exists(dest):
                        import shutil
                        shutil.move(addon_batch_state, dest)
                        logger.info("AI-Hints: Migrated batch_state.json to profile bin folder.")
                    else:
                        os.remove(addon_batch_state)
                
                if os.path.exists(root_batch_state):
                    if not os.path.exists(dest):
                        import shutil
                        shutil.move(root_batch_state, dest)
                        logger.info("AI-Hints: Migrated root profile batch state to profile bin folder.")
                    else:
                        os.remove(root_batch_state)
        except Exception as e:
            logger.error(f"AI-Hints: Failed to migrate batch_state: {e}")

        # Delay startup tasks to avoid resource contention and potential crashes.
        # This also ensures we don't interfere with Anki's initial startup sync.
        def _delayed_startup():
            if not mw or not mw.col:
                return
            auto_update_mobile_setup()
            
            # Reload batch state once profile folder is fully available, then
            # re-evaluate whether an interrupted queue should auto-resume.
            try:
                from .batch_manager import initialize_batch_manager
                initialize_batch_manager()
            except Exception as e:
                logger.error(f"AI-Hints: Failed to reload batch state on startup: {e}")
            
        QTimer.singleShot(2000, _delayed_startup)

    def on_profile_will_close():
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

    # Enable Anki Terminator addon support
    try:
        from .anki_terminator_patch import setup_anki_terminator_patch
        setup_anki_terminator_patch()
    except Exception:
        pass

    # Enable PiperTTS addon support
    try:
        from .tts_addon_patch import setup_tts_addon_patch
        setup_tts_addon_patch()
    except Exception:
        pass
