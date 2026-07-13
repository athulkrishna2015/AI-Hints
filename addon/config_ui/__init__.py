def init_config_ui():
    from .main_dialog import init_config_ui as actual_init
    return actual_init()

def on_config_dialog(mw):
    from .main_dialog import on_config_dialog as actual_on_config
    return actual_on_config(mw)

def ConfigDialog(*args, **kwargs):
    from .main_dialog import ConfigDialog as ActualConfigDialog
    return ActualConfigDialog(*args, **kwargs)

from .widgets import ADDON_PACKAGE

__all__ = ["ConfigDialog", "init_config_ui", "on_config_dialog", "ADDON_PACKAGE"]
