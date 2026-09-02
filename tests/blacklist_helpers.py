"""Shared test helper: point the blacklist sidecar at an isolated temp file.

The blacklist (FAILED_COMBOS_CACHE / RATE_LIMIT_STREAK) is persisted to
`blacklist.json`. Inside Anki this lives in the profile data dir; outside Anki
(and in isolated unit tests) the code falls back to the addon folder via
``_blacklist_path()``, which can pollute the live on-disk file and cause
order-dependent test failures (a combo blacklisted by an earlier test is
re-loaded by a later one).

Each test class that exercises provider calls / ``_mark_combo_failed`` should
call ``isolate_blacklist(self)`` in ``setUp`` (or add it as an ``addCleanup``)
so every test reads/writes a throwaway temp file and never the real one.
"""

import os
import shutil
import tempfile

from addon import ai_client as ai

# Process-wide safety net: redirect every mutable state file (blacklist, logs,
# caches) to a dedicated test folder, never the live addon/profile data dir.
# `addon_data_dir()` in config_io.py reads this at call time, so it survives the
# aggressive `addon.*` module re-imports some test files perform.
_AIHINTS_DATA_DIR = os.environ.get(
    "AIHINTS_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".aihints_data"),
)
os.environ["AIHINTS_DATA_DIR"] = _AIHINTS_DATA_DIR
os.makedirs(_AIHINTS_DATA_DIR, exist_ok=True)


def isolate_blacklist(testcase):
    """Redirect the blacklist sidecar to a per-test temp file.

    Must be called from setUp so the override is in place before any provider
    call or cooldown mutation. The caller's tearDown restores the original
    path and removes the temp dir via addCleanup registration.
    """
    tmpdir = tempfile.mkdtemp(prefix="aihints-bl-")
    original_path = ai.BLACKLIST_FILE
    ai.BLACKLIST_FILE = os.path.join(tmpdir, "blacklist.json")
    ai._blacklist_path_resolved = True
    ai._BLACKLIST_LOADED = False

    def _restore():
        ai.BLACKLIST_FILE = original_path
        ai._blacklist_path_resolved = False
        shutil.rmtree(tmpdir, ignore_errors=True)

    testcase.addCleanup(_restore)
