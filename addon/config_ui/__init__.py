def check_support_on_update():
    from .main_dialog import check_support_on_update as actual_check
    return actual_check()

def _close_config_dialog_on_shutdown():
    from .main_dialog import _close_config_dialog_on_shutdown as actual_close
    return actual_close()

def on_clean_orphaned_hints():
    from .main_dialog import on_clean_orphaned_hints as actual_clean
    return actual_clean()

def init_config_ui():
    from aqt import mw, gui_hooks
    gui_hooks.profile_will_close.append(_close_config_dialog_on_shutdown)
    gui_hooks.profile_did_open.append(check_support_on_update)
    
    mw.addonManager.setConfigAction(ADDON_PACKAGE, on_config_dialog)

    from aqt.qt import QAction
    orphan_action = QAction("Clean Orphaned Hints", mw)
    orphan_action.triggered.connect(on_clean_orphaned_hints)
    
    inserted = False
    try:
        tools_menu = mw.form.menuTools
        for action in tools_menu.actions():
            if action.text().replace("&", "") == "Empty Cards...":
                actions = tools_menu.actions()
                idx = actions.index(action)
                if idx + 1 < len(actions):
                    tools_menu.insertAction(actions[idx+1], orphan_action)
                else:
                    tools_menu.addAction(orphan_action)
                inserted = True
                break
    except Exception as e:
        from .main_dialog import logger
        logger.error(f"AI-Hints: Failed to insert menu item at specific location: {e}")

    if not inserted:
        mw.form.menuTools.addAction(orphan_action)

    action = mw.form.menuTools.addAction("AI-Hints Config")
    action.triggered.connect(lambda: on_config_dialog(mw))

def on_config_dialog(*args, **kwargs):
    from .main_dialog import on_config_dialog as actual_on_config
    return actual_on_config(*args, **kwargs)

def ConfigDialog(*args, **kwargs):
    from .main_dialog import ConfigDialog as ActualConfigDialog
    return ActualConfigDialog(*args, **kwargs)

ADDON_PACKAGE = __name__.split(".")[0]

__all__ = ["ConfigDialog", "init_config_ui", "on_config_dialog", "ADDON_PACKAGE"]
