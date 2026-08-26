# Changelog

All notable changes to the AI-Hints Anki Add-on will be documented in this file.

## 7.0.1 (2026-08-26)
- **Global Fallback Priority Dialog Crash Fix**: Fixed `AttributeError: 'GlobalFallbackOrderDialog' object has no attribute '_build_remove_menu'` that crashed the Advanced Global Fallback Priority dialog on open. `_build_remove_menu` and `_build_test_menu` were `@staticmethod` methods on `FallbackOrderDialog` only — moved to module-level functions shared by both dialogs.
- **Add Custom Model to Per-Provider Fallback List**: The per-provider Fallback Priority dialog now has an **Add Model...** button that lets you type any custom model name directly into the list (useful for providers whose API doesn't support model fetching, or for manually adding models not yet fetched).
- **Local Endpoint URL for Fetch/Test**: Fixed `'ConfigDialog' object has no attribute 'local_url_edit'` crash when fetching or testing models for the `local` provider in fallback dialogs. Local endpoint configuration now reads from `local_providers_data` and `config["local_endpoint"]` instead of non-existent UI widgets.
- **Global Fetch No Longer Aborts on Single Provider Failure**: One provider failing during Fetch All (e.g. bad URL, network error) no longer kills the entire fetch loop — each provider is wrapped in its own try/except so remaining providers continue fetching.
- **Malformed Provider URL Guard**: Providers with non-HTTP URLs (e.g. missing scheme) are now silently skipped during model fetch instead of crashing with `unknown url type` errors.

## 7.0.0 (2026-08-26)
- **Undo / Redo for AI Updates (Ctrl+Alt+Z / Ctrl+Alt+Shift+Z)**: Every AI write now snapshots the previous per-card state before overwriting. In the reviewer, `Ctrl+Alt+Z` steps backward through them — first press restores the result that was replaced (e.g. the fast fallback candidate a lingering higher-priority model overwrote), the next removes the AI data entirely (original value); `Ctrl+Alt+Shift+Z` walks forward again. Scoped to the on-screen card, capped at 50 steps, and a fresh AI write clears that card's redo history.
- **Batch Generation Gets Its Own Timeout**: Batch workers inherited the short foreground `request_timeout` (e.g. 20s), killing slow-but-healthy models and burning quota on retries even though nobody watches a spinner. New `is_batch` client mode reads `batch_request_timeout` (default **120s**). Custom per-model / per-provider timeouts are now honored by **every** flow (explicit, pregen, batch) with extend-only semantics: a value greater than the flow's base budget wins; a smaller one never shortens it — so your ollama 45s cloud-model overrides also rescue slow calls in batch/pregen without ever shrinking their unattended budgets.
- **Stale Card After Mid-Review Generation Fixed**: When a background/auto generation finished while its card was on screen, the refresh relied on Anki's async card-face swap — the setup pass could race the swap and leave the visible face stale (fresh data written to disk but not rendered until the next card transition; re-entering the reviewer showed it). `_apply_results_to_card` now re-pushes the finished payload to the frontend 400 ms after the redraw via the identity-checked push (`_push_hint_data_to_frontend`), so the data lands exactly once on the right card or no-ops if the user moved on.
- **Moved-On Generations Saved Instead of Discarded**: Clicking Generate (or an auto-generation) and advancing to the next card before it finished used to throw the completed result away entirely ("Discarding to prevent bleed") — a wasted API call. The bleed-guard now only suppresses the UI update: the payload is saved silently to its own note (`update_ui=False`) and the pre-generation buffer is refilled.
- **Pregen Buffer Refills After Manual Generations**: Manual generations never triggered a buffer refill, starving pre-generation until some later auto event happened to fire (observed as "should have been already pregened" cards arriving raw). Every successful generation now triggers `_trigger_next_pregeneration()`, manual or auto.
- **Dead Antigravity Accounts Sync Removed**: The `antigravity-accounts.json` backup/restore mechanism (`_sync_accounts_file()` in `proxy_manager.py`) is gone along with its start/stop hooks, its test and `.gitignore` entries — the feature was unused (no accounts data stored, no proxy config) and a stale copy of the file (corrupted by an old test run leaking a `MagicMock` repr) was left behind in `addon/bin/`. Docs refreshed to reflect the canonical profile-scoped storage locations (`ai_hints_bin/` for logs, pregen cache).
- **Single Canonical Log File Fixed**: The file handler was bound at addon-import time — before the profile opened — so it landed on `addon/ai_hints.log` (holding only a few startup lines per session) while the Logs tab and Clear Log resolved the profile-scoped path once the profile was up: two divergent streams. The handler is now attached when the profile opens (`rebind_file_logging()`), rolling the previous session over there, so the on-disk file, Logs tab and Clear Log all operate on the exact same file; stale copies in the addon folder are no longer written and can be deleted.
- **Logs Tab No Longer Freezes Anki on Large Logs**: The Logs tab re-read the entire rotating log, filtered it several times, regex-linkified every line and rebuilt one giant HTML document **on the GUI thread every second** — freezing Anki and ballooning memory when a batch job had filled the log. Processing now streams the file in a background thread with bounded memory, renders at most the newest 4,000 matching lines (older ones collapse into a "N older matching lines hidden" notice), skips all work until the file or filters actually change, and stale results are discarded if filters change mid-scan. The header shows "matched / total lines" plus truncation info.
- **Hotmouse Suspended While Model Picker Is Open**: Opening the Alt+click "Generate with a specific model" popup now suspends the Review Hotmouse addon (via its own suspend/resume API) so the mouse wheel scrolls the provider/model lists instead of flipping cards; it resumes automatically on every close path (Generate, Cancel, ✕, Esc, backdrop click), and stale popups are wiped + Hotmouse restored on card transitions as a safety net. Silent no-op when Hotmouse is not installed.
- **Alt+Click Picker Shows Disabled, Blacklisted & All Providers**: The "Generate with a specific model" dialog now lists **all** providers (including disabled/unready ones, marked ⛔), both checked *and* unchecked fallback models (dimmed `⊘ Disabled` group), and models whose keys are all on cooldown get a 🚫 marker — everything remains selectable for explicit generation. Forcing a model whose every key-combo is cooling down now retries those combos as a last resort instead of failing silently; providers with multiple API keys already skip only the failed key and keep using healthy ones.
- **Linger-on-Timeout Fallback Racing**: When a model hits a read timeout, the request is no longer thrown away — it is re-dispatched in a background thread with an extended deadline (3x the request timeout, clamped 180–900s, `timeout_linger_seconds` to override) while fallback continues immediately with the next candidate. If the slow request finishes before later candidates, its result is used (earliest candidate wins); if every candidate fails, generation waits out the lingering attempts instead of returning empty. Pure read timeouts also no longer blacklist a model (slow ≠ broken). Disable with `linger_on_timeout: false`; disabled for single-model tests and skipped on emergency stop / network loss.
- **Linger Now Catches First-Timeouts & Highest-Priority Result Wins**: Two gaps closed in the linger system. (1) A read timeout on the *first* model of a provider was silently absorbed by the inner model-fallback loop ("try the next model") and never reached the linger hooks — so the slow-but-alive request was never re-dispatched in the background; all four inner provider loops (Gemini, OpenAI-compatible, Anthropic, custom) now spawn the lingering retry on the very first model timeout. (2) Race policy: when a lower-priority candidate succeeded while a higher-priority (earlier on the fallback list) attempt was still running, the fast-but-lower result won and the smarter one was discarded on arrival. Generation now waits out the earlier attempt's extended deadline and prefers it (`higher-priority late result ... wins over ...`), falling back to the fast result only if it yields nothing; already-finished results are claimed instantly without waiting. The wait is surfaced on the card via a distinct amber **"⏳ Waiting for higher-priority model… (Stop)"** button state (still stoppable), and the whole behavior is configurable: `linger_race_policy` — `priority` (default, as described) or `first` (first usable result wins immediately, no waiting).
- **Instant Fallback Dialog for Large Providers**: The per-provider Fallback Priority dialog created two live widgets (thinking-level combo + timeout spinbox) for every row up front, so providers with hundreds of models (e.g. OpenRouter's ~400) took seconds to open. Widgets are now materialized lazily for visible rows only (values kept in name-keyed dicts and harvested back before every read/reorder), making the dialog open instantly regardless of model count.

## 6.4.0 (2026-08-25)
- **Mobile Template Placement Fixed**: On note types without cloze-specific anchors, the mobile `AI-HINTS` block was appended to the **very end** of the back template, so AnkiDroid/AnkiMobile rendered hints/options *after* all back-side content. The block is now anchored between the front and back sections — right after `<hr id=answer>`, or after `{{FrontSide}}` when no divider exists (cloze tldraw/cloze anchoring keeps priority).
- **Media Script Sync Fixed**: One-Click Install failed with "expected bytes, _io.BytesIO found" because `col.media.write_data()` was passed a `BytesIO` wrapper while modern Anki expects raw `bytes`. Raw bytes are now written directly, with a fallback to a plain file write if the media-tracker API rejects or lacks the call.
- **Removed Obsolete Maintenance Buttons**: "📦 Migrate AI Data to First Fields" and "👻 Convert HTML to Hidden JSON" are removed from the Advanced tab (their behavior is covered by automatic on-review migration/formatting); docs updated accordingly.
- **Mobile Install During Sync Fixed**: Clicking **One-Click Install** right after **Remove from All Cards** failed with a generic "Failed to sync script file to media folder." — Remove triggers `mw.onSync()`, which closes the collection while it runs, and the installer hit the silent "no collection" path (no log, no reason). The installer/remover now wait (up to 2 minutes, with a status indicator) for the sync/profile to become available and proceed automatically; if script sync still fails, the dialog shows the actual cause and every failure path is logged.
- **Guarded JSON Parsing (GUI Freeze / Crash Fix)**: Oversized or deeply nested AI payloads could hold the GUI thread for seconds while parsing (the C-level `json` scanner holds the GIL) and abort via scanner recursion — observed crashes on 2026-08-18. All card-field and JS-bridge parse sites in `card_parser.py` / `reviewer_hooks.py` now route through `_safe_loads()`, which refuses payloads larger than 256 KB or nested deeper than 100 levels **before** parsing; small malformed payloads still raise ordinary catchable `JSONDecodeError`s.
- **Configurable Hints/Options Order**: New **"Show Options Above Hints"** toggle (General tab, `options_before_hints` config key) renders the multiple-choice options section before the hints section on the card — **enabled by default** (existing installs are migrated via `config_version` 5); uncheck it for hints first, then options. The Show Hints / Show Options toggle buttons reorder to match, and the setting is synced into mobile templates (`optionsBeforeHints` in `aiHintsMobileConfig`) so AnkiDroid/AnkiMobile honor it too.

## 6.3.4 (2026-08-23)
- **Batch Worker State Corruption Fix (Critical)**: The `local_queue_errors` setter in `batch_manager.py` contained a duplicated `__init__` block that reset `_db_lock`, diagnostics, and reloaded queue state from disk on **every failed card** — corrupting batch state and destroying mutual exclusion mid-run. The stray re-initialization is removed.
- **Anki Terminator Patch Scoped (Critical)**: The global `anki.notes.Note` fields proxy is now installed **only** when the Anki Terminator webview is actually detected. Previously it patched every user's `Note.__init__`, risking cleaned-text write-backs on field round-trips even without Anki Terminator installed.
- **Worker Threads No Longer Touch the Collection (Critical)**: Batch verification and final-stats passes now hop to the main thread via `taskman` instead of accessing the collection from worker threads.
- **429 Streak Double-Increment Fix**: Rate-limit failure streaks were incremented twice per failure (once by the delay calculation). There is now a single authoritative increment in `_mark_combo_failed`.
- **Atomic Sidecar Writes**: `pregen_cache.json` and the batch state file are now written atomically (temp file + `os.replace`), matching the meta.json corruption post-mortem pattern.
- **Multithreaded Batch Isolation**: In multithreaded batch mode each provider worker now gets its own `AIClient` instance — `_request_provider`/`_request_model` are per-request instance state and were being clobbered across threads.
- **Cooldown Parsing Hardened**: `_cooldown_seconds()` coerces string/`None` config values instead of raising inside error handling.
- **Browser Bulk Undo Checkpoints**: Browser bulk skip/unskip/clear operations now create undo checkpoints (parity with the sidebar actions).
- **Depth-Aware Hint-Block Parser**: `card_parser.py`'s non-greedy `.*?</div>` regexes are replaced with a depth-aware scanner everywhere. Legacy raw-HTML payloads no longer corrupt fields on update/clear, and unterminated blocks are skipped instead of swallowing the whole field.
- **Linearized Config Migration**: Startup migration in `addon/__init__.py` performs a single conditional config write instead of multiple overlapping ones.
- **Pregen Data Applied Before Frontend Setup**: In `on_show_question`, pre-generated data is injected before the frontend setup runs so the UI renders it on the same pass instead of one card late.
- **Interrupted Batches Restore Paused**: Interrupted batch queues are restored as **PAUSED** on startup instead of silently auto-resuming.
- **Mobile Sync Template Write Fix**: `mobile_sync` writes the template via `mw.col.media.write_data` with an undo checkpoint.
- **Proxy Manager Robustness**: A non-string `antigravity_accounts` value no longer crashes sync; `stop()` is shutdown-safe.
- **Gemini Auth via Header**: `fetch_models` sends the Gemini API key in the `x-goog-api-key` header instead of the URL query string; no-op legacy stub calls removed.
- **State Files Survive Addon Updates**: Mutable state files (`blacklist.json`, pregen cache, orphan scan state, logs, batch scan cursors) moved to a profile-level `ai_hints_bin` directory with a one-time migration from the addon folder, so they survive addon updates/deletions.
- **Misc Hardening & Fixes**: "Clear log" actually clears the log file (was a logged-only no-op); the network monitor thread starts lazily; `USER_AGENT` derives from the VERSION file; API key parsing requires matching bracket pairs; batch status summary HTML-escapes job/provider/model strings; `trigger_js_click` JSON-escapes needles into generated JS; TTS patch imports bs4 lazily; latex_fixer submodule fixes a broken Greek-name character class in the `$...$` heuristic.
- **Regression Test Suite**: New `tests/test_review_fixes.py` with 27 regression tests mapped to review findings; full suite green.

## 6.3.3 (2026-08-21)
- **Batch Worker Crash Fix (Deleted Cards)**: Fixed a `NotFoundError: No such card` crash that killed the batch worker thread when a card was deleted while a batch/pregen queue still referenced its id. `_get_card_from_collection()` now treats deleted cards as missing (all callers already skip on `None`), and the pre-generation chain skips queued cards that no longer exist instead of aborting the whole queue.
- **Accurate Unskip Confirmation Count**: The deck menu's "Unskip AI for All Cards in Deck" prompt previously showed the deck's total card count; it now counts only the cards actually marked skipped (`_skipped` flag / skip marker), shows a tooltip and bails out when the deck has no skipped cards, so the number always matches what unskip will change.
- **Live Progress Bar for Skip Counting**: Scanning a large deck before the unskip prompt now shows Anki's native progress dialog with real progress (`Counting skipped cards... x/y`) instead of a static label, throttled to 10 updates/sec.
- **Faster Skip Counting**: Sibling cloze cards sharing one note are now grouped, so each note is loaded and parsed once per scan instead of once per card — identical exact result, fewer redundant loads on cloze-heavy decks.
- **Bleed Diagnostics**: New `debug_logging`-gated `[BLEED]` (card-load block source, scope attrs, payload keys, `_src` presence) and `[BLEED-WRITE]` (target card vs reviewer card match, generation type) log lines to trace reports of data bleeding between cards.

## 6.3.2 (2026-08-20)
- **meta.json Wipe Prevention (Critical)**: Fixed a second config-loss incident (2026-08-20) where `addon/meta.json` was destroyed during a batch run. The custom pretty-JSON writer opened the file with `"w"` (truncating it to 0 bytes) and dumped JSON while batch blacklist updates ran from many concurrent worker threads; a reader hitting the file mid-truncation saw an empty file, `read_meta_config()` fell back to `{}`, and the next write persisted a pure `config.json` defaults blob — wiping api_keys, custom providers, templates and tweaks. Fixes:
  - Config writes now go through Anki's atomic `addonManager.writeConfig` (the default, non-pretty path) instead of the hand-rolled truncating file write, and are serialized with a module-level lock, so the truncate/read race can no longer happen.
  - `write_pretty_config_preserve_keys()` keeps the merge-safe baseline: the on-disk config is the baseline, incoming keys win only when explicitly present, `api_keys` always keeps on-disk values for any key the incoming snapshot leaves empty, and the previous `meta.json` is copied to `addon/meta.json.bak` before every overwrite.
- **High-Frequency Data Moved Out of meta.json**: The model cooldown/blacklist, per-deck batch scan cursors, and the orphaned-hints scan timestamp no longer live in `meta.json` (the file holding api_keys, providers and the whole user config). They now live in dedicated, atomically-written sidecar files — `blacklist.json`, `batch_scan_cursors.json`, `orphan_scan_state.json` — so a single bad write can no longer take down the entire config. Legacy values already in `meta.json` are migrated to the sidecar files on first run.
- **Delta-Only Config Writes**: All remaining save paths that built a full snapshot from `addonManager.getConfig()` (mobile install/remove, proxy antigravity-accounts sync, batch scan-cursor recording) now pass only the single changed key to the merge-safe writer, so a defaults-returning `getConfig()` can never overwrite the user's other settings.
- Batch runs no longer perform any high-frequency writes to `meta.json` — the only write during a batch is the single full-config autosave at batch start, which is built directly from the on-disk config.

## 6.3.1 (2026-08-19)
- **Config Loss Fix (Critical)**: Fixed a bug where the batch-start autosave (and other save paths) could overwrite your entire real configuration with the `config.json` defaults. When Anki's `addonManager.getConfig()` could not resolve the addon's own `meta.json` (package-name mismatch / transient unreadable file), it silently returned the default template; saving that template then destroyed custom providers, templates, tweaks and per-deck scan cursors from `addon/meta.json`. Recovery from the affected session (user config restored from the startup backup) is documented in the README. Fixes:
  - Config writes are now **merge-safe**: the on-disk config is the baseline and an incoming snapshot can never drop keys that already exist on disk (custom providers, templates, tweaks, `api_keys`, scan cursors). `api_keys` additionally keeps on-disk values for any provider the UI doesn't currently render.
  - The config dialog now builds its base directly from the on-disk `addon/meta.json` instead of Anki's name-based `getConfig()`, so it can never start from defaults while a real config exists.
  - The previous `meta.json` is copied to `addon/meta.json.bak` **before every write** (in addition to the startup backup), so a bad write can always be rolled back.
  - The orphaned-hints scan/cleanup save paths (6 more full-replace `writeConfig` calls) now go through the same merge-safe writer.
- **meta.json Write Audit Logging**: Every config write is now logged to `ai_hints.log` with the writer, package, on-disk vs written key counts, API-key count and scan-cursor count (`meta.json written [direct-file(preserve-merge)] ...`). If an incoming snapshot is missing keys the disk has, the preserved key names are logged too, so any future config-loss event is immediately diagnosable from the logs.
- **Batch Fast-Scan Cursor Fix**: A full batch scan of a deck that found nothing new to generate now still records the deck's scan cursor (previously it returned early without one), so the deck is never re-scanned in full again — subsequent runs use the incremental "only notes since last full scan" path instead of scanning the whole deck every time. Cursor reads/writes also now use the on-disk config directly and the merge-safe writer.

## 6.3.0 (2026-08-18)
- **Reliable Batch Queue Recovery**: Added a watchdog that releases a batch pass when a provider thread hangs after all queued cards have been dispatched, allowing verification to requeue unfinished cards instead of stalling indefinitely.
- **Entire Collection Batch Source**: Batch generation and regenerate-by-model now support processing the entire collection in one run, in addition to decks and browser selections.
- **Improved Batch Controls and Status Scrolling**: Queue controls are grouped above the batch logs, the batch tab uses tighter spacing, and log/status views keep the newest activity visible without losing the user's scroll position during updates.
- **Scoped Regenerate-by-Model**: Regeneration can be limited to the selected deck or browser selection instead of always scanning the whole collection.
- **API Key Preservation During Background Saves**: Model blacklist updates now preserve all saved API keys even when the background operation uses a stale or sanitized configuration snapshot.
- **Contentless Card Safety**: Empty or clozeless cards are skipped before generation state, provider checks, network calls, or card refreshes, preventing recursive auto-generation crashes.
- **Fallback Highlight Fix**: Green, amber, and red model-status highlighting now follows the model when fallback rows are moved up or down instead of remaining attached to the old row.
- **Startup Metadata Backup**: The previous `addon/meta.json` is copied to `addon/meta.json.bak` when a profile opens, before configuration migration or writes occur.

## 6.2.5 (2026-08-18)
- **Reviewer Unlimited-Recursion Crash Fix (Critical)**: Fixed a `RecursionError: maximum recursion depth exceeded` crash when auto-generating hints on a **contentless card** (e.g. a cloze card whose required deletion, like `{{c2::…}}`, is missing). The skip/refresh path re-fired `on_show_question`, which re-triggered auto-generation for the still hint-less card, looping until the interpreter gave up.
- **Empty/Clozeless Cards Are Skipped Up Front**: Contentless cards are now detected at the very start of the generation path — **before** the card enters the generating set, **before** any network/provider checks, and **before** any card refresh. As a result, an empty card no longer shows the "generating" spinner, no longer makes a pointless API/network call, and no longer triggers a redundant card redraw. The card is still tagged `ai-hints::skipped` in the database so it is not retried.

## 6.2.4 (2026-08-18)
- **API Key Wipe Fix (Critical)**: Fixed two config save paths that could silently write empty API keys over your saved keys, wiping them from `meta.json`:
  - The settings dialog **tab-switch** handler was dumping the whole in-memory config straight to disk with no key protection.
  - `save_config` was rebuilding `api_keys` from **only the visible UI key fields**, dropping keys for any provider not currently rendered as a row (e.g. GitHub, Together and custom providers like CLIProxy/OpenCode Free).
  - A new `write_pretty_config_preserve_keys()` writer now merges your on-disk keys back in before saving, so an empty/missing key field can never blank an existing key. If you already lost keys during a batch or settings save, the recovery steps (and how to restore from a previous backup) are documented in the README.
- **Multithreaded Batch On by Default**: "Concurrent Multi-Provider Generation (Multithreaded)" (`multithread_providers`) now defaults to **ON** for new installs.
- **Fallback "Restore Defaults" Crash Fix**: Fixed an `AttributeError: 'FallbackOrderDialog' object has no attribute 'list_widget'` crash when clicking **Restore Defaults** in a provider's Fallback Priority dialog (a leftover reference from the older list-based UI). Restore Defaults now correctly repopulates the model table.
- **Gitignore Coverage**: `meta.json` backup variations (`.bkp`, `meta.bkp.json`, `*.before_*`, etc.) are now ignored by git.

## 6.2.3 (2026-08-16)
- **Custom Provider Batch Failure Fix**: Fixed a `NameError: name 'parsed' is not defined` bug in the custom-provider request path (`_call_custom_provider`) that caused **every** custom-provider call (OpenCode Free, CLIProxyAPI, etc.) to fail immediately. This was a major source of batch-generation failures — cards routed to a custom provider errored out and, combined with blacklisting and read-timeouts, could exhaust all retry passes. Custom-provider responses are now correctly parsed and validated before being returned.
- **Pregen Timeout Default Alignment**: The background pre-generation timeout default in the request client is aligned with the shipped config (120s), matching the active-review 60s default.

## 6.2.2 (2026-08-16)
- **Removed the "Unsaved Changes" Warning**: Closing the AI-Hints settings dialog (via Cancel, `Esc`, or the window's X) no longer pops up a "You have unsaved changes" confirmation box. The dialog now closes immediately.

## 6.2.1 (2026-08-16)
- **Longer API Request Timeouts**: The default active-review (`request_timeout`) and pre-generation (`pregen_request_timeout`) timeouts are raised to **60s** and **120s** respectively. Slow free endpoints (e.g. teamorouter/orcarouter) can take ~26s for a real generation, so the old 10s/20s defaults caused read timeouts and forced fallback switches.
- **Config Migration to v4**: Existing installations are migrated automatically on load — `config_version` is bumped to `4` and the timeouts are forced to the new defaults (60s / 120s), overriding older saved values. New installs ship with the new defaults.
- **Custom Provider Fallback Models Fix**: Custom providers now use the models you actually **checked/enabled** in the Fallback dialog instead of the provider's saved `model` field (which was auto-set to the first fetched model). Batched generation and the model picker follow the same enabled-fallback resolution, with the saved model used only as a last resort.
- **Custom Provider Test/Fetch Fixes (Before Save)**: Testing or fetching fallback models for a newly added/edited custom provider now works correctly even before the config is saved — it routes to the provider's *actual* endpoint, uses the *saved* API key (not stale UI state), and allows fetching fallback models for brand-new custom providers.
- **Keyless Provider Auto-Derivation**: The active-provider auto-derivation previously required an API key for every provider, so keyless providers (local endpoints, URL-only custom providers) could never become primary. These are now treated as ready without a key; only built-in providers require a key.
- **Cleaner Debug Logging**: Debug logging now logs the (constant) system prompt once and the full variable request/response payloads per call, so it is easy to inspect each request's actual content without drowning in repeated boilerplate.

## 6.2.0 (2026-08-15)
- **Per-Card Model Override (Alt+Click)**: **Alt+click** the **Generate/Regenerate** button during review to open a "Generate with a specific model" dialog. Pick any provider and any of its models to force that exact model for the current card's regeneration — bypassing the automatic fallback order for that single generation.
  - **Per-provider model lists**: A Provider dropdown cascades into that provider's Model dropdown, showing **all active models** (including models currently on cooldown/blacklist, so they can be retried explicitly).
  - **Remembers your last choice**: The dialog re-opens on your previously used provider + model whenever they are still available.
  - **Theme-aware UI**: The dialog matches Anki's dark (night) and light themes automatically.
  - **No scroll pass-through**: Wheel/touch input over the dialog is blocked so it never scrolls the reviewer or triggers Hotmouse-style wheel actions underneath, and `Esc` closes it.
- **Active Provider Auto-Derivation**: Removed the **Active AI Provider** dropdown from the General tab. The primary provider is now derived automatically from the first usable entry in the fallback priority list — the first enabled provider (non-disabled) that has an API key configured, or the first custom provider. One less setting to maintain; the priority order you already configure is what decides the active provider.

## 6.1.6 (2026-08-15)
- **Config Simplification**: Removed the **Multiple-Formula Separator** and **MathJax Format** selections from the General settings. Multiple distinct formulas in a single option/correct answer are now always separated with a ` ; ` separator (enforced in the generation prompt), and generated math always uses Anki delimiters (`\( ... \)` / `\[ ... \]`). Reduces config surface; existing saved values are still honored at runtime.

## 6.1.5 (2026-08-15)
- **Multiple-Formula Option Separator**: When an option (or the correct answer) contains two or more distinct but related formulas (e.g. a general efficiency formula plus its Carnot special case), the add-on now requires them to be separated with a ` ; ` separator instead of being mashed together inline. The rule is enforced in the default system prompt (with a GOOD/BAD example) and hard-coded into the generation prompt, so the model no longer produces output like `\eta = 1 - \frac{Q_C}{Q_H}\eta = 1 - \frac{T_C}{T_H}`.

## 6.1.4 (2026-08-13)
- **AnkiDroid Swipe Gesture Fix**: Mobile AI-Hints controls no longer use native button or `onclick` targets that AnkiDroid classifies as interactive and excludes from its swipe handler. Horizontal swipe gestures now work when started over hints, options, and Show Hints, Show Options, Refresh, and JSON controls.
- **Mobile Cloze Data Isolation**: A cloze card now ignores keyed JSON data belonging to another cloze ordinal. For example, a c2 card with only c1 data is treated as having no AI data and does not show stale hints, options, JSON, or other controls.

## 6.1.3 (2026-08-13)
- **NameError Fix for Python 3.13 and Older**: Fixed a `NameError: name 'Set' is not defined` crash in `card_parser.py` that occurred when importing the addon on Python 3.13.14 and older. The uppercase type annotation `Set[int]` was replaced with standard lowercase `set[int]`. (Python 3.14 did not trigger this crash due to PEP 649/749 deferred annotation evaluation).

## 6.1.2 (2026-08-13)
- **Startup Crash Fix for Upgrading Users**: Fixed a startup crash where the configuration migration logic attempted to log info/error statements before the `logger` module was imported, which raised a `NameError` and caused the add-on to fail to load when upgrading from older settings versions.
- **Prevent Unsaved-Changes Prompt on Read-Only Widgets**: Fixed an issue where programmatic changes to read-only widgets in the Settings dialog (such as the batch status list view on the Batch tab, and the manual installation script edit box on the Mobile tab) triggered text-changed signals, incorrectly marking the dialog as dirty and prompting an "unsaved changes" warning when closing.
- **Fresh-Show JSON Panel Collapse**: Standardized review persistence to collapse the JSON panel whenever a card is shown freshly (matching hints/options auto-show defaults), preventing it from bleeding expanded state across different card reviews in the same session.

## 6.1.1 (2026-08-13)
- **Stale-Cloze Edit Notification**: If the content of a cloze deletion was changed after its AI hints/options were generated, the stored data no longer matches the immutable `_src` snapshot and is considered stale. Previously, editing such a card failed silently with an internal out-of-range error — you could enter edit mode but the save did nothing. The edit path now detects this stale state and shows a clear notification explaining that editing is disabled because the cloze content changed, and to regenerate the AI hints to update it. Generic out-of-range edit failures (e.g. a stale on-screen block) now also show a "could not save — data may be stale" tooltip instead of failing silently.

## 6.1.0 (2026-08-13)
- **Back-Side Auto-Show Control**: New dedicated **answer-side** auto-show settings in the **General** tab — **Auto-show hints on answer side** (`auto_show_hints_answer`) and **Auto-show options on answer side** (`auto_show_options_answer`), both **enabled by default**. They control whether generated hints/options are expanded automatically when the answer side of a card is shown, independently of the front-side auto-show toggles.
- **Config Migration to v3**: Config upgraded to `config_version` 3. Existing installations are migrated automatically on load; hints and options default to auto-show on both card load and the back side.
- **Relearn / Fresh-Show Reset Fix**: Previously, collapsing a hint or option box during review would leave it collapsed on the *next* card or after a relearn/retry. A fresh-show token (`review_token`) now resets every card to the configured auto-show defaults on question display, so collapsed state never bleeds between cards.
- **Mobile Auto-Show Defaults**: AnkiDroid and AnkiMobile now respect the same front- and back-side auto-show defaults (emitted via the mobile config), keeping desktop and mobile behavior consistent.
- **Generation Disabled UI**: When both **Generate Hints** and **Generate Options** are turned off, the Generate/Regenerate button and its generation animation are now disabled, clearly signalling that AI generation is off.
- **Removed "Do Not Auto-Collapse" Option**: The redundant *"Do Not Auto-Collapse on Next Card"* option (`do_not_auto_collapse`) has been removed from the General settings and template. Its behaviour is superseded by the new auto-show defaults that reset per card.
- **Config Dialog Qt Compatibility**: The Settings window is now compatible with the latest Qt/PyQt (6.11): the "Unsaved Changes" prompt uses version-agnostic button roles and `exec()`/`exec_()`, fixing an `AttributeError` crash when closing with unsaved changes on newer Anki builds.
- **Save & Close Restored**: The config dialog bottom bar now shows **Save** (stays open), **Save & Close** (saves, syncs mobile, and closes), and **Cancel** (with unsaved-changes warning). The intermediate "Save & Sync" button was removed.

## 6.0.0 (2026-08-12)
- **Skipped-Card Reviewer Rendering**: Skipped cards now render their `AI generation skipped.` message reliably. Desktop shows all buttons (Generate/Regenerate, Clear, Refresh, JSON) alongside the message, while mobile (AnkiDroid/AnkiMobile) shows only the skipped message with no buttons. Previously the message could sit inside a hidden box (blank card) and new cards could drop their buttons after a null-data guard regression — both fixed.
- **Generation Master Switch (Hints / Options)**: Added two independent master toggles in the **General** settings — **Generate Hints** and **Generate Options (MCQ)**, both **enabled by default**. They control *every* generation path (manual, auto, pre-generation, and batch):
  - Unchecking **Generate Hints** stops hint generation only (options still produced).
  - Unchecking **Generate Options** stops MCQ/option generation only (hints still produced). The prompt is adjusted so the LLM only returns what is enabled.
  - Turning **both** off effectively disables the addon — no API calls are made anywhere (manual/auto/pregen/batch) until you re-enable a toggle.
  - Provider **Test** buttons in Settings still work while generation is disabled, so you can verify connectivity before re-enabling.

## 5.8.6 (2026-08-12)
- **Snapshot-Based Stale Cloze Detection Fix**: v5.8.5's stale-hint check compared the stored `correct_answer`/`options` against the cloze text, so **manually edited** hints/options were often mistaken for stale data and wiped. Stale detection now snapshots the actual cloze answer (`_src`) inside the hidden JSON block at generation/save time, then compares the *current* cloze text against that immutable snapshot — never against your (possibly edited) `correct_answer`/`options`. Manually edited hints and options are therefore preserved, while a genuinely changed/repurposed cloze is still caught and regenerated. Existing cards saved before `_src` existed are treated as valid (never content-invalidated), so legacy manual edits are safe.

## 5.8.5 (2026-08-12)
- **Orphaned Cloze Key Purge**: Stale hint/option data for cloze deletions that no longer exist on a note is now automatically purged. When saving or updating hints, any keyed `cN` entry whose corresponding `{{cN::...}}` tag is missing from the note's text is removed from the hidden JSON block, preventing ghost data and stale cards.
- **Stale/Mismatched Hint Invalidation**: Cloze data whose saved `correct_answer`/`options` no longer match the actual text of the active cloze deletion is now rejected as stale on both the Python side (`find_hints_block`) and in the reviewer pre-generation cache (`_cached_hints_for_card`). If a cloze's answer was edited (e.g. copy-pasted or changed), the old hints/options are treated as invalid and regenerated instead of showing inaccurate data.

## 5.8.4 (2026-08-11)
- **AnkiWeb Multi-Cloze Detection Fix**: On AnkiWeb (ankiuser.net/study) every cloze card showed only the `c1` hints/options. AnkiWeb places the cloze number on the card container (`<div id="qa_box" class="card card2">`) instead of on `<body>`, so the mobile cloze detection never found it and always fell back to `c1`. `getCardOrd()` now also reads the `cardN` class from `#qa_box`, so c2/c3 cards render their own hints and options correctly on AnkiWeb.

## 5.8.3 (2026-08-11)
- **AnkiWeb (ankiuser.net/study) Option Reveal Fix**: Tapping a generated MCQ option on the AnkiWeb reviewer used to only save your selection — the card never flipped because AnkiWeb exposes no JavaScript reveal API (`pycmd` / `showAnswer()` do not exist there). The reveal now falls back to simulating a click on the reviewer's own **Show Answer** button (`#ansarea .btn.btn-primary.btn-lg`), so options flip the card and the correct/incorrect highlight renders on the back side exactly like on Desktop and the mobile apps.

## 5.8.2 (2026-08-11)
- **AnkiMobile "undefined" Tap Fix**: On AnkiMobile (iOS), tapping a generated MCQ option used to blank the card and show the literal text `undefined` at the top instead of flipping to the answer side. AnkiMobile has no JavaScript API for showing the answer, so the old `pycmd('ans')`/`showAnswer()` reveal call made the WebView navigate to a blank `undefined` page. The add-on now detects the AnkiMobile WebView bridge (`webkit.messageHandlers.cb`) and skips the JS reveal there — the option tap only saves your selection and the platform's native tap-to-reveal flips the card, so the correct/incorrect highlight still renders on the back side. Desktop and AnkiDroid are unaffected and keep their `pycmd('ans')`/`showAnswer()` reveal. Documented in the README's **Mobile Setup & Troubleshooting** section, including the requirement to keep a review tap zone set to "Show Answer".

## 5.8.1 (2026-08-09)
- **Together AI Provider Removed**: The Together provider has been fully removed from the provider list, default models, suggestions, fallbacks, legacy replacements, chat routing, and config. Together's API key authentication was often misconfigured (returning `HTTP 401 Unauthorized`), and the endpoint is better served through a Custom Provider for users who need it.
- **Token Usage Logging**: Every successful provider completion now logs its token usage (`prompt_tokens`/`completion_tokens`/`total_tokens`, or Anthropic-style `input_tokens`/`output_tokens`) to `ai_hints.log` (visible in the Logs tab), so you can monitor per-call API usage without querying the provider dashboard.
- **Custom Provider Improvements**: Custom (OpenAI-compatible) providers now work more reliably in the dialogs — the Fallback Priority dialog's **Fetch All** includes custom providers (not just built-ins), the Add Model dialog reads each custom provider's own `model`/`model_fallbacks` so they stay in sync with runtime routing, custom providers are auto-assigned default models on fetch/ready check, and the system prompt is omitted from the request log for privacy. **Fetch/Save URL**, **Test** and **Fetch Default Models** now also recognize custom providers.

## 5.8.0 (2026-08-08)
- **Deprecated / New / Missing Model Highlighting**: After a model fetch, fallback lists now flag models visually — 🆕 newly fetched models (green), ⚠️ Deprecated models (red), and ⚠️ No Longer Returned models (amber, i.e. present before the fetch but missing from the latest API response). Deprecation is detected live from each provider's own API (OpenRouter `deprecation`, Gemini models that no longer expose `generateContent`, and generic `expires_at`/`deprecated` flags on custom/GitHub-style endpoints) plus legacy replacement mappings and name heuristics. No hardcoded model lists.
- **Unified Remove Dropdown**: The fallback dialogs now have a single **Remove** button with a choose-type menu: *Remove Selected*, *Remove Deprecated*, *Remove No Longer Returned*, or *Remove Deprecated & No Longer Returned* together.
- **Unified Test Dropdown**: The per-provider and global fallback dialogs now have a single **Test** button with a dropdown: *Test Checked*, *Test Row*, or *Test All* (replacing the previous separate button cluster).
- **GitHub Models Provider Removed**: GitHub Models was fully retired by GitHub on 2026-07-30 (`models.github.ai` now returns 410 Gone). The GitHub provider has been removed from the provider list, default models, suggestions, fallbacks, and config.
- **Faster Large Fallback Lists**: Fallback dialogs with hundreds of models (e.g. OpenRouter's ~400 models) now open much faster — rows are bulk-populated with layout/repaint updates frozen instead of a relayout per row.
- **Crash Fix**: Fixed a `TypeError`/`AttributeError` in the Fallback dialog (`QTableWidget` has no `setCurrentRow`; moved to `setCurrentCell`), which crashed when setting the active model or reordering rows.

## 5.7.1 (2026-08-08)
- **Incremental Per-Deck Batch Fast Scan**: Batch generation now skips notes created before this deck's last FULL batch scan by default. The cursor is tracked independently **per deck** (including all sub-decks) in `deck_last_scan_nid`, so scanning a sub-deck never wrongly skips its older cards based on another deck's timestamp. The cursor only advances after a full, eligible pass (no cards dropped to the safety limit, and not a browser-card selection).
- **Valid Search Syntax Fix**: Fixed the batch fast-scan filter, which used the unsupported `nid:>` search operator. Anki 26.x rejects `nid:>` / `nid:1-5` with `"expected only digits and commas in nid:"` (causing an error every run and a full-deck fallback scan). New note ids are now resolved in Python and queried via the valid comma-list form (`deck:"..." nid:111,222`).
- **Force FULL Scan Checkbox**: Added a **"🧹 Force FULL scan (ignore last-scan cursor)"** checkbox to the Batch tab to re-check every card in the deck, bypassing the incremental cursor.
- **Hint Tagging On by Default**: `tag_hinted_notes` now defaults to **ON**. Notes are tagged (`ai-hints`) when hints are generated and the tag is removed when hints are cleared or skipped. Tagging enables the fast batch-scan mode (untagged notes are the only ones scanned).
- **Tag All Cards with Hints Tool**: New **"🏷️ Tag All Cards with Hints"** button in the Advanced tab. Runs once to tag every note that already contains saved AI-Hints data, covering cards created before tagging was enabled. Skipped and cleared notes are NOT tagged.
- **Mobile JSON Button Always Available**: The 📝 **Show JSON** button is now always rendered whenever card data exists, including on AnkiDroid/AnkiMobile where the Python addon is inactive and the extra-buttons toggle is off. The "Show extra buttons" option now controls only the 🔄 Refresh button.
- **Batch Tab Layout**: Moved the **🚀 Initiate Queue**, **🛑 Stop & Discard Queue**, and **🔄 Refresh Status** buttons to the top of the "Running & Pending Batches" panel, above the batch list.

## 5.7.0 (2026-07-29)
- **Per-Model Thinking Level**: Fallback priority dialog now has a Thinking Level dropdown (`off`/`low`/`medium`/`high`) per model. Default is `off`. Controls model reasoning traces on thinking-capable models like GPT-OSS or Qwen3.
- **Per-Model Timeout**: Each model in the fallback list has a Timeout spinbox (seconds) that overrides the provider/global request timeout.
- **Multi-Select Test Row**: Ctrl+click or Shift+click to select multiple rows in the fallback table, then click **Test Row** to test them all at once. Renamed old "Test Selected" to "Test Checked" for clarity.
- **Body Params for Custom Providers**: Added "Body Params (JSON)" field to custom provider configuration, allowing extra fields (e.g. `{"think": "low"}`) to be sent in the API request body.
- **No API Key Required for Custom/Local Providers**: Custom providers and named local providers no longer force an API key entry — leave blank for unauthenticated endpoints like Ollama.
- **Editable Custom Provider Name**: Provider names can now be changed after creation via the Edit button (previously read-only).
- **Debug Prompt Logging**: When "Debug logging" is enabled in the Logs tab, full request and response payloads are logged to `ai_hints.log`.
- **Fallback Table Redesign**: Replaced QListWidget with QTableWidget in the Fallback priority dialog for proper per-column thinking level and timeout controls.

## 5.6.0 (2026-07-28)
- **Inline Editor Keyboard Shortcuts**: Added Anki editor-style keyboard shortcuts (Ctrl+M,M → `\( \)`, Ctrl+M,E → `\[ \]`, Ctrl+M,C → `\(\ce{}\)`, Ctrl+T,T → `\( \)`, Ctrl+T,E → `\[ \]`, Ctrl+T,M → `\[\begin{}...\end{}\]`, Ctrl+B → `<b>`, Ctrl+I → `<i>`, Ctrl+U → `<u>`) to the inline editing textarea during review. Uses a chord-based key system with `e.stopPropagation()` and 1500ms chord timeout.

## 5.5.0 (2026-07-26)
- **GitHub Models Provider**: Added GitHub Models (`models.github.ai/inference`) as a new AI provider with access to DeepSeek, OpenAI, Meta, Mistral, and Microsoft models through GitHub's inference API.
- **Custom Provider Models URL**: Added a separate "Models URL (optional)" field in the Custom Provider dialog, allowing users to specify a distinct URL for model discovery independent of the chat completion endpoint.
- **Custom Provider Routing Priority**: Custom provider endpoint configurations now take priority over built-in provider routing, so mapping a custom URL to a built-in provider name correctly routes through the custom provider path.

## 5.4.1 (2026-07-26)
- **Per-Provider Timeout Relocation**: The per-provider request timeout setting has been moved to the **AI Providers** tab, shown next to each provider row. Fallback model testing and search were also improved.

## 5.4.0 (2026-07-26)
- **Default Front-Side MCQ Selection**: Bare `1–9` keys now select the corresponding option on the question side by default.
- **Answer-Side Rating Preservation**: Anki’s normal `1–4` rating shortcuts remain unchanged on the answer side.
- **Shortcut Collision Fix**: Existing Anki numeric shortcuts are wrapped instead of skipped, allowing front-side selection while preserving answer-side actions.

## 5.3.5 (2026-07-26)
- **Offline Generation Handling**: Stop fallback provider/model attempts when connectivity is lost, preventing cascaded DNS and timeout errors.
- **Offline UI Reset**: Clear the foreground generation animation when an offline response is received.

## 5.3.4 (2026-07-23)
- **QLineEdit Deleted Crash on Save**: Fixed `RuntimeError: wrapped C/C++ object of type QLineEdit has been deleted` when saving settings after adding/editing a custom provider. `refresh_custom_list()` now resets `api_key_edits` alongside `model_edits` when rebuilding provider rows, and the save routine safely falls back to the last persisted value for any stale deleted widget reference.
- **Custom Provider Key Sync**: Adding or editing a custom provider immediately syncs the API key into the live config and active provider row, eliminating the need to re-enter the key after creation.
- **Custom Endpoint URL Auto-normalization**: Custom provider URLs automatically get `/chat/completions` appended if omitted, so both `https://aihubmix.com/v1` and `https://aihubmix.com/v1/chat/completions` work without manual correction.

## 5.3.3 (2026-07-23)
- **Custom Provider Key Syncing**: Adding or editing a custom provider now automatically populates and syncs its API key across the settings dialog, removing duplicate key entry steps.
- **Custom Endpoint URL Auto-Normalization**: Custom provider endpoint URLs automatically append `/chat/completions` if omitted (supporting both `https://domain.com/v1` and `https://domain.com/v1/chat/completions`).
- **Warning Emoji Variant Support**: Added support for both `⚠️` (U+26A0 with variation selector) and `⚠` (U+26A0) warning symbols in factual error detection and UI button rendering.
- **QComboBox Qt Object Deletion Fix**: Resolved a `RuntimeError` crash when saving non-modal fallback dialogs after parent widget destruction.

## 5.3.2 (2026-07-16)
- **Stop Foreground Generation by Clicking Again**: Clicking the active **Generate** button a second time now stops the in-progress foreground generation.
- **Prompt Updates & Commutator Fix**: Refreshed the default prompt configuration and fixed commutator-related generation handling.

## 5.3.1 (2026-07-16)
- **Packaged Release**: Re-released the add-on package with an updated `latex_fixer` submodule pointer.

## 5.3.0 (2026-07-14)
- **Bulk TTS Hints Preservation**: Fixed a bug where running bulk TTS generation (PiperTTS addon 428593773) caused the `ai-hints-json` data block to be stripped from note fields. A new patch on `bulk_to_notes.add_audio_to_card` re-reads the freshest note from the database before and after each save to guarantee the hints div is always preserved, even under race conditions or stale note-object scenarios.
- **Debug Logging Toggle in Logs Tab**: Added a **"Debug logging"** checkbox directly in the Settings → Logs tab. Enabling it immediately switches the logger to `DEBUG` level (no restart required), making it easy to trace low-level events such as the TTS patch activity without editing raw JSON config.

## 5.2.0 (2026-07-14)
- **Reviewer Card-Transition DOM Bleed Fix**: Resolved an issue where stale AI hints and metadata from previously viewed cards bled into empty cards, which blocked automatic generation (autogen) and pre-generation (pregen) until restarting Anki or returning to the deck browser.
- **Optimized Reviewer Startup Polling**: Reduced the initial script loading polling check interval from 50ms to 10ms, speeding up reviewer card display and hints rendering latency on the first card of a session.

## 5.1.1 (2026-07-13)
- **LaTeX False-Positive Fix for Text Conjunctions**: Fixed a bug where hints containing `&amp;` as a text conjunction (e.g. "Commerce &amp; Industry", "Power &amp; Coal") were incorrectly parsed as LaTeX matrix column separators and wrapped in math delimiters. The `isWordAmp` guard regex now accounts for optional spaces around `&amp;` and `&` in word contexts.
- **Windows / Python 3.13 Config Crash Fix**: Fixed `NameError: name 'Optional' is not defined` in `batch_manager.py` that crashed the Settings dialog on Anki 26.05 (Windows). Added `Optional` to the `typing` imports.

## 5.1.0 (2026-07-13)
- **Auto-Rate Option Selections with Custom Delays**: Added `Auto Rate Good on Correct Option` and `Auto Rate Again on Wrong Option` settings under the General settings UI tab. If active, selecting an option on the front/question side automatically rates the card as 'Good' or 'Again' after a user-specified delay duration (by default, 0.0s instant for correct selection, 1.0s delay for wrong selection to review card details first). Both are disabled by default. Supports full undo integration—cancels pending rating timers on card switches and locks pycmd auto-rating triggers for 0.8s following an undo event to prevent accidental card skips.
- **Inline Editing Lock Fix**: Selection click auto-rate triggers are disabled on option items when holding Ctrl/Cmd (which starts inline editing) or when the option text block is already actively in edit mode.
- **Math Parser Boundary Match Improvement**: Refactored the JavaScript LaTeX delimiters wrapper regex to enforce boundary matching (`/\\\b[A-Za-z]+\b/`). This prevents regular English/Malayalam hyphenated words (like "Re-entry") containing control character sequences from being incorrectly formatted as LaTeX, restoring normal edit-mode control.

## 5.0.3 (2026-07-13)
- **Settings UI Argument Forwarding Fix**: Updated lazy loader wrapper parameter signatures (`on_config_dialog`) to dynamically forward variable positional and keyword arguments (*args and **kwargs) down to the config layout, fixing TypeError crashes when launching batch dialog menus from browser selections.

## 5.0.2 (2026-07-13)
- **Startup Speed Optimization**: Deferred eager/premature imports of the main configuration dialog and provider modules until they are actually opened or triggered. This decreases import load time from over 1.15 seconds to under 0.32 seconds (a 3.5x speed boost), preventing resource contention at Anki startup.

## 5.0.1 (2026-07-12)
- **Checkable Multiple Modifiers**: Replaced single modifier dropdowns in the Shortcuts settings tab with checkboxes for Ctrl, Alt, Shift, and Meta, allowing compound modifiers (like `Ctrl+Alt`) to be configured independently for both primary shortcuts and option selection shortcuts.
- **Default Modifier Change**: Changed default MCQ options selection modifier key combination to `Ctrl+Alt` to prevent collisions.
- **Python Keypress Interception**: Options selection hotkeys are now registered on the Python side, intercepting shortcuts (like `Ctrl+Alt+1-9`) and routing them to the card view before Anki's global handlers can catch them.

## 5.0.0 (2026-07-12)
- **Interactive MCQ Option Selection**: Click or tap on generated MCQ options during review to test your knowledge.
- **De-deferred Color Highlighting**: Clicked options are saved in state and colored on the back (answer) side of the card—highlighting green for correct, red for incorrect (with the true correct answer highlighted green next to it).
- **Keyboard Selection Shortcuts**: Press number keys `1-9` on the front/question side to select options and automatically flip the card. Reviewer rating hotkeys continue to function on the back side as normal.
- **Improved Option Box Styling**: Added distinct rounded boundaries, padding, and subtle light mode / night mode hover shading to option list items.

## 4.5.0 (2026-07-09)
- **Model Blacklist Cooldown Sorting**: Added a new "Sort By" dropdown selection box in the Advanced Settings panel. Users can now sort active provider/model cooldown locks and failure streaks alphabetically by **Name**, by remaining cooldown duration (**Time Remaining Descending/Ascending**), or by the magnitude of consecutive API rate-limiting failure **Streaks**.

## 4.4.1 (2026-07-08)
- **High-Quality Exam Distractor Guidelines**: Re-engineered the default system prompt to strictly forbid fabricated, synthetic, or fake facts, names, dates, or formulas across all subjects.
- **Subject-Specific MCQ Rules**: Integrated universal and subject-specific MCQ test design rules (Math calculation traps, Science conceptual misconceptions, Language faux-amis, and PSC Cluster sequencing) to generate challenging, high-quality exam distractors resembling actual board and competitive exams.

## 4.4.0 (2026-07-08)
- **Time-based Orphaned Card Scan Optimization**: Introduced a new toggle options checkbox (`[x] Only scan notes modified since last clean scan`) to speed up orphaned card checking. The scanner uses Anki's native `edited:X` search parameters combined with config-managed timestamp tracking to scan only notes modified since the last clean run, making checks almost instantaneous.
- **Circular Import Fix**: Resolved a circular import `ImportError` when running "Clean Orphaned Hints..." directly from Tools or browser context menus outside the config UI.

## 4.3.6 (2026-07-08)
- **Semicolon cloze deletion separator**: Switched the multi-cloze same-ID answer separator from a comma (`, `) to a semicolon (` ; `) to prevent collisions with standard text punctuation and digit separators. Updated the default system prompt, backend card parser, and reviewer JavaScript to format and parse multiple cloze answers using the new delimiter.

## 4.3.5 (2026-07-07)
- **Malayalam dotted-circle rendering fixes**: Simplified LaTeX math detection regex to prevent catastrophic backtracking and infinite loops when compiling cards.
- **Ampersand matrix collision avoidance**: Updated the reviewer matrix column detector to ignore standard textual ampersands (e.g., `"AEW&C"`, `"R&D"`), fixing Malayalam options from being incorrectly wrapped and broken.

## 4.3.4 (2026-07-07)
- **Dollar-sign delimiter normalization**: The reviewer webview now automatically converts AI-generated `$...$` (inline) and `$$...$$` (display) math delimiters to Anki-standard `\(...\)` and `\[...\]` at render time, so mixed-delimiter hints and options (e.g. `"the new $x'$-axis"`) display correctly without any manual fixup.

## 4.3.3 (2026-07-07)
- **Tabular option formatting**: Instructed the default system prompt to output multi-row/tabular lists of values (e.g. microprocessor status signal tables) using line breaks (`\n`) matching the row structure of the question rather than formatting them all in a single line. Added `white-space: pre-wrap` to the reviewer CSS so newline characters render as actual line breaks.
- **Targeted math inline formatting**: Fixed a bug where a whole hint sentence containing a bare LaTeX expression (like `\overline{M}`) was wrapped in inline math delimiters (`\(` and `\)`), causing MathJax to strip all spaces and render the whole sentence in math-italic font. Now only the specific LaTeX math segments are wrapped.
- **`<anki-mathjax>` tags in options/hints**: Updated `escapeHtml` to unescape `&lt;anki-mathjax&gt;` back to real tags and strip backslash escaping introduced by LLM markdown output.
- **Matrix environment auto-wrapping**: Fixed rendering of options that use `\begin{pmatrix}...\end{pmatrix}` syntax (without outer `\(` delimiters) — the entire option is now automatically wrapped in `\(...)` so MathJax compiles it correctly.
- **Double-delimiter bug fix**: Fixed a bug where hints already containing inline `\(` math (e.g. `"...the scale \(\lambda_L\)."`) were incorrectly getting an extra `\(` prefix, producing broken `\(\(\lambda_L\)\)` output. Mixed inline-math text is now returned as-is.
- **Column-aligned matrix detection**: Options encoded as `&`-separated column values (e.g. from Anki's native HTML entity `&amp;`) are now auto-wrapped in `\begin{matrix}...\end{matrix}` environments. HTML comparison entities (`&lt;`, `&gt;`, etc.) are correctly excluded from this detection.

## 4.3.2 (2026-07-07)
- **Fix div wrapper deletion bug**: Fixed a bug where clearing a single card's hints (e.g. `c1` only) from a multi-card note also stripped out the hidden `<div class="ai-hints-json" ...>` container wrapper, leaving raw JSON visible as plain text on the card.
- **STEM pre-factors / constants outlier balancing**: Updated prompt rules to require that physical and mathematical pre-factors or constants (such as $\frac{1}{i\hbar}$ or $2\pi$) be balanced evenly (e.g. 2-vs-2 split) across multiple-choice options to prevent them from becoming visual outliers.

## 4.3.1 (2026-07-05)
- **Refined Timeout & Fallback Logic**: Added configurable active-review (`request_timeout`) and background pre-generation (`pregen_request_timeout`) timeout settings. Refined the fallback logic to fail-fast on host unreachable network errors, while allowing read operation timeouts to try other models of the same provider with a maximum cap of 2 consecutive failures.
- **Smarter Auto-Regeneration Controls**: Integrated the `auto_regenerate_if_modified` option in the General settings UI to automatically refresh hints/options when edited notes are newer than their saved generation time.
- **Sequence Distractor Generation Refinement**: Updated the default system prompt to request actual, unmodified adjacent sequence provisions (e.g. adjacent constitutional amendments) as distractors instead of forcing grammatical prefix-aligned placeholders.

## 4.3.0 (2026-07-02)
- **Multi-Local Provider Support**: Local AI can now be configured as multiple endpoints with independent enable/disable state, ordering, and per-endpoint fetch/test actions from the Providers tab.
- **Batch Queue Recovery**: Saved local batch queues now rehydrate after Anki restarts, so interrupted queues can resume from disk instead of only surviving in-memory sessions.
- **Release Cleanup**: Removed stale single-endpoint local UI references and aligned packaging metadata for the new release.

## 4.2.4 (2026-07-02)
- **Front-Side Shortcut Flexibility**: AI-Hints shortcuts now work with or without the configured modifier on the question/front side, while the answer/back side still requires the modifier so Anki rating keys remain safe.
- **Smarter Auto-Regeneration Controls**: Added modified-card regeneration alongside version-gated and time-gated regeneration, so edited notes can refresh stale AI data automatically when auto-generation is enabled.
- **Configurable Request Timeouts**: Added separate active-review and pregeneration API timeout settings. Host/network failures now fail fast, while read timeouts can still try limited model fallbacks.
- **Inline Editing Escape Save Documentation**: Clarified that `Escape` saves changed inline edits and reverts only unchanged edits.

## 4.2.3 (2026-07-01)
- **Bug-Fix Re-Release**: Re-packaged the v4.2.2 build with the same fixes (Inline Editing Escape Save, cloze placement alignment, JSON block persistence).

## 4.2.2 (2026-07-01)
- **Visual Alignment & Card Layout Fixes**: Ensured that the hints/options container is placed directly between the Front and Back sides (or right after the Cloze text field) on both desktop Anki and AnkiDroid, preventing it from incorrectly shifting to the bottom of the card (after the `Extra` field).
- **Escape Key Saves Inline Edits**: Pressing the `Escape` key inside the inline editor now saves the edit (using `saveEdit()`) instead of discarding changes, with automatic reversion if the value remains unchanged.
- **Rendering Bypass & DOM Persistence**: Prevented the note fields cleanup patch from stripping out the hidden JSON blocks during card rendering, and updated reviewer hooks to preserve JSON blocks in the webview DOM.
- **Formula Generation Enhancements**: Updated system prompt instructions to allow modifying both sides of equations to generate realistic distractor formulas, and added the physics Binet equation as a reference pattern.
- **UI Cleanups**: Removed the "Generate" button from the review bottom bar and disabled showing results in popup windows for a cleaner, inline-only review experience.

## 4.2.1 (2026-07-01)
- **Generalized Proximity and Symmetry Rules**: Refined and generalized system prompt rules in `config.json` for numbers, percentages, years, dates, and measurements to ensure clean distractor formatting.
- **Visual Outlier Prevention**: Enforced the strict "Odd One Out" rule in prompt instructions to prevent single visual or structural outliers from giving away the correct answer.
- **Symmetric Distractor Options**: Balanced sections and months using pattern guides to avoid predictable default prefixes.

## 4.2.0 (2026-06-29)
- **Queued Batch Jobs**: Batch generation now supports multiple queued jobs instead of rejecting new requests while one queue is active. The Batch tab shows the active job, pending jobs, and controls to reorder, cancel, or clear queued jobs.
- **Expanded Bulk Skip/Unskip Actions**: Added unskip actions for selected browser cards, browser sidebar groups, and deck browser deck menus, alongside the existing skip/clear workflows.
- **Skip Clears Stale AI Data**: Marking a card as skipped now replaces that card's saved AI payload with a clean skipped marker, preventing old hints/options from lingering under skipped state.
- **JSON-Only Storage Cleanup**: Removed the legacy `storage_mode` configuration path and updated migration/batch code to use the hidden JSON storage engine consistently.

## 4.1.0 (2026-06-29)
- **Decoupled System Prompt**: Separated the core system prompt from user-specific instructions. The core prompt is now loaded dynamically from `config.json` at runtime, ensuring prompt updates are applied automatically upon addon updates. Custom instructions are now stored in `additional_system_instructions` in `meta.json` and appended to the core prompt.
- **Persistent Profile-Relative Batch State**: Relocated the batch queue state file (`ai_hints_batch_state.json`) from the addon folder to the user's active Anki profile directory. Added automatic startup migration for existing queue states and deferred loading to prevent conflicts during startup.
- **Config-Managed Model Blacklist**: Migrated the model lockout/blacklist cache from a volatile local file (`blacklist.json`) to the persistent `meta.json` config under `"model_blacklist_data"`, preserving cooldown states during upgrades.

## June 28, 2026 (v4.0.1)
- **LaTeX Control-Character Restoration Fix**: Fixed LaTeX formatting issues caused by restoring control characters parsed from unescaped LLM JSON, ensuring math output survives un-escaped JSON responses.

## June 25, 2026 (v4.0.0)
- **Inline Editing of Hints and Options**: Introduced interactive inline editing for hints and multiple-choice options directly during review. Holding `Ctrl` (or `Cmd` on macOS) highlights editable items on hover. Ctrl-clicking (or Cmd-clicking) an item turns it into an inline editor (`<textarea>`). Edits are saved on `Enter`, blur, or `Escape` when the value changed, which surgically updates the note's JSON block in the Anki database, synchronizes the `correct_answer` field if the correct option (index 0) was modified, updates the generated hint cache, and pushes the updated data back to the frontend dynamically with zero page flicker.
 
## June 22, 2026 (v3.8.2)
- **Tools Menu Clean Orphans Fix**: Fixed a `TypeError: bad argument type for built-in operation` crash when running the "Clean Orphaned Hints..." maintenance tool from the Tools menu. This was caused by PyQt passing a boolean argument to the trigger slot, which overrode the default query string. We now strictly validate and sanitize the parameter type.

## June 21, 2026 (v3.8.1)
- **Pregenerated Card Momentum Scrolling Fix**: Resolved a bug where trackpad kinetic/momentum scrolling on the previous card automatically triggered the "Show Answer" gesture (revealing the cloze) on the next card if that card was pregenerated. We now update the webview dynamically via direct JS push for pregenerated cards, avoiding recursive page reloads and event loop disruption.

## June 20, 2026 (v3.8.0)
- **Targeted Clean Orphans Maintenance**: Added the ability to run "Clean Orphaned Hints..." directly from the Card Browser context menu (scoping to the selected cards) or from the Deck Browser cogwheel menu (scoping to the selected deck and its subdecks).
- **Non-Modal Cleanup Dialog**: Configured the orphaned hints cleanup dialog to be non-modal so that users can interact with Anki and the card browser while reviewing and cleaning orphaned hints.
- **Anki Terminator Companion Conflict Fix**: Fixed a bug where the third-party `Anki_Terminator_Performance_Companion` addon overwrote the `clean_ai_hints_from_text` function with a buggy version that stripped cloze tags (e.g. converting `{{c1::വിൺ}}` to empty placeholders/whitespace). We now declare `_companion_optimized = True` to prevent this override safely.
- **Card Browser Row Fetch Robustness**: Enhanced `browser_did_fetch_row` hook error handling to gracefully handle cases where row cells are missing, avoiding hook deactivation by Anki.
- **Unified Cogwheel Menu Integration**: Moved the batch generation menu entry and added the "Clean Orphaned Hints..." action to the deck selector cogwheel sub-menu in the deck browser.

## June 19, 2026 (v3.7.0)
- **Organized Card Browser Context Menu**: Moved "✨ Batch Generation..." and "Clear AI-Hints" into a clean "AI Hints" nested sub-menu to avoid cluttering Anki's main context menu.
- **Bulk Skip AI Generation**: Added a new "Skip AI for Selected Cards" action inside the card browser's "AI Hints" sub-menu. This allows marking multiple selected cards as skipped in the database in a single click.
- **Clear Skipped State Integration**: Verified and tested that the "Clear AI-Hints" action correctly clears the skipped state from the cards, preparing them for generation.

## June 19, 2026 (v3.6.5)
- **Fix Sequential Queue Loop on Empty Cards**: Workers in the batch sequential queue now save a skipped state (`_skipped: True`) to the database when a card exists but has empty content (e.g. missing Cloze deletion). This stops verification passes from endlessly re-queuing the card and hitting the maximum pass limit.
- **Improved Skip Visibility in Reviewer UI**: Pregeneration and manual generation now correctly record `_skipped: True` to the database and refresh the current card instead of silently discarding empty cards. This clears the stuck generating spinner and updates the reviewer UI with the skip status.

## June 18, 2026 (v3.6.4)
- **Robust Math/Image Cloze Parsing**: Fixed sequential queue processing skipping cloze cards that contain images or formulas by returning an explicit existence boolean instead of checking if the text content is empty.
- **HTML Image Descriptor Preservation**: Enhanced `_clean_html` to convert `<img>` tags into descriptive textual placeholders (e.g. `[Image: filename - alt]`) rather than stripping them completely. This preserves context for math clozes and allows the LLM to generate higher quality hints.
- **Stuck/Failed Card ID Visibility**: Added real-time tracking and visual display of failed card IDs in the batch generation status summary. Clickable card links are shown for active, dormant, and completed queue runs.
- **Startup Connection Stability**: Delayed sequential queue auto-resume until after the local proxy daemon is fully initialized.

## June 14, 2026 (v3.6.3)
- **Interactive Warning-Removal Action**: Added an interactive warning-removal button inline next to warning hints during card review, letting you dismiss factual-error warnings directly on the card.

## June 11, 2026 (v3.6.2)
- **Optimized Default Logging Level**: Set the default log verbosity to INFO to reduce noise, and made the debug/verbose logging level configurable.
- **Batch Scan Progress Dialog**: Added a `QProgressDialog` that shows progress while scanning cards for batch generation.

## June 11, 2026 (v3.6.1)
- **Granular API Key Blacklisting**: Refactored the key rotation blacklist to block specific model-key-provider combinations rather than entire keys or models globally.
- **Gemini 3.5 Flash Support**: Added support for Google's new `gemini-3.5-flash` model as the default Gemini and Antigravity provider model.
- **Manual Test Bypass**: The settings test buttons now bypass the blacklist and force live testing, auto-clearing the cooldown if the test succeeds.
- **Native Gemini Batch Integration**: Updated the Gemini batch submission and status checking to use and respect the new granular combination blacklist.

## June 10, 2026 (v3.6.0)
- **Pregeneration Button Redesign**: Fixed pregeneration button animation and styling. Restored original green colors for light mode and night mode with explicit overrides for maximum text readability and visual consistency.
- **Prompt Optimization & Factual Warning**: Updated the system prompt to enforce exactly 3 hints across all card types. If the front or back contains factual errors, the 3rd (last) hint is formatted with a warning symbol `⚠️` to indicate exactly what is wrong and explain the correct information.

## June 10, 2026 (v3.5.0)
- **Multiple API Keys Rotation**: Configure multiple API keys per provider in a new visual Manage Keys dialog. Keys can be assigned custom labels/names for clearer logging.
- **Enabled/Disabled Key States**: Temporarily disable backup keys using checkboxes in the GUI without removing them from your settings.
- **Persistent Key Cooldowns**: API key blacklists are now written to `blacklist.json` on disk to survive Anki restarts. Added an optimized global cache flag to prevent redundant disk I/O.
- **Python 3.11+ Closure Fix**: Resolved a `NameError` crash occurring in asynchronous exception closures on Python 3.11+.
- **Orphan Hints Detection**: Added robust detection and cleanup of orphaned hints in card parser.
- **Clean Test Logs**: Isolated unit test logs to prevent mock API failures from polluting your production log file.

## June 9, 2026 (v3.4.1)
- **Optimized Prompt Efficiency**: Re-engineered system prompts for maximum token efficiency (~1k tokens saved per request) while improving distractor quality via Sequential Parallelism.

## June 8, 2026 (v3.4.0)
- **Persistent Pre-generation Cache**: Background hints now survive Anki restarts and Undo operations. Data is strictly retained until successfully added to a card.
- **Manual Cache Maintenance**: Added a "🧹 Clear Pregen Cache" button to the Advanced settings tab.
- **Enhanced Data Integrity**: Eliminated "data bleed" between cards and sessions by ensuring strictly isolated DOM cleanup on every load.
- **Fallback Visibility**: Added visual 🚫 Blacklisted badges in fallback priority dialogs to instantly identify models on cooldown.
- **Infinite Regeneration Fix**: Completely refactored cloze matching to use robust card keys, resolving issues with summary-style AI answers.
- **Interactive Logs**: 13-digit card IDs in the logs are now clickable, and a new "Refresh" button has been added to the Logs tab.
- **Skip AI Feature**: Added the ability to permanently skip AI generation for specific cards with a single click.
- **Orphaned Hint Cleanup**: New maintenance tool to scan and remove AI-Hints data for notes that have been deleted or modified.
- **Improved Cloze Parsing**: Robust depth-aware parsing for complex nested cloze deletions.
- **Stability Fixes**: Resolved IndentationError and TypeError regressions in the reviewer hooks.

## June 8, 2026 (v3.3.2)
- **Fixed Math Cloze Loop**: Resolved an endless regeneration loop for cards containing math formatting inside cloze deletions. The system now robustly handles LaTeX normalization during answer verification.
- **Optimized UI Refresh**: Prevented redundant re-rendering of reviewer card HTML to improve performance and stability during background generation.
- **Adjusted Fallback Delay**: Set the default model fallback cooldown to 10 minutes to better handle transient API rate limits.

## June 8, 2026 (v3.3.1)
- **LaTeX Repair Disabled by Default**: Set the "Repair AI LaTeX Errors" setting to `off` by default. This preserves standard math normalization (delimiters, JSON escaping) while making aggressive repairs opt-in for maximum stability with modern models like Claude 3.7 or Gemini 2.0.
- **Improved Log Ignoration**: Updated `.gitignore` to more robustly handle rotated log files (`.log.1`, `.log.2`) and ensured critical metadata files remain tracked.
- **Test Suite Stability**: Resolved unit test regressions in `CardParser` and improved coverage for LaTeX normalization and JSON-only storage.
- **Cleaned Up Batch Logic**: Removed stray code and improved reliability of multi-threaded generation hooks.

## June 8, 2026 (v3.3.0)
- **Granular Batch Queue Control**: You can now see the next 5 cards in the pending batch queue directly in the status area, with individual **[✖ Discard]** buttons to remove specific cards without stopping the whole process.
- **Deck-Specific Maintenance Scoping**: Added a searchable deck selector to the **Advanced** tab. All maintenance tools (Migration, Unicode Fixer, Orphan Cleanup, and Naked JSON Purge) can now be scoped to a specific deck or run on the entire collection.
- **"👻 Convert HTML to Hidden JSON" Tool**: Introduced a new heuristic parser that can "read" visible legacy HTML hint boxes (including those in Malayalam and other complex languages) and convert them into the optimized, invisible JSON format to clean up your editor.
- **Aggressive Consolidation Logic**: Enhanced the core saving engine to prevent "stacked boxes" caused by race conditions during multi-threaded generation. It now forces data to merge into a single, keyed JSON block.
- **3-Level Log Rotation**: Implemented a robust 3-level log rotation system (`ai_hints.log`, `.1`, `.2`). Logs now automatically rotate on every Anki startup, ensuring each session starts with a fresh log file while preserving recent history.
- **Improved UI Clarity**: Renamed the "Stop Queue" button to **"Stop & Discard Queue"** to better reflect its full action of halting the process and clearing the remaining items.
- **Stability Fixes**: Resolved several `AttributeError` crashes in the configuration UI and improved frontend randomization robustness for card re-shows and background data pushes.

## June 7, 2026 (v3.2.0)
- **Automatic Multi-Pass Batch Verification**: Introduced a "chain-reaction" verification loop that automatically identifies and retries cards that failed to generate hints. The system now performs up to 10 sequential passes until the entire requested batch is complete, ensuring maximum reliability against transient network or API errors.
- **Enhanced Collection Maintenance Logging**: Added explicit, high-level `INFO` logging for all collection-wide tools in the **Advanced** tab. You can now track the start, progress (including user cancellations), and final summary of AI Data Migrations, Unicode Escape Conversions, Orphaned Hints Cleanups, and Naked JSON Purges directly in the **Logs** tab.
- **Enforced Language Consistency**: Updated the system prompt to strictly require that AI hints and distractors are generated in the **same language** as the question content. This prevents the AI from defaulting to English when processing cards in other languages (e.g., Spanish, Malayalam, etc.).
- **Finalized Log Streamlining**: Demoted low-level operational logs (like raw JSON payloads and internal polling status) to the `DEBUG` level. This keeps the standard `INFO` view focused exclusively on card generation milestones and significant configuration changes.
- **Improved Batch Status Summary**: Updated the Batch tab to display real-time pass tracking (e.g., `Pass #2`) and overall success statistics across the entire verification cycle.

## June 6, 2026 (v3.1.3)
- **Fix Copy-Paste Cloze Contamination**: Implemented a deep answer-matching validation check that compares the stored `correct_answer` inside the hidden JSON payload against the actual text of active cloze deletions on the note, instantly purging mismatched/copied cloze data.
- **Time-Gated Auto-Regeneration**: Added support for automatically regenerating hints that are older than a specific date/time. Configurable in the General settings tab (`auto_regenerate_if_old_time` and `auto_regenerate_min_time`).

## June 5, 2026 (v3.1.2)
- **Fix Browser Search Bug in Config UI**: Fixed an `AttributeError` that occurred when clicking "Show Card" on orphaned hints, by utilizing a version-agnostic browser search call.
- **Refresh Options Randomization on Review Retries**: Modified option-shuffling to generate and persist a new random seed on the card's front side, ensuring that options are reshuffled on every review retry while maintaining layout consistency between front and back sides of the same review.
- **HTML Code Tag Options Highlight Fix**: Corrected answer normalization to preserve code-containing HTML tags like `<a>`, `<link>`, and `<url>` (while still stripping formatting wrappers). This prevents different HTML code options from being normalized to the same text and mistakenly highlighted as correct.

## June 5, 2026 (v3.1.1)
- **Batch Queue Handover & Peer Coordination**: Modified concurrent queue threads to wait for peers when the queue is empty. This prevents race conditions where late-failed/requeued cards are left unattended, ensuring active threads successfully hand over failed cards to other working providers.
- **Fix Thread Hang/Deadlock on Queue Completion**: Fixed a bug where rate-limited or blacklisted provider threads remained stuck in infinite sleep/cooldown loops after the batch queue was fully processed, preventing the queue from finishing. Threads now check if the queue is empty and exit cleanly.
- **Batch Queue Rate-Limit Handling**: Modified sequential batch queue worker threads to pause/sleep when a provider is rate-limited or blacklisted, preventing it from popping and immediately failing pending cards in the queue.
- **Provider Isolation in Diagnostic Tests**: Enforced `only_this_provider=True` during manual connection and model testing to isolate provider checks, preventing successful fallback routing from misrepresenting status.
- **Hugging Face Compatibility Fix**: Removed the `response_format` JSON parameter from Hugging Face API requests to prevent structured-outputs `400 Bad Request` errors on non-supporting endpoints.
- **GUI Thread Status Tracking**: Added detailed thread status labels (`⏳ Rate Limited / Cooldown`, `⏸️ Paused`, `Processing`, etc.) in the active concurrent threads list to ensure better diagnostic visibility.

## June 5, 2026 (v3.1.0)
- **Manual Regeneration UI Refresh**: Fixed the post-regeneration display issue by forcing a clean card refresh on manual regeneration, guaranteeing the card is redrawn with the newly generated elements embedded.
- **Persistent JSON Panel State**: Stored the JSON panel's open status in persistent session storage (`state.showJson`), preventing the panel from closing automatically when background pre-generation status updates trigger container re-renders.
- **MCQ Formatting & Structural Symmetry**: Enforced MCQ best practices, options symmetry, distractor formatting rules, and mathematical sign balance directly in the AI client's generation prompts.
- **Card Review State Resets**: Fixed a bug where option/hint elements remained expanded during card review retries/fails. The front side of the card now resets states to user defaults when rendering.
- **UI & Logging Enhancements**:
  - Render clickable URLs (turning plain text log links into functional HTML anchors) in the logs tab.
  - Replaced intrusive toast notifications with tooltip-style hover errors when prioritizing API connection tests.
  - Propagated detailed HTTP error messages down to provider testing outputs to assist in configuring providers.
  - Kept provider registration URLs clickable even when the provider checkbox is disabled.
- **Concurrent Multi-Provider Batch Generation**: Added concurrent multi-provider generation with single-provider fallback queues in the batch manager to process queues faster.
- **Deck Browser Cogwheel Integration**: Added batch generation option directly in the deck browser cogwheel menu with updated queue selection status UI.
- **Thread-Safety & Deadlock Prevention**: Fixed background thread-safety database access and stopped queue deadlock, added auto-saving of configuration on batch start, fixed NoneType error in fallback models retrieval, and added model success info logs.
- **Startup Backup Log Cleanup**: Modified startup log clearing to also clean or delete backup log files (`ai_hints.log.1`).

## June 4, 2026 (v3.0.1)
- **Enhanced MathJax and LaTeX Rendering**:
  - Dynamically convert LaTeX math delimiters to `<anki-mathjax>` tags in the reviewer template for proper typesetting.
  - Added support for bare LaTeX equations without delimiters up to 1000 characters.
  - Added `tex2jax_process` class to math tags and containers to bypass Anki's global MathJax ignore wrapper.
  - Fixed MathJax math formula rendering in reviewer template.
- **Improved Fallback Fetch Logic**: Updated the fallback fetch logic.

## June 3, 2026 (v3.0.0)
- **Major Architecture Overhaul**: Transitioned to a more robust background generation and UI synchronization engine.
- **Advanced Global Fallback Priority (Global Flat List)**: Introduced a new global flat-list configuration dialog to custom-arrange model fallbacks across different providers. Features an interactive toggle switch to enable the global priority list, which dynamically manages fallback sequences across all your configured AI accounts.
- **Dual-State Generation Animations**: The 'Generate' button now features two distinct pulsing states:
    - **Blue Pulse**: Indicates the current card is actively generating. The button is temporarily disabled to prevent duplicate requests.
    - **Green Pulse**: Indicates the AI is pre-generating upcoming cards in the background. The button remains **fully interactive**, allowing you to force-generate the current card without waiting for the background tasks.
- **Continuous Buffer Refilling**: The pre-generation engine now automatically refills your configured buffer (e.g. 10 cards) in a background chain reaction, ensuring your next few minutes of review are always ready instantly.
- **Smart Tooltip Positioning & Formatting**: 
    - Replaced the large, obstructive test result overlays with mouse-relative tooltips that always appear to the right of your cursor, ensuring model names and checkboxes remain visible.
    - Tooltips now use width-constrained HTML with word-wrapping and monospace fonts, making detailed AI JSON responses significantly easier to read.
- **Improved UI Modality & Sync**: The Advanced Fallback dialog is now application-modal to prevent configuration conflicts, and it features a live "Fetch All" bridge that updates status indicators in real-time as background threads complete.
- **Log Streamlining**: Dramatically reduced log noise by moving internal "Filtering out" and "Auto-show" messages to the DEBUG level, leaving the INFO log clear for actual generation progress.
- **Interactive Drag & Drop Reordering**: Enabled native internal drag-and-drop reordering inside the QListWidget for fallback priority lists, plus a **Restore Defaults** option to reset to factory defaults.
- **Batch Testing Support**: Added a **Test All Models** button to sequentially test and report live status for all active/configured providers at once.
- **Dynamic Fetch and Stop Controls**: Implemented dynamic button text changes (`Fetch All` -> `Stop Fetch All` / `Test All` -> `Stop Test All`) for the fallback configuration windows, complete with background thread task cancellation.

## June 2, 2026 (v2.8.4)
- **Fixed Model Fallbacks Logic**: Corrected a critical logic issue where the model fallback tree was cut short upon any specific model's failure (e.g. rate limit, 503 service unavailable, or connection timeout), jumping immediately to the next provider instead of retrying with other valid fallback models for the same provider as intended.
- **Consolidated Redundant Logging**: Replaced noisy, multi-line disabled provider filter logs with a single combined log line, dramatically reducing log clutter and spam during generation and pre-generation cycles.

## June 2, 2026 (v2.8.3)
- **Critical Fix: Settings Saving & Persisting Bug**: Resolved a severe packaging issue where the crucial `config.json` template was accidentally omitted from AnkiWeb packages, causing settings to fail to persist and resetting user preferences, API keys, and models.
- **Excluded Local Configs/Credentials from Releases**: Strictly barred local development `meta.json` files, logs, and temporary state databases from being bundled in release builds, fully protecting user security and privacy during upgrades.

## June 1, 2026 (v2.8.2)
- **Purge Stale Naked JSON Blocks**: Added a new graphical maintenance tool under the **Advanced** tab to safely scan your collection and purge unwrapped raw JSON text blocks while keeping correctly wrapped AI-Hints data completely untouched.
- **Full Undo Checkpointing & UI Refreshes**: Wrapped all database-modifying maintenance tools (Migrate Data, Convert Unicode Escapes, Clean Orphans, and Purge Naked JSON) in standard Anki undo checkpoints (`mw.checkpoint`) with full support for database restoration (`Ctrl+Z`) and UI live refreshes (`mw.reset()`).

## June 1, 2026 (v2.8.1)
- **Qt Namespace Bug Fix**: Fixed a critical `AttributeError` crash (`type object 'Qt' has no attribute 'ItemData'`) when opening the Config GUI under newer PyQt6/PyQt5 environments, correcting it to the proper `Qt.ItemDataRole` namespace.

## June 1, 2026 (v2.8.0)
- **Unified Providers Layout**: Merged the API keys groups and priority rows into a clean, card-like block layout. You can now configure keys (with eye toggles 👁️), active models, and priority-order in a single location, removing redundant provider lists.
- **Enable/Disable Providers**: Added checkbox toggles next to each provider in the priority list to easily turn them off completely. Disabled providers are bypassed during standard generation and fallbacks even if their API keys are configured.
- **Manage Fallback Models**: Made fallback models inside the "Fallbacks" priority dialog checkable, allowing users to temporarily disable specific models from the fallback tree without removing them.
- **Model Blacklist & Cooldowns Manager**: Introduced a new management UI under the **Advanced** tab that displays active cooldown remaining times, permits clearing specific or all model failures, and allows configuring the standard failure lockout duration down to **5 minutes** (from the previous 1-hour hard default).
- **Responsive Scrollbar Support**: Added smooth scrollareas wrapping the Advanced, Mobile, and Batch tabs, ensuring the config dialog stays perfectly usable and readable on compact screen sizes and high-DPI displays.

## June 1, 2026 (v2.7.1)
- **Cloze Custom Hint Detection**: Fixed a bug where cloze deletions with custom hints (like `{{c1::Shankari Prasad::case}}` which renders as `[case]` on the front side) failed to be identified as the card's front side. The template's client-side heuristic now robustly detects all active cloze deletions (both standard `[...]` and custom bracketed hints like `[case]` or `[year]`) on the front side of cards.

## May 31, 2026 (v2.7.0)
- **Configurable N-Card Pregeneration Buffer**: Implemented an upcoming review queue peeking engine that maintains a configurable buffer of pregenerated hints (up to `N` cards, defaulting to `3`) in the background. Added a visual spinner in the General configuration tab to easily customize your pregeneration buffer size to prevent lagging during rapid reviews.

## May 31, 2026 (v2.6.3)
- **Interactive Ko-fi Support Widget**: Restored the beautiful interactive script-based Ko-fi widget in the "Support Authors" tab via an embedded `AnkiWebView`, allowing users to directly support the addon with a native experience.
- **Cloze Answer-Side Detection Heuristic**: Fixed a bug where correct options failed to highlight and hints remained collapsed on the back/answer side of Cloze deletion cards on mobile (AnkiDroid/AnkiMobile) or when the Python addon is not running. Implemented a robust, client-side HTML heuristic that identifies the answer side when all `.cloze` elements have been revealed (i.e., none of them contain the `[...]` placeholder).

## May 30, 2026 (v2.6.2)
- **Compact Dynamic Sizing**: Scaled option and hint lists down to 80% (`0.8em`) of the native card font size to ensure compact, perfectly proportioned, and responsive layout across all templates.
- **AnkiDroid Cloze Ordinal Sync**: Fixed mobile synced reviewer always showing `c1` data on AnkiDroid/AnkiMobile. Correctly extracts active cloze index (`card1`, `card2`, etc.) directly from `document.body` classes when the Python backend is absent.

## May 29, 2026 (v2.6.1)
- **Batch Startup-Pause State**: Interrupted batch queues will now automatically restore upon Anki startup in a **PAUSED** state, waiting for you to explicitly resume them instead of auto-starting immediately.

## May 28, 2026 (v2.6.0)
- **Auto-Resume Interrupted Queues**: Added state persistence for the local sequential batch generation queue. If Anki is closed or terminated while a queue is actively running, it will automatically resume generating upon Anki startup.
- **Clean Browser Columns & Sort Fields**: Registered a new Anki browser column format hook (`browser_did_fetch_row`) and enhanced the HTML/JSON cleaner to strip tag-stripped JSON blocks. This prevents raw JSON strings from displaying in the Browser's "Sort Field" column or other columns.

## May 25, 2026 (v2.5.3)
- **Eliminated Prompt Pollution**: Fixed a critical bug where existing AI-Hints JSON data was being sent back to the LLM as part of the card text. The cleaner now aggressively strips all previous hint/option data before generation, ensuring the AI only focuses on the actual card content.
- **Anti-Synthetic Distractor Logic**: Updated the system prompt with a strict "Real-World Accuracy" constraint. This prevents the AI from creating "made-up" distractors by simply swapping words (e.g., turning "Concurrent List" into "Integrated List") and forces it to use real, existing concepts from the same domain instead.
- **Improved Cloze Context**: Replaced active cloze answers with a `[...]` placeholder on the front side. This prevents the AI from seeing the correct answer in the question context, drastically improving option quality for secondary clozes (like `c2`).
- **Enhanced AI Transparency**: Updated logs to display the full, un-truncated "Front" and "Back" payloads sent to the AI, making it easier to audit prompt quality.
- **Robust Model Detection**: Improved detection of cloze note types by checking Anki's internal model type flags.

## May 25, 2026 (v2.5.2)
- **AnkiDroid Option Randomization Fix**: Added a dynamic `hashCode` content resolver to ensure every card reviewed on AnkiDroid gets a unique state key and random shuffling seed, resolving the stuck-option bug.
- **Enhanced Distractor Guidelines**: Updated the default system prompt with the **Temporal & Field Parallelism Trap** (for Nobel Prizes and historical events) and the **Prevent Overlapping Clues** constraint to avoid similar options that give away answers.

## May 24, 2026 (v2.5.1)
- **Anki Terminator Integration**: Added monkey-patch support for the "Anki Terminator" add-on. Intercepts card text field access and sanitizes AI-Hints hidden divs and container markup, ensuring seamless co-existence without UI disruption.
- **Strict Field Extraction**: Restructured card content parsing to strictly target standard Front/Back fields for standard/reversed card extraction, ensuring auxiliary/storage fields are not sent to the LLM.
- **Robust Template Detection**: Refactored front field detection to robustly match field references containing spaces or filters (like `{{type:Back}}` or `{{ Back }}`).

## May 23, 2026 (v2.5.0)
- **Flicker-Free UI**: Re-engineered the template rendering engine to be fully idempotent. Eliminated the annoying "flash" and intermittent click failures by preventing redundant DOM reconstructions during card transitions and state updates.
- **Enhanced Cloze Support**: Added support for `c2`/`c3` keyed hints, allowing independent AI hints for different cloze deletions on the same note.
- **Improved UI Layout**: Refactored the configuration dialog's "General" tab to prevent layout squishing and improved the visual polish of the reviewer buttons with smoother transitions and animations.
- **PyQt6 Compatibility**: Updated internal dialog execution calls for better compatibility with modern Anki versions.
- **Reversed Template Fix**: Corrected front/back detection for "Basic (and reversed card)" templates to ensure hints are generated for the correct face.
- **Unicode Stability**: Fixed potential `UnicodeDecodeError` when reading addon metadata.
- **Smart Render Guards**: Added protection against re-rendering while editing fields and implemented more aggressive stale data pruning.

## May 21, 2026 (v2.3.5)
- **Log Viewer Decoding Fix**: Added `errors="replace"` to the log file reading logic in the configuration dialog to prevent Anki from raising a `UnicodeDecodeError` when logs contain invalid UTF-8/ANSI characters.
- **Crash Fix**: Resolved a `TypeError` crash in `CardParser.__init__` caused by obsolete configuration arguments (`target_fields` and `note_type_fields`).
- **Robust Note Updates**: Updated note saving logic to use `mw.col.update_note(note)` instead of the deprecated `note.flush()` method to ensure database consistency.
- **Enhanced Data Extraction**: Implemented robust field-scanning extraction methods for the migration utility.
- **First Field Storage Priority**: Forced AI hints storage to the first field of all cards (improving front-side card rendering compatibility).
- **Data Migration Tool**: Added a dedicated migration utility in the config dialog to scan, clean, and move all existing AI hints to the first fields of notes safely with progress and stop/resume controls.
- **Card Shuffling Fix**: Ensured the correct answer option is tracked through the shuffle logic.
- **Reviewer Refresh Races**: Resolved races in reviewer AI hints refresh logic.
- **Data Ghosting Resolution**: Restored multi-block rendering to completely resolve Web-review card data ghosting.

## May 19, 2026 (v2.3.3)
- **Optimized Startup**: Delayed heavy initialization of the Antigravity Proxy and Mobile Sync to prevent resource contention and potential crashes during Anki startup.
- **Resource Efficiency**: Replaced the heavy `AnkiWebView` used for the Ko-fi widget with a native `QPushButton` to reduce memory overhead and improve UI responsiveness.
- **Stable Update Notifications**: Added a delay to automatic support dialog popups after updates and fixed the tab index to correctly open the "Support Authors" tab.
- **Cross-Platform Keyboard Shortcuts**: Implemented review screen keyboard shortcuts for both Desktop (native python hook) and Mobile/Standalone (JavaScript keydown listener).
- **Customizable Default Mappings**: Swapped default toggle mappings so `Alt+2` toggles hints and `Alt+3` toggles options.

## May 18, 2026 (v2.3.2)
- **Offline Template Resolution**: Corrected a major bug where template installers injected prompt fields instead of storage fields, enabling full offline card reviewer button rendering.
- **Propagation & Tap Delay Prevention**: Restructured `template.js` reviewer buttons to block event propagation (`e.stopPropagation()` / `e.preventDefault()`), eliminating click delays and double-clicking issues.
- **Python 3.14 exit-crash prevention**: Cleaned timers and shutdown daemon in `profile_will_close` hook to stop PyQt6/sip crash.
- **Self-Healing Daemon Startup**: Automatically kills previous session's zombie proxy process on start to release Port 3000 conflicts.
- **Polished Card UI**: Hidden 'Clear' buttons offline/mobile, and unconditionally hidden duplicate static HTML blocks to ensure styling parity.
- **Critical Stability Fix**: Implemented a singleton guard in the UI script to prevent multiple instances from running simultaneously, resolving reported crashes in Anki's web engine (SIGABRT).
- **Reduced Rendering Overhead**: Removed redundant re-render triggers in the backend to improve performance and reduce UI flickering.
- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Smart Auto-Updates**: Once you click "One-Click Install", the addon automatically keeps your mobile script and templates up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Robust Clearing**: Re-engineered the "Clear" logic to be HTML-aware, aggressively removing redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Improved Navigation**: Added separate "Save", "Save & Close", and "Cancel" buttons to the configuration dialog.
- **Performance**: Optimized rendering and state management to eliminate "ghost data" and flickering during card transitions.

## May 13, 2026 (v2.2.0)
- **Improved Pre-generation Strategy**: Implemented smarter queue-peeking for Anki v3 scheduler.
- **Robust Network Monitoring**: Added background network status monitor.
- **Global Emergency Stop**: Added instant-kill signal for all AI generations.
- **Optimized Provider Failover**: Enhanced 404/Timeout recovery.
- **Missing Cloze Handling**: Graceful detection and skipping for cards with missing clozes.

## May 12, 2026 (v2.1.0)
- **Persistent Model Blacklisting**: Model failures, rate limits, and quota exhaustion states now persist across Anki restarts via a local `blacklist.json` file.
- **Enhanced Fallback UI**: Added a dedicated **[Fallbacks]** button for every AI provider, a new priority-manager dialog to manually reorder fallback models, and [Test] buttons inside the fallback selector.
- **Improved Failover Logic**: Removed the "Trying anyway" bypass to strictly skip blacklisted models, allowing faster failover to working providers.
- **Robust Rate-Limit Recovery**: Blacklist entries are now automatically cleared if a model succeeds during a manual test.
- **Clean Packaging**: Build exclusions ensure local cache files (`blacklist.json`, `batch_state.json`, `antigravity-accounts.json`) are never bundled into the distributed package.

## May 12, 2026 (v2.0.0)
- **Instant-Open Config UI**: Implemented lazy-loading for note types and fields, cutting configuration window opening time from seconds to milliseconds.
- **Optimized Anki Startup**: Background tasks (proxy daemon startup, log clearing) are now deferred until after the profile is loaded.
- **Interactive Model Testing**: Added [Test] buttons next to every AI provider to verify API keys, connectivity, and generation quality before saving.
- **Live Proxy Status Indicator**: Added a real-time, color-coded status tracker (**● Running** / **○ Stopped**) for the Antigravity Proxy daemon in the configuration tab.
- **Intelligent Dropdown Synchronization**: The "Active AI Provider" and per-model dropdowns now strictly follow custom priority order and the intelligence-ranked fallback hierarchy.
- **Python 3.14 Compatibility**: Fixed a startup crash caused by legacy hook names in the latest Python/Anki builds.
- **Proxy Manager Stability**: Resolved an `UnboundLocalError` that could prevent the Antigravity daemon from starting on certain platforms.

## May 9, 2026 (v1.3.1)
- **Packaging Optimization**: Optimized the distributed package size and cleaned up vendored `json_repair` files.

## May 9, 2026 (v1.3.0)
- **json_repair Integration**: Integrated the `json_repair` library for robust AI response parsing, along with a robust AI hallucination sanitizer and front-side detection fixes.

## May 9, 2026 (v1.2.1)
- **AI Hallucination Sanitizer**: Added robust hallucination sanitization, prefix removal, and front-side detection fixes.

## May 9, 2026 (v1.2.0)
- **Front-Side Detection Fix**: Corrected front-side detection and improved the UI.

## May 9, 2026 (v1.1.4)
- **Stability, Custom Undo Labels & FSRS Compatibility**: Improved overall stability, added custom undo labels, and ensured compatibility with FSRS schedulers.

## May 8, 2026 (v1.1.3)
- **Reviewer Undo Fix**: Added safe Anki checkpoints for the **Generate** and **Clear** actions so background note database modifications register in Anki's undo history (Ctrl+Z no longer kicks you back to the deck overview).
- **Restored Card-Refreshing Logic**: Restored the original, highly stable card-refreshing logic via standard `getCard` re-assignments.

## May 8, 2026 (v1.1.2)
- **Multi-Cloze Support**: Hints and options for each cloze deletion are now stored independently using `c1`, `c2` keys in a single unified JSON block, and the reviewer dynamically selects the data for the active cloze.
- **Math Rendering Improvements**: Fixed dangling/broken LaTeX delimiters (auto-corrected to `\(...\)`), improved math wrapping for `\mathbf`/`\text{}` expressions, and stricter deduplication of mathematically identical options.
- **Review UX**: Hints and options no longer auto-reveal on return visits; buttons must be pressed to show them each time. Fixed a JS `SyntaxError` that could prevent the add-on from appearing on the review screen.

## May 8, 2026 (v1.1.0)
- **Standardized LaTeX Generation**: Standardized math output using `$` delimiters and improved MCQ reliability.

## May 8, 2026 (v1.0.6)
- **Multi-Cloze Support**: Added specialized handling for cards containing multiple cloze deletions with the same ID.
- **Stability Improvements**: Fixed an issue where hints would "disappear" after pressing "Show Answer" due to stale card rendering.
- **Enhanced LaTeX Fixer**: Improved the `ai-latex-fixer` library to handle nested delimiters and better standardize multi-part math strings.
- **Aggressive Hiding**: Ensured hints and options stay strictly hidden on existing cards until manually revealed or just generated.

## May 7, 2026 (v1.0.5)
- **Expert SRS Mode**: Upgraded the AI to follow Dr. Wozniak's 20 Rules of Formulating Knowledge, specializing in the Minimum Information Principle and concise hint generation.

## May 7, 2026 (v1.0.4)
- **Enhanced Logging**: Added model names to logs, a log search filter, and structured changelog documentation.

## May 7, 2026 (v1.0.3)
- **Dynamic Models & Custom Priority**: Added dynamic model fetching from provider APIs, customizable fallback priority, and improved LaTeX output cleaning.

## May 7, 2026 (v1.0.2)
- **MathJax Rendering**: Updated MathJax delimiter instructions and hardened AI hint rendering.
