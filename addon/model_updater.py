"""Automatic model-list refresh for AI-Hints.

Fetches the available models for every configured provider and prunes entries
that the provider no longer returns (or flagged as deprecated) from both the
per-provider fallback lists and the global fallback priority list.

Runs entirely in a background thread and never blocks the UI or interrupts
an in-progress generation/batch.  Throttled by ``last_model_update`` so it
only happens once per day by default.  All Anki-collection / addonManager
writes are marshalled to the main thread.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Set

try:
    from .logger import logger
except Exception:
    import logging
    logger = logging.getLogger("AI-Hints")

try:
    from .ai_client import AIClient, FETCHED_DEPRECATED_MODELS
except Exception:
    AIClient = None
    FETCHED_DEPRECATED_MODELS = {}

try:
    from .config_io import read_meta_config, write_pretty_config_preserve_keys
except Exception:
    read_meta_config = None
    write_pretty_config_preserve_keys = None

# Guard against overlapping runs (startup + manual "Update Now" racing).
_RUN_LOCK = threading.Lock()
_RUNNING = {"flag": False}


def _addon_package():
    try:
        from aqt import mw
        if mw is not None and getattr(mw, "addonManager", None) is not None:
            return mw.addonManager.addonFromModule(__name__.split(".")[0]) or __name__.split(".")[0]
    except Exception:
        pass
    return __name__.split(".")[0]


def _providers_to_update(config: Dict[str, Any]) -> List[str]:
    providers: Set[str] = set()
    fb = config.get("model_fallbacks") or {}
    if isinstance(fb, dict):
        providers.update(fb.keys())
    cp = config.get("custom_providers") or {}
    if isinstance(cp, dict):
        providers.update(cp.keys())
    lp = config.get("local_providers") or {}
    if isinstance(lp, dict):
        providers.update(lp.keys())
    if config.get("local_endpoint"):
        providers.add("local")
    try:
        client = AIClient(config)
        for p in ("anthropic", "openai", "deepseek", "grok", "gemini",
                  "openrouter", "huggingface", "groq", "sambanova", "nvidia",
                  "mistral", "cerebras"):
            try:
                if client._available_api_keys(p):
                    providers.add(p)
            except Exception:
                pass
    except Exception:
        pass
    return sorted(providers)


def _tooltip_on_main(msg: str):
    """Show a tooltip from any thread without blocking."""
    try:
        from aqt import mw
        if mw is None:
            return
        def _show():
            try:
                from aqt.utils import tooltip
                tooltip(msg)
            except Exception:
                pass
        mw.taskman.run_on_main(_show)
    except Exception:
        pass


def run_auto_update(silent: bool = False) -> Dict[str, Any]:
    """Fetch + prune. Returns a summary dict. Safe to call from any thread.

    ``silent`` suppresses the user-facing tooltip (used by the throttled
    startup run so it never interrupts the user).
    """
    summary = {"changed": False, "removed": 0, "providers": 0, "errors": []}
    if read_meta_config is None or write_pretty_config_preserve_keys is None or AIClient is None:
        return summary
    # Never run (and never hit the network) outside of a live Anki session.
    try:
        from aqt import mw
        if mw is None or getattr(mw, "col", None) is None:
            return summary
    except Exception:
        return summary

    with _RUN_LOCK:
        if _RUNNING["flag"]:
            logger.debug("AI-Hints model updater: already running, skipping.")
            return summary
        _RUNNING["flag"] = True

    try:
        try:
            config = read_meta_config() or {}
        except Exception as e:
            logger.error(f"AI-Hints model updater: could not read config: {e}")
            return summary
        if not config.get("auto_update_models", True):
            return summary

        try:
            client = AIClient(config)
        except Exception as e:
            logger.error(f"AI-Hints model updater: could not build client: {e}")
            return summary

        providers = _providers_to_update(config)
        changed = False
        removed_total = 0
        for provider in providers:
            try:
                fetched = client.fetch_models(provider)
            except Exception as e:
                logger.warning(f"AI-Hints model updater: fetch failed for {provider}: {e}")
                summary["errors"].append(f"{provider}: {e}")
                continue
            if not fetched:
                continue
            keep = set(fetched)
            deprecated = FETCHED_DEPRECATED_MODELS.get(provider, set()) or set()
            keep = keep - set(deprecated)

            # Per-provider fallbacks
            fb = config.get("model_fallbacks")
            if not isinstance(fb, dict):
                fb = {}
            if provider in fb and isinstance(fb[provider], list):
                before = list(fb[provider])
                new_list = [m for m in before if m in keep]
                if new_list != before:
                    fb[provider] = new_list
                    config["model_fallbacks"] = fb
                    changed = True
                    removed_total += len(before) - len(new_list)

            # Per-provider disabled fallbacks
            dfb = config.get("disabled_fallback_models")
            if not isinstance(dfb, dict):
                dfb = {}
            if provider in dfb and isinstance(dfb[provider], list):
                before = list(dfb[provider])
                new_list = [m for m in before if m in keep]
                if new_list != before:
                    dfb[provider] = new_list
                    config["disabled_fallback_models"] = dfb
                    changed = True

            # Global fallback priority (list of [provider, model] pairs)
            for key in ("global_model_priority", "disabled_global_model_priority"):
                gl = config.get(key)
                if isinstance(gl, list):
                    before = list(gl)
                    new_list = [
                        entry for entry in before
                        if not (isinstance(entry, (list, tuple)) and len(entry) >= 2
                                and entry[0] == provider and entry[1] not in keep)
                    ]
                    if new_list != before:
                        config[key] = new_list
                        changed = True
                        removed_total += len(before) - len(new_list)

            summary["providers"] += 1

        config["last_model_update"] = time.time()

        # Marshal the write to the main thread so addonManager is never
        # touched from a worker thread.
        write_done = threading.Event()
        write_ok = {"ok": False}

        def _save():
            try:
                # write_pretty_config_preserve_keys swallows exceptions
                # internally, so verify success by re-reading the persisted
                # last_model_update timestamp afterwards.
                write_pretty_config_preserve_keys(_addon_package(), config)
                persisted = read_meta_config() or {}
                if persisted.get("last_model_update") == config.get("last_model_update"):
                    write_ok["ok"] = True
                else:
                    logger.error("AI-Hints model updater: save did not persist (last_model_update missing).")
                    summary["errors"].append("save: did not persist")
            except Exception as e:
                logger.error(f"AI-Hints model updater: failed to save config: {e}")
                summary["errors"].append(f"save: {e}")
            finally:
                write_done.set()

        try:
            from aqt import mw
            if mw is not None and getattr(mw, "taskman", None) is not None:
                mw.taskman.run_on_main(_save)
                write_done.wait(timeout=30)
            else:
                _save()
        except Exception as e:
            logger.error(f"AI-Hints model updater: could not schedule save: {e}")
            summary["errors"].append(f"schedule-save: {e}")

        summary["changed"] = changed and write_ok["ok"]
        summary["removed"] = removed_total if write_ok["ok"] else 0
        if changed and write_ok["ok"]:
            logger.info(f"AI-Hints: auto-updated model lists; pruned {removed_total} deprecated/removed entr{'y' if removed_total == 1 else 'ies'}.")
            if not silent:
                _tooltip_on_main(f"Model lists updated. Pruned {removed_total} deprecated/removed entr{'y' if removed_total == 1 else 'ies'}.")
        elif not changed:
            logger.debug("AI-Hints: auto model update ran; nothing to prune.")
    except Exception as e:
        logger.error(f"AI-Hints model updater: unexpected error: {e}")
        summary["errors"].append(f"unexpected: {e}")
    finally:
        with _RUN_LOCK:
            _RUNNING["flag"] = False
    return summary


def maybe_auto_update():
    """Throttled trigger. Safe to call from the main thread at startup."""
    try:
        from aqt import mw
        if mw is None or getattr(mw, "col", None) is None:
            return
    except Exception:
        return
    try:
        config = read_meta_config() or {}
    except Exception:
        return
    if not config.get("auto_update_models", True):
        return
    last = config.get("last_model_update", 0) or 0
    interval = 24 * 3600
    if time.time() - last < interval:
        logger.debug("AI-Hints model updater: last update recent, skipping.")
        return
    threading.Thread(target=run_auto_update, kwargs={"silent": True}, daemon=True,
                     name="ai-hints-model-updater").start()
    logger.info("AI-Hints: scheduled background model-list update.")
