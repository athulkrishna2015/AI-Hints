# Data Storage, Files & State

This page documents **where** AI-Hints stores data, **what** files it creates, and the **variables/values** it keeps across sessions.

## Storage Locations Overview

| Location | Contents |
|----------|----------|
| `addon/config.json` | Factory default config (tracked in git; the "restore defaults" source). |
| Anki profile config (via `meta.json` / Anki add-on manager) | Your **live** configuration, including user data like blacklist state and scan cursors. |
| Anki profile `ai_hints_bin/pregen_cache.json` | Pre-generated hint cache (disk-backed; legacy fallback: `addon/pregen_cache.json`). |
| Anki profile `ai_hints_bin/ai_hints_batch_state.json` | Persistent batch queue state (fallback: `addon/batch_state.json`). |
| Anki profile `ai_hints_bin/ai_hints.log`, `.1`, `.2`, `.3` | Rotating log files (current session plus three backups, 5 MB each); resolved via `logger._log_path()`. |
| `addon/meta.json.bak`, `.bak.1`, `.bak.2` | Startup copies of the previous addon metadata file, rotated once when an Anki profile opens. |
| In-note hidden JSON block | Per-card generated data (see [Data & Storage Format](data-format.md)). |
| `addon/manifest.json`, `addon/VERSION` | Package metadata and version string. |
| `_ai_hints_template.js` (media folder) | Mobile/synced frontend template script. |

---

## 1. `config.json` (Factory Defaults)

`addon/config.json` is **tracked in git** and ships with the add-on. It is the source of factory defaults (used by **Restore Defaults**) and is never modified at runtime.

Every key in this file (with its default value and purpose) is documented in the [Configuration Reference (all keys)](config-reference.md).

Key structure highlights:

```json
{
  "ai_provider": "gemini",
  "api_keys": { "openai": "", "anthropic": "", "gemini": "", "...": "" },
  "models": { "openai": "gpt-4o", "gemini": "gemini-flash-latest", "...": "" },
  "model_fallbacks": { "anthropic": ["claude-3-7-sonnet-latest", "..."], "...": [] },
  "provider_priority": ["anthropic", "openai", "deepseek", "grok", "gemini", "openrouter", "huggingface", "groq", "sambanova", "nvidia", "mistral", "cerebras"],
  "options_count": 4,
  "config_version": 3,
  "auto_show_hints": true,
  "...": ""
}
```

## 2. Live Configuration (`meta.json` / Anki Config)

Your **actual** settings are stored by Anki's add-on manager (persisted to your profile's `meta.json`). The add-on reads/writes it through `mw.addonManager.getConfig()` / `writeConfig()` (via `addon/config_io.py`).

In addition to the config keys, this live store also holds **runtime/user state** that is not in the factory defaults:

| Key | Type | Purpose |
|-----|------|---------|
| `model_blacklist_data` | object | Persisted blacklist/cooldown state (see below). |
| `deck_last_scan_nid` | object | Per-deck incremental batch-scan cursors: `{ "Deck::Sub": <maxNoteId> }`. |
| `last_orphans_check_time` | int | Timestamp cursor for the orphaned-hints scan. |
| `mobile_setup_completed` | bool | Whether mobile templates were installed. |
| `last_active_tab` | int | Last selected config tab, restored on reopen. |
| `supporter_opt_out` | bool | Hide the Support tab auto-open (stored in addon meta). |
| `local_providers` | object | Legacy local-endpoint provider configs. |
| `provider_timeouts` | object | Per-provider timeout overrides: `{ provider: seconds }`. |
| `provider_overrides` | object | Per-provider routing overrides. |
| `disabled_global_model_priority` | array | Check state for the Advanced Global Fallback dialog. Separate from `disabled_fallback_models`. |
| `test_question_front` / `test_question_back` | string | The model-testing prompt. |
| `global_model_priority` | array | The global cross-provider fallback list. |
| `use_global_model_priority` | bool | Whether the global list is active. |
| `pre_generate_count` | int | Pre-generation buffer size. |

### `model_blacklist_data` Structure

Persisted by `ai_client._save_blacklist()` with **version 3**:

