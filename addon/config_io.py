import json
import os
import shutil
import threading

try:
    from .logger import logger
except Exception:
    import logging

    logger = logging.getLogger("AI-Hints")

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


def _meta_path():
    return os.path.join(_ADDON_DIR, "meta.json")


def _rotate_meta_backups():
    """Rotate meta.json backups to keep 3 levels: .bak, .bak.1, .bak.2.

    Newest backup is always .bak, oldest is .bak.2. Called before creating
    a new .bak so the previous 3 are preserved.
    """
    base = _meta_path()
    bak = base + ".bak"
    bak1 = base + ".bak.1"
    bak2 = base + ".bak.2"
    try:
        # Remove oldest
        if os.path.exists(bak2):
            try:
                os.remove(bak2)
            except Exception:
                pass
        # Shift
        if os.path.exists(bak1):
            try:
                shutil.move(bak1, bak2)
            except Exception:
                pass
        if os.path.exists(bak):
            try:
                shutil.move(bak, bak1)
            except Exception:
                pass
    except Exception as e:
        try:
            logger.error(f"AI-Hints: failed to rotate meta backups: {e}")
        except Exception:
            pass


def addon_data_dir() -> str:
    """Directory for mutable state files (blacklist, pregen cache, logs...).

    Lives in the active PROFILE folder so it survives addon updates (files in
    the addon folder are wiped on every update). Falls back to the addon
    directory when no Anki profile is available (tests, headless import).

    Tests can redirect every state file to a throwaway directory by setting
    ``AIHINTS_DATA_DIR``; this keeps the live on-disk blacklist/caches out of
    the test run and survives module reloads (it is read at call time).
    """
    override = os.environ.get("AIHINTS_DATA_DIR")
    if override:
        d = os.path.join(override, "ai_hints_bin")
        os.makedirs(d, exist_ok=True)
        return d
    try:
        from aqt import mw
        if (
            mw is not None
            and "Mock" not in type(mw).__name__
            and getattr(mw, "pm", None) is not None
        ):
            profile_dir = mw.pm.profileFolder()
            if profile_dir:
                d = os.path.join(profile_dir, "ai_hints_bin")
                os.makedirs(d, exist_ok=True)
                return d
    except Exception:
        pass
    return _ADDON_DIR


def resolve_data_file(filename: str) -> str:
    """Return the profile-scoped path for a mutable state file.

    Migrates a legacy copy left in the addon folder (pre-profile-storage
    versions wrote there) exactly once, preserving user data across the move.
    """
    data_dir = addon_data_dir()
    new_path = os.path.join(data_dir, filename)
    old_path = os.path.join(_ADDON_DIR, filename)
    if old_path != new_path and os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            shutil.move(old_path, new_path)
            try:
                logger.info(f"AI-Hints: migrated {filename} to the profile folder ({data_dir}).")
            except Exception:
                pass
        except Exception as e:
            try:
                logger.error(f"AI-Hints: failed to migrate {filename}: {e}")
            except Exception:
                pass
            return old_path
    return new_path


