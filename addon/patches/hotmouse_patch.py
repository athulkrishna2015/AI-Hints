# -*- coding: utf-8 -*-
"""Best-effort bridge to the Review Hotmouse addon.

While the Alt+click "Generate with a specific model" popup is open, mouse-wheel
events must scroll the popup instead of triggering Hotmouse actions (next card,
overview, etc.). Hotmouse intercepts wheels at the Qt event-filter level, so a
JS-side preventDefault is not enough — we toggle its own suspend/resume API.

The manager is located by scanning sys.modules (same convention as
anki_terminator_patch) without hardcoding the addon's folder name; if Hotmouse
is not installed every function here is a silent no-op.
"""

SUSPEND_REASON = "ai-hints-model-picker"


def _find_manager():
    import sys

    for name, module in list(sys.modules.items()):
        if not name or "hotmouse" not in name.lower():
            continue
        manager = getattr(module, "manager", None)
        if (
            manager is not None
            and callable(getattr(manager, "suspend", None))
            and callable(getattr(manager, "resume", None))
        ):
            return manager
    return None


def suspend_hotmouse():
    """Pause Hotmouse wheel/click handling while a modal AI-Hints popup is open."""
    try:
        manager = _find_manager()
        if manager:
            manager.suspend(SUSPEND_REASON)
    except Exception:
        pass


def resume_hotmouse():
    """Restore Hotmouse handling after an AI-Hints popup closes."""
    try:
        manager = _find_manager()
        if manager:
            manager.resume(SUSPEND_REASON)
    except Exception:
        pass