```json
{
  "combos_expiries": { "provider|model|key": <unix_expiry_ts> },
  "streaks": { "provider|model|key": <failure_streak_count> },
  "version": 3
}
```

- Keys use the `provider|model|key` composite string.
- `combos_expiries` holds the timestamp when a failed combo's cooldown ends.
- `streaks` holds consecutive failure counts (used for blacklisting/sorting).

## 3. `pregen_cache.json` (Pre-Generation Cache)

- **Path**: `<profile>/ai_hints_bin/pregen_cache.json` (resolved by `resolve_data_file()`; survives addon updates).
- **Class**: `PregenCache` (a `UserDict`) in `addon/reviewer_hooks.py`.
- **Purpose**: Persist background pre-generated hint data across sessions so pre-generated cards survive restarts and Undo.
- **Structure**: JSON object mapping card keys to their pre-generated payloads.
- **Writes on every set/delete** (auto-save).
- **Cleared** by the **🧹 Clear Pregen Cache** maintenance tool.

## 4. Batch Queue State (`ai_hints_batch_state.json`)

- **Primary path**: `<profile>/ai_hints_bin/ai_hints_batch_state.json` (created lazily).
- **Fallback path**: `addon/batch_state.json` (used when no profile is available, e.g. tests).
- **Class**: written by `batch_manager.py` (`_state_file_path`, `load_state`, `save_state`).
- **Purpose**: Persist the batch generation queue so interrupted runs resume after Anki restarts.

Structure (new nested format):

```json
{
  "native_jobs": { "<job_id>": { "...": "cloud/native batch job" } },
  "local_cache": {
    "active": true,
    "paused": false,
    "last_run_stats": { "...": "..." },
    "jobs": [ { "id": "...", "queue": [ ... ] } ]
  }
}
```

- Backward-compatible: legacy plain `jobs` dicts and old `queue` fields are reconstructed on load.
- **Migrated** on startup from the old location to the profile folder (see `addon/__init__.py`).

## 5. Log Files (`ai_hints.log`)

- **Path**: `<profile>/ai_hints_bin/ai_hints.log` — the single canonical location shared by the file handler (`rebind_file_logging()`), the Logs tab and Clear Log.
- **Handler**: `RotatingFileHandler`, `maxBytes=5*1024*1024`, `backupCount=3`.
- **Rotation**: 4 files total — `ai_hints.log`, `ai_hints.log.1`, `ai_hints.log.2`, `ai_hints.log.3`. A rollover happens when the profile opens so each session starts with a fresh log and three prior sessions are preserved.
- **Clear on startup**: with `auto_clear_logs` enabled (the default) only the current `ai_hints.log` is deleted on startup; the rotated backups remain available.
- **Format**: `%(asctime)s - %(levelname)s - %(message)s`.
- **Viewable** live in the **Logs** tab, which offers **Level** (DEBUG/INFO/WARNING/ERROR) and **Source** filters (Antigravity Proxy, Batch Processing, Pre-generation, Model Testing, **Lingering** — the `AI-Hints Linger: ...` background-timeout lines — and Standard Addon) plus free-text search; configurable via **Clear on startup** and **Debug logging**.

## 6. In-Note JSON Block

Generated hints/options are stored in a hidden `<div class="ai-hints-json">` block inside each note. This is the core per-card data. See [Data & Storage Format](data-format.md) for the full payload fields (`hints`, `options`, `correct_answer`, `_src`, `_provider`, `_model`, `_generated_at`, `_generation_type`).

## 7. Package Metadata

| File | Contents |
|------|----------|
| `addon/manifest.json` | `name`, `package`, `version`, `human_version`. |
| `addon/VERSION` | Plain version string (e.g. `6.1.0`), read at import for auto-regeneration version checks. |

## 8. Mobile Template Script

- **File**: `_ai_hints_template.js` in your Anki media folder.
- **Source**: `addon/web/template.js`.
- **Purpose**: The lightweight JavaScript renderer used by AnkiDroid, AnkiMobile, and AnkiWeb (Zero-Addon architecture).
- Installed/removed by the **Mobile Support** tab and synced to AnkiWeb.

---

## Related Documentation

- [Configuration Reference (all keys)](config-reference.md)
- [Data & Storage Format](data-format.md)
- [Features](features.md)