def read_meta_config():
    """Read the live config dict from the addon's own meta.json on disk.

    Anki's ``addonManager.getConfig()`` silently falls back to the
    config.json defaults whenever it cannot resolve the addon package's
    meta.json (package-name mismatch, transient unreadable/corrupt file,
    etc.). Reading the file directly from the addon folder (derived from
    ``__file__``) bypasses that name-based lookup entirely, so the dialog
    and batch code always start from the actual on-disk config.
    """
    try:
        with open(_meta_path(), encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        logger.error(f"AI-Hints: read_meta_config() could not read {_meta_path()}: {e}")
        return None
    if not isinstance(meta, dict):
        logger.error(f"AI-Hints: read_meta_config() got non-dict meta from {_meta_path()}")
        return None
    config = meta.get("config")
    if not isinstance(config, dict):
        logger.error(f"AI-Hints: read_meta_config() got no 'config' dict in {_meta_path()}")
        return None
    return config


def atomic_write_json(path, data):
    """Atomically write ``data`` to ``path`` (temp file + rename).

    Used for the high-frequency sidecar files (blacklist.json, batch scan
    cursors) so a reader never observes a partial/empty file, and so these
    churning writes never touch meta.json (which holds api_keys, providers
    and the whole user config).
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json_file(path, default=None):
    """Read a JSON sidecar file, returning ``default`` if missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _orphans_state_path() -> str:
    return resolve_data_file("orphan_scan_state.json")


def get_orphans_check_time():
    """Return the last orphan-hint scan timestamp (0 if never scanned).

    Stored in its own sidecar file; on first use a legacy value left in
    meta.json is migrated over so existing state is preserved.
    """
    data = read_json_file(_orphans_state_path(), {})
    if isinstance(data, dict) and data.get("last_orphans_check_time"):
        return int(data["last_orphans_check_time"])
    try:
        legacy = (read_meta_config() or {}).get("last_orphans_check_time", 0) or 0
        if legacy:
            set_orphans_check_time(legacy)
            return int(legacy)
    except Exception:
        pass
    return 0


def set_orphans_check_time(ts):
    """Record the orphan-hint scan timestamp in orphan_scan_state.json."""
    data = read_json_file(_orphans_state_path(), {}) or {}
    if not isinstance(data, dict):
        data = {}
    data["last_orphans_check_time"] = int(ts)
    atomic_write_json(_orphans_state_path(), data)


def _log_write(addon_package, mode, on_disk, merged):
    """Emit an audit line for every meta.json write so misbehaving write paths
    can be diagnosed from ai_hints.log after the fact."""
    try:
        on_disk_keys = set(on_disk) if isinstance(on_disk, dict) else set()
        merged_keys = merged.get("api_keys") if isinstance(merged, dict) else None
        merged_decks = merged.get("deck_last_scan_nid") if isinstance(merged, dict) else None
        logger.info(
            f"AI-Hints: meta.json written [{mode}] package={addon_package} "
            f"on_disk_keys={len(on_disk_keys)} written_keys={len(merged or {})} "
            f"api_keys={len(merged_keys) if isinstance(merged_keys, dict) else 0} "
            f"scan_cursors={len(merged_decks) if isinstance(merged_decks, dict) else 0}"
        )
    except Exception:
        pass


_write_lock = threading.Lock()


def write_pretty_config(addon_package, config):
    """Write config using Anki's addon manager (full replace, default path).

    Only for paths where the incoming dict is known to be complete (e.g. the
    raw JSON editor). Never use for snapshots that might be defaults-based.
    Anki's ``addonManager.writeConfig`` is the canonical, atomic writer and
    does not truncate-and-dump the file the way a hand-rolled
    ``open(path, "w")`` writer does (that truncation race is what destroyed
    addon/meta.json on 2026-08-20).
    """
    from aqt import mw

    target = dict(config or {})
    on_disk = read_meta_config() or {}
    try:
        mw.addonManager.writeConfig(addon_package, target)
        _log_write(addon_package, "addonManager(full-replace)", on_disk, target)
    except Exception as e:
        logger.error(f"AI-Hints: write_pretty_config via addonManager failed: {e}")


def write_pretty_config_preserve_keys(addon_package, config):
    """Merge ``config`` onto the on-disk config and write it back.

    Safety properties (these are what keep a batch run from wiping the
    user's real config):

    * The on-disk config (read directly from the addon folder) is the
      baseline; an incoming key only wins when it is explicitly present, so
      a stale/defaults snapshot can no longer drop keys that already exist
      on disk.
    * ``api_keys`` keeps every on-disk key; incoming keys only replace a
      slot when they are non-empty. A snapshot built from defaults (which
      has empty api_keys) can never erase the user's keys. This is what
      stopped api_keys from being wiped when the user clicked "Reset" during
      a batch on 2026-08-20.
    * Writes are serialized with a module-level lock. The previous custom
      writer opened the file with ``"w"`` (truncating it to 0 bytes) and
      dumped JSON while other batch threads were concurrently reading the
      same file; a reader that hit the file in that window saw an empty
      file, ``read_meta_config`` fell back to ``{}``, and the next write then
      persisted a pure-defaults blob — which is exactly how addon/meta.json
      was destroyed on 2026-08-20. Anki's ``addonManager.writeConfig`` (the
      default path) does not truncate-and-dump, and the lock removes the
      read/write interleave entirely.
    * Startup rotates meta.json through 3 levels (.bak, .bak.1, .bak.2)
       before Anki or the addon can update it, so prior versions remain
       available without creating a backup on every config save.
    """
    with _write_lock:
        on_disk = read_meta_config() or {}
        incoming = dict(config or {})

        # Preserved = on-disk keys the incoming snapshot did NOT mention. A large
        # preserved set is the fingerprint of a defaults-snapshot bug.
        preserved = set(on_disk) - set(incoming)
        if preserved:
            logger.info(
                f"AI-Hints: preserve-merge keeping {len(preserved)} on-disk key(s) not "
                f"present in incoming snapshot: {sorted(preserved)[:10]}..."
            )

        merged = dict(on_disk)
        for k, v in incoming.items():
            if k == "api_keys":
                continue
            merged[k] = v

        merged_keys = {}
        on_disk_keys = on_disk.get("api_keys") or {}
        if isinstance(on_disk_keys, dict):
            merged_keys.update(on_disk_keys)
        incoming_keys = incoming.get("api_keys") or {}
        if isinstance(incoming_keys, dict):
            for p, v in incoming_keys.items():
                if v:
                    merged_keys[p] = v
        merged["api_keys"] = merged_keys

        try:
            from aqt import mw

            mw.addonManager.writeConfig(addon_package, merged)
            _log_write(addon_package, "addonManager(preserve-merge)", on_disk, merged)
        except Exception as e:
            logger.error(f"AI-Hints: preserve-merge write via addonManager failed: {e}")
