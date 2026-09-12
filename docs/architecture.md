# Architecture & Code

This page documents the high-level architecture of **AI-Hints** and what each module in `addon/` does. For user-facing configuration see [Configuration](configuration.md) and [Configuration Reference](config-reference.md); for the on-disk format see [Data & Storage Format](data-format.md); for runtime files see [Data Storage, Files & State](storage.md); for the JavaScript bridge see [Frontend (JavaScript) Reference](frontend.md).

## High-Level Architecture

AI-Hints is a single Python package loaded by Anki that combines:

1. **A multi-provider AI client** (`addon/ai_client.py`) that talks to OpenAI-compatible endpoints, Anthropic, Gemini, Groq, OpenRouter and any **Custom Provider** the user adds, with model fallback, lingering-on-timeout, blacklist cooldowns, per-key rotation, and depth-aware JSON repair.
2. **A reviewer integration** (`addon/reviewer_hooks.py`) that hooks the Anki reviewer (front, back, undo/redo, shortcuts, bleed guard), injects the AI-Hints UI via `web/template.js`, and pushes/pulls data through the `pycmd` bridge.
3. **A batch queue** (`addon/batch_manager.py`) that scans decks (with a per-deck incremental cursor) and runs multithreaded generation in the background.
4. **A card parser** (`addon/card_parser.py`) that finds the hidden AI-Hints JSON block in a note, parses the field content (cloze-aware), and is **depth-aware** so legacy raw-HTML payloads cannot corrupt fields.
5. **A Qt configuration dialog** (`addon/config_ui/`) built as a **Python multiple-inheritance mixin stack** — each tab is its own `XxxTabMixin` class, the main `ConfigDialog` inherits them all and shares `self`.
6. **A mobile sync path** (`addon/mobile_sync.py`) that copies the lightweight `web/template.js` into the Anki media folder as `_ai_hints_template.js` so AnkiDroid / AnkiMobile / AnkiWeb can render the data without a local add-on ("Zero-Addon" architecture).
7. **Profile-scoped sidecar files** for the blacklist, pre-generation cache, per-deck batch cursors, orphan-hint scan state, batch state, and rotating log (see [storage.md § 5](storage.md#5-log-files-ai_hintslog) for log details).

Data flow at a glance:

```
   ┌──────────────┐   pycmd ◀──▶ JavaScript  ┌──────────────────┐
   │  Anki UI /   │    bridge      template.js │   Reviewer /     │
   │  Config UI   │  ───────────────────────▶  │   Mobile WebView │
   └──────┬───────┘                            └────────┬─────────┘
          │                                            │
          ▼                                            ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                       addon/ Python                         │
   │  reviewer_hooks ──▶ ai_client ──▶ chat provider (HTTPS)     │
   │        │              │   ▲                                  │
   │        │              ▼   │ fallback / linger / blacklist   │
   │        │           batch_manager ─▶ (multithread)           │
   │        │              │                                     │
   │        ▼              ▼                                     │
   │  card_parser ◀── in-note JSON block                         │
   │                                                             │
   │  config_io ◀──▶ addon/meta.json                             │
   │  logger    ──▶ <profile>/ai_hints_bin/ai_hints.log          │
   │  sidecars  ──▶ <profile>/ai_hints_bin/*.json (atomic)       │
   └─────────────────────────────────────────────────────────────┘
```

## Module Map

### `addon/__init__.py`

- Entry point. Anki imports this once.
- Registers all reviewer / profile / sync hooks.
- Performs the one-time config migration on profile open (`config_version` bumping, sidecar-file migration from the old `addon/` location, `meta.json` startup backup to `meta.json.bak`).
- Calls `rebind_file_logging()` so the rotating file handler points at the **profile-scoped** `ai_hints_bin/ai_hints.log`.

### `addon/ai_client.py`

The heart of the add-on. Owns:

- `PROVIDER_ORDER`, `MODEL_SUGGESTIONS`, `MODEL_FALLBACKS`, `LEGACY_MODEL_REPLACEMENTS` — all **intentionally empty** (models come from Fetch Models or are typed by the user; any pre-shipped list rots fast).
- `FETCHED_DEPRECATED_MODELS` — per-session cache of model ids the provider's own API marked as deprecated.
- `_DEPRECATION_MARKER_KEYS` — the set of field names (`deprecation`, `deprecated`, `is_deprecated`, `expires_at`, `expiresAt`, `expiration`, `expirationTimestamp`) used to detect live deprecation in OpenRouter/Azure/GitHub-style responses.
- `_model_id(item)` — small helper that extracts a model id from a list-models entry by trying `id` → `model_id` → `model` → `name` (covers providers like AIHubMix that don't follow the OpenAI schema).
- `_collect_deprecated_items(items)` — collects the set of model ids marked deprecated by the provider's own API.
- `AIClient` class:
  - Constructor stores `self.config` and the `request_timeout` / `batch_request_timeout` / `pregen_request_timeout` (per-flow base budgets; explicit per-model/per-provider overrides extend but never shrink).
  - `fetch_models(provider)` — single source of truth for **Fetch Models**:
    1. `local` / `local_providers` first → `GET {base_url}/models`.
    2. Custom providers (`config["custom_providers"][name]`) — if `models_url` is set use it as-is, otherwise rewrite a `…/chat/completions` `url` to `…/models`. Custom provider lookups are **case-insensitive**.
    3. Built-in `openrouter` / `gemini` / `groq` and the OpenAI-compatible set (`openai`, `deepseek`, `mistral`, `nvidia`, `sambanova`, `cerebras`, `grok`).
    4. Filters out embeddings / OCR / moderation / TTS / realtime-audio and experimental `labs` models via `_chat_only_models` so the fallback list doesn't accumulate always-failing entries.
  - `_is_provider_ready(provider)` — readiness check; the fallback for custom providers without a saved model is to attempt `fetch_models` and accept the result if non-empty.
  - `_call_*` paths — one per provider family:
    - `_call_anthropic`, `_call_gemini` (and `_call_gemini_batch_generate_content`), `_call_openai_compatible` (for the built-ins), `_call_custom_provider` (for user-added endpoints), and the top-level `generate_hints` / `generate_options` entrypoints.
  - **Linger-on-timeout** — when a read timeout occurs the request is re-dispatched in the background with an extended deadline (`3 × request_timeout`, clamped 180–900s, `timeout_linger_seconds` overrides). All four inner provider loops spawn the lingering retry on **every** model — including the first. Race policy is `priority` (higher-priority late result wins) or `first` (first usable result wins), via `linger_race_policy`.
  - **Blacklist / cooldown** — `_mark_combo_failed` adds a `(provider, model, api_key)` triple to `FAILED_COMBOS_CACHE` with a streak-based delay (`_cooldown_seconds() × streak`) and persists via `blacklist.json`. Model-test runs (`log_context.source == "model_test"`) and offline environments are explicitly skipped so a settings-page test can never poison production cooldowns.
  - **Key rotation** — `_available_api_keys(provider)` returns all keys for the provider; per-model loops filter out only the keys currently on cooldown, so multiple healthy keys keep working.
  - **Transient provider skip** — `_skip_transient_provider_error` treats `429` / `503` as provider-wide outages during normal generation: the provider is added to `_generation_skipped_providers` and parked for `PROVIDER_OUTAGE_COOLDOWN_SECONDS` (60) in the in-memory `PROVIDER_UNAVAILABLE_UNTIL` map, and the outer fallback loop immediately tries the next provider (`_provider_temporarily_unavailable` re-bails until the cooldown lapses). Later generations retry. Gated by `_skip_provider_on_transient_outage`, which is only enabled inside live generation loops — model tests keep per-key rotation for diagnosis and never mark a provider down.
  - **Per-thread client** in batch mode — batch workers construct their own `AIClient`; `_request_provider` / `_request_model` are per-request instance state and must not be shared across threads.
  - **Reasoning-model content recovery** — `_extract_content` and `_parse_generation_result` unwrap a top-level `data` envelope (Cline BYOK) and fall back to `message.reasoning` / `message.reasoning_details[*].text` when `content` is empty, so reasoning models don't get reported as "no parseable hints".

### `addon/reviewer_hooks.py`

The longest file. Owns:

- Reviewer hooks: `on_show_question`, `on_show_answer`, `reviewer_did_show_question`, `answerCard` hooks, undo (`Ctrl+Alt+Z` / `Ctrl+Alt+Shift+Z`), and shortcut wiring.
- **Bleed guard** — `_apply_results_to_card` re-pushes finished payloads to the frontend 400 ms after the redraw via the identity-checked `_push_hint_data_to_frontend`; the data lands exactly once on the right card or no-ops if the user moved on. Gated by the `[BLEED]` / `[BLEED-WRITE]` debug log lines (see [storage.md § 5.3](storage.md#5-log-files-ai_hintslog)).
- **Moved-on generations** — clicking Generate and advancing to the next card before the request finishes no longer throws the result away. The bleed-guard suppresses the UI update only; the payload is saved silently (`update_ui=False`) and the pre-generation buffer is refilled.
- **Pregen refills** — every successful generation (manual or auto) triggers `_trigger_next_pregeneration()`.
- **Stale cloze detection** — `_src` snapshot stored at generation time, compared against the current cloze text; manually-edited hints/options are not mistaken for stale data.
- **Hotmouse compatibility** — suspends the Review Hotmouse add-on while the Alt+click "Generate with a specific model" popup is open.
- **Provider overrides** — `provider_overrides` config lets a per-card (or per-deck) override reroute generation to a specific provider/model.
- **JSON / Parse path** — `find_hints_block` is depth-aware and refuses oversized / deeply nested payloads via `_safe_loads()` (256 KB / 100 levels) before parsing.

### `addon/batch_manager.py`

- Persistent batch queue (`ai_hints_batch_state.json`).
- **Watchdog** — releases a batch pass when a provider thread lingers after all queued cards have been dispatched. Its 45s grace period is measured from the moment a thread becomes the lone survivor (not from pass start), so a normal "waiting for peers" thread is not mislabeled as hung. After release the pass waits a bounded window for still-in-flight requests to land (`_await_workers_settled`), and verification does not requeue cards whose request is still running — preventing duplicate (billed) generations.
- **Multithreaded workers** — `multithread_providers` (default ON) gives each provider worker its own `AIClient`; per-worker `AIClient` is mandatory.
- **Cooldown-provider exit** — when a worker's models are all blacklisted/on cooldown, it exits the pass if a peer is actively `Processing` (redundant idle thread otherwise), and a lone cooldown-stalled provider caps its wait at `batch_request_timeout + 60s` before ceding to the verification pass — a dead key set can't pin the pass open. Providers are re-created each pass, so exiting just shrinks the idle fleet.
- **Per-deck fast-scan cursor** — `deck_last_scan_nid` is a `deck_name -> max note id` cursor advanced only after a full, eligible pass (no cards dropped to the safety limit and not a "Selected Cards" selection). New note ids are resolved in Python and queried via the valid `nid:1,2,3` comma-list form because Anki's `nid:>` / `nid:1-5` syntax is rejected on 26.x.
- **Linger / rate-limit integration** — uses the same `_mark_combo_failed` rules, but uses `is_batch = True` so the longer `batch_request_timeout` base budget is honored and per-model/per-provider overrides only extend, never shrink.
- **Atomic sidecar writes** — every sidecar is written via temp-file + `os.replace`.

### `addon/card_parser.py`

- Locates the hidden `<div class="ai-hints-json">` block in a note's field.
- **Depth-aware scanner** — replaces non-greedy `.*?</div>` regexes with a stack-based scanner; legacy raw-HTML payloads cannot corrupt fields on update/clear, and unterminated blocks are skipped instead of swallowing the whole field.
- **Stale cloze handling** — keyed `cN` entries whose `{{cN::…}}` tag is missing are purged automatically on save (orphan purge).
- **Cloze isolation** — cloze cards ignore keyed JSON belonging to another cloze ordinal (`c2` card with only `c1` data → no AI data shown).
- **Prefers manual edits** — `_src` is the immutable source of truth; manually edited `correct_answer` / `options` are not treated as stale.

### `addon/config_io.py`

- The merge-safe `meta.json` writer. Two paths:
  - `addonManager.writeConfig` (default, non-pretty) — serialized through a module-level lock; the on-disk config is the baseline, incoming keys win only when explicitly present, and `api_keys` always keeps on-disk values for any key the incoming snapshot leaves empty.
  - `write_pretty_config_preserve_keys` — same merge-safe baseline, pretty-printed; copies the previous `meta.json` to `meta.json.bak` **before every overwrite** (in addition to the startup backup).
- `read_meta_config()` — reads directly from `addon/meta.json` instead of Anki's name-based `getConfig()` so a package-name mismatch can never silently fall back to the default template.
- Every save is logged with `[addonManager(preserve-merge)]` (or `[direct-file(preserve-merge)]`) plus `on_disk_keys`, `written_keys`, `api_keys`, `scan_cursors` counts so any future config-loss event is immediately diagnosable from the log.

### `addon/logger.py`

- Single canonical file handler; the path is resolved via `_log_path()` to `<profile>/ai_hints_bin/ai_hints.log`.
- `rebind_file_logging()` is called from `addon/__init__.py` when the profile opens, so the on-disk file, the Logs tab, and **Clear Log** all share the same path.
- `RotatingFileHandler` with `maxBytes=5*1024*1024`, `backupCount=3` — see [storage.md § 5](storage.md#5-log-files-ai_hintslog) for the full file/level/prefix reference.
- `log_context` — a small context object carrying `source` (`model_test` / batch / pregen / lingering / etc.). The client consults it to skip linger retries, skip blacklist increments, and apply flow-specific timeouts.

### `addon/mobile_sync.py`

- One-click install / remove of `_ai_hints_template.js` into the Anki media folder.
- Waits up to 2 minutes for the sync/profile to become available (so **One-Click Install** right after **Remove from All Cards** doesn't fail with a generic "Failed to sync script file to media folder.").
- Raw `bytes` (not `BytesIO`) to `col.media.write_data`, with a fallback to a plain file write if the media-tracker API rejects or lacks the call.

### `addon/web/template.js`

- The lightweight JavaScript renderer used in the desktop reviewer and on mobile.
- A single unified script; no separate mobile build. Reads runtime globals (theme, cloze ordinal, mobile config), receives data via `pycmd`, and calls back to Python for show-answer, copy, regenerate, skip, and Undo/Redo.
- Documented in detail at [Frontend (JavaScript) Reference](frontend.md).

### `addon/config_ui/`

The settings dialog uses a **Python Multiple-Inheritance Mixin** pattern. Each tab is implemented as a standalone `class XxxTabMixin:` in its own file. The main `ConfigDialog` in `main_dialog.py` inherits from all of them:

```python
class ConfigDialog(QDialog,
                   GeneralTabMixin,
                   ProvidersTabMixin,
                   AdvancedTabMixin,
                   ShortcutsTabMixin,
                   BatchTabMixin,
                   SupportTabMixin,
                   LogTabMixin,
                   MobileTabMixin):
```

This means every mixin method shares the same `self` (including `self.config`, `self.tabs`, all widget refs) with no awkward cross-references or parameter passing. Adding a new tab means:

1. Create `addon/config_ui/tab_xxx.py` with `class XxxTabMixin`.
2. Add it to the inheritance list in `main_dialog.py`.
3. Call `self._create_xxx_tab()` inside `setup_ui()`.

| File | Tab | Purpose |
|------|-----|---------|
| `main_dialog.py` | — | Dialog shell, save/load, timers, tab routing, custom-provider data model (`custom_providers_data`), `on_fetch_models` / `on_add_custom` / `on_edit_custom` handlers, mobile install. |
| `tab_general.py` | General | Master toggles (generate hints/options), system prompt, mathjax format, auto-show defaults (front + back), pre-generation, debug logging, log auto-clear, support links. |
| `tab_providers.py` | AI Providers | API keys, Fetch / Fetch All, per-provider model + fallback list, Local provider, global Advanced Global Fallback Priority. |
| `tab_advanced.py` | Advanced | Per-deck scanning controls, additional system instructions, raw JSON editor, internal state JSON. |
| `tab_shortcuts.py` | Shortcuts | Keyboard shortcut bindings. |
| `tab_batch.py` | Batch | Batch tab — initiate queue, dedicated pause/resume toggle, per-deck source, force-full-scan checkbox, multithread toggle, batch logs, batch status table, per-job progress. |
| `tab_mobile.py` | Mobile | One-click mobile install/remove, mobile config (auto-show, font size, emojis, extra buttons), test card. |
| `tab_support.py` | Support | About / donation links. |
| `tab_logs.py` | Logs | Live log viewer — streamed from `ai_hints.log` in a background thread; Level + Source + free-text filters; matched / total line counts; Clear Log. |
| `widgets.py` | — | `ProviderRowWidget`, `CustomProviderDialog`, `ADDON_PACKAGE` constant (`__name__.split(".")[0]`), and a small `temp_config` helper that injects `custom_providers` / `local_providers` so **Fetch / Test** works for in-memory custom providers before the dialog is saved. |

### Patches (`anki_terminator_patch.py`, `tts_addon_patch.py`)

- Scoped compatibility patches for two specific third-party add-ons (Anki Terminator's webview and PiperTTS bulk-generation). Both install only when the host add-on is detected; otherwise no-op. See `anki_terminator_patch.py` and `tts_addon_patch.py`.

### Vendored / Submodule

- `addon/json_repair/` — robust AI response JSON parser; refreshed via `update_deps.py`.
- `addon/latex_fixer/` — LaTeX/MathJax normalization engine; a Git submodule, but `update_deps.py` syncs its core files without managing submodule pointers manually.
- `addon/Support/` — support / donation assets.

## Fallback & Error Handling Flow

Every generation (explicit review, pregen, batch, and, with `override_model`, the per-card picker) funnels through `AIClient.generate_hints` / `generate_options` → `_generate()`. The same nested tier loop runs the show, so a fix applied here fixes every flow.

### Fallback Tiers

Fallbacks are a three-level onion, innermost first:

1. **Key rotation (model level)** — `_call_*` loops the provider's API keys for the model, skipping only the keys currently on cooldown (`_available_api_keys`). Multiple healthy keys keep working; a failing key is rotated to the next one.
2. **Model fallbacks (provider level)** — `_call_provider` walks the provider's **enabled fallback list** in order (first row = active model, then fallbacks). A blacklisted model is skipped, not tried.
3. **Provider fallbacks (generation level)** — one of two top loops in `_generate()`:
   - **Global flat list** (`use_global_model_priority`): iterates `global_model_priority` — explicit `(provider, model)` rows top-to-bottom — when it is enabled and no `override_provider`/test is active.
   - **Standard per-provider list**: `_candidate_providers(primary_provider)` yields ready providers in priority order (primary first, then fallbacks); for each, `_call_provider` runs its internal tier-2 loop. `only_this_provider` (batch) restricts it to the single primary.

A generation succeeds at the first tier that produces a usable result and walks no further. Aggregation of skip conditions down the layers: each outer loop re-checks `network_failed_providers`, `_generation_skipped_providers` (transient outage), `_provider_temporarily_unavailable` (60s cooldown), disabled providers, disabled models, readiness, and the blacklist before calling anything.

### Linger-on-Timeout

A read timeout never throws the request away — it is kept alive in the background while fallback continues (`_LingerPool`):

- **Trigger** — a timeout at any tier: `HTTPError` `408`/`504`, or a `URLError` / timeout exception matched by `_is_read_timeout_error`, including on the **first** model of a provider. Pure read timeouts are **never blacklisted** (slow ≠ broken).
- **Re-dispatch** — `_LingerPool.spawn(order, provider, model)` re-issues the same request on a daemon thread with the extended deadline `_linger_timeout()`: `timeout_linger_seconds` if set, else `3 ×` the effective request timeout clamped to `[180, 900]`s. The lingering copy clears `model_timeouts` / `provider_timeouts` and pins both `request_timeout` and `pregen_request_timeout` to the linger budget, so a per-model/per-provider override can never cut a lingering attempt short.
- **Hooks** — both top loops (global flat list and per-provider) host the pool in `_active_linger` while walking candidates; the inner per-provider model loops consult it, so a timeout absorbed at tier 1/2 still reaches the pool. Before starting the next candidate the loop offers any finished result via `claim_ready(max_order)` and, on success, prefers a higher-priority attempt still in flight via `wait_for_any(max_order)`.
- **Result selection** — `_claim_best` returns the earliest-`order` (highest-priority) ready result instantly without waiting. `wait_for_any` blocks up to `linger_timeout + 15`s, draining to the earliest finished attempt; it aborts early on Emergency Stop, network loss, or when no attempts remain pending, and polls every `POLL_INTERVAL` (0.5s).
- **Race policy** — `linger_race_policy`: `"priority"` (default) makes a fresh success yield to still-running higher-priority attempts for their extended deadline (amber **"⏳ Waiting for higher-priority model…"**, stoppable); `"first"` settles on the first usable result instead.
- **Rescue** — when every foreground candidate has failed (`last_exception` set **or** `has_pending()` — the pending-only branch matters for single-candidate flows like batch's `only_this_provider`), generation waits out the lingering attempts instead of returning empty: `all candidates failed; using late result from …`.
- **Scope & config** — `linger_on_timeout` (review/pregen, default **on**), `timeout_linger_seconds` (override), `linger_race_policy` (`"priority"` / `"first"`), `batch_linger_on_timeout` (batch, default **off** — a lingering retry could otherwise outlive the job by minutes holding a thread/HTTP client). Disabled for single-model tests (`log_context.source == "model_test"`); `cancel()` discards results on close/stop.

```
generate_hints / generate_options
        │
        ▼
Tier 3: for provider [or (provider,model) row in global list] in priority order:
  ├─ disabled / network-failed / generation-skipped / cooling-down  → SKIP provider
  ├─ provider not ready / model disabled / model blacklisted        → SKIP row
        ▼
Tier 2: for model in provider's enabled fallback list (model_test honor override):
        │
        ▼
Tier 1: for api_key in provider's keys (skip keys on cooldown):
        │
        ├─ HTTP 429 / 503 (normal generation)
        │      → _skip_transient_provider_error(): provider parked 60s
        │        (PROVIDER_UNAVAILABLE_UNTIL) + added to _generation_skipped_providers;
        │        returns empty result → the enclosing tier-3 loop moves to the NEXT
        │        provider/row. The provider is retried on a later generation.
        │        ← no per-key or per-model burning happens
        │
        ├─ HTTP 429 (model_test)
        │      → rotate to next key with rate-limit backoff sleep; on last key re-raise
        │        (diagnosis keeps working; a test NEVER marks the provider down)
        │
        ├─ HTTP 408 / 504 or read timeout (URLError/TIMEOUT/ReadTimeout)
        │      → model_timed_out: request re-dispatched as a background LINGER retry
        │        (3× extended deadline, clamped 180–900s) in _LingerPool; tier 2/3
        │        fallback continues immediately. Pure read timeouts are NEVER
        │        blacklisted (slow ≠ broken).
        │
        ├─ other HTTP error (401 / 400 / 422 / 5xx …)
        │      → _extract_retry_delay() + _mark_combo_failed(): streak-based cooldown
        │        (_cooldown_seconds() × streak, persisted in blacklist.json);
        │        next key → next model → next provider.
        │
        ├─ network unreachable (socket.gaierror / ECONNREFUSED / DNS)
        │      → provider added to network_failed_providers for this run; in batch the
        │        worker parks on 🌐 Offline; in review the outer loop tries the next
        │        provider. Real failures still cool down; a false-positive verdict can
        │        be bypassed via ⚡ Force Start or ignore_network_checks.
        │
        ├─ odd-but-good response shape
        │      → _extract_content() unwraps a top-level data envelope and falls back to
        │        message.reasoning / reasoning_details before giving up; malformed JSON
        │        goes through json_repair. Only then is a reply considered unparseable.
        │
        └─ unparseable response
              → warning + _mark_combo_failed() → next model in the list
```

On **partial success** at any tier, `linger_race_policy: "priority"` (default) may hold the result while a still-running attempt from an EARLIER (higher-priority, usually smarter) row runs out its extended deadline — amber "Waiting for higher-priority model…" — and its late result wins over the later success (`_LingerPool.claim_ready` / `wait_for_any`). Set `"first"` to return the first usable result immediately instead. On **total failure** across all tiers, the generator waits out any lingering attempts (rescue: "all candidates failed; using late result from …") and only then returns empty or re-raises `last_exception`, which the caller surfaces as a UI error / batch retry notice.

| Exception / status | Classification | Handling |
|---|---|---|
| `429 Too Many Requests` / `503 Service Unavailable`, normal generation | Provider-wide transient outage (`TRANSIENT_PROVIDER_ERROR_CODES`) | Skip provider for 60s (`PROVIDER_OUTAGE_COOLDOWN_SECONDS`); move to next provider; retried next generation. No per-key/model burning. |
| `429` during a model test | Rate limited | Rotate keys with backoff sleep (`_rate_limit_backoff_seconds()`); last key re-raises. Never marks provider down. |
| `408 Request Timeout` / `504 Gateway Timeout` / read-timeout exception | Timeout (`_is_read_timeout_error`) | Spawn linger retry (extended deadline) + continue fallback; never blacklisted. |
| Other `HTTPError` (401/400/5xx …) | Hard failure | `_extract_retry_delay()` + `_mark_combo_failed()` → streak-based cooldown; next key/model/provider. |
| Host unreachable (DNS / refused / `gaierror`) | Network failure | `_is_host_unreachable_error()` → provider marked network-failed (batch parks 🌐 Offline); next provider in review; blacklist skipped when offline (see `_is_offline_environment`). |
| Unparseable JSON / empty content | Quality failure | `_extract_content` reasoning recovery → `json_repair` → warning + `_mark_combo_failed()`; next model. |
| `U+FFFD` replacement chars in output | Corrupt output | Detected and discarded; fallback retries next model instead of writing garbage. |

Guards: read timeouts never blacklist; model-test runs can never poison production cooldowns (`log_context.source == "model_test"`); the transient-provider skip is gated on `_skip_provider_on_transient_outage`, which is only enabled inside live generation loops.

## Concurrency Model

- **All Qt UI code runs on the main thread.** Background work uses `threading.Thread` + `mw.taskman.run_on_main()`.
- **No blocking I/O inside `__init__` or tab constructors** — defer with `QTimer.singleShot(0, ...)`.
- **Per-thread `AIClient` in batch mode** — each batch worker constructs its own `AIClient`; per-request state is not thread-safe.
- **Worker threads must not touch the collection** — verification and final-stats passes hop to the main thread via `taskman`.
- **Atomic state writes** — every sidecar (`blacklist.json`, `pregen_cache.json`, `batch_scan_cursors.json`, `orphan_scan_state.json`, `ai_hints_batch_state.json`) is written via temp-file + `os.replace`.

## Cross-Cutting Concerns

- **No hardcoded model names.** See [conventions in AGENTS.md](../AGENTS.md).
- **Respect `is_batch` / `log_context.source`.** Test endpoints and model-blacklisting must skip lingering retries and never poison production cooldowns.
- **merge-safe config writes.** See [storage.md § 1](../docs/storage.md) and `config_io.py`.
- **Profile-scoped storage.** See [storage.md](../docs/storage.md) for the canonical paths and sidecar layout.
- **Bleed diagnostics.** Enable `debug_logging` and grep for `[BLEED]` / `[BLEED-WRITE]` lines.

## Code Standards

- Compatible with **Anki 25.x** (Qt 6, PyQt 6, Python 3.10+).
- All Qt UI code must run on the **main thread**. Background work uses `threading.Thread` + `mw.taskman.run_on_main()`.
- No blocking I/O inside `__init__` or tab constructors — defer with `QTimer.singleShot(0, ...)`.
- Keep `ADDON_PACKAGE` derived from `__name__.split(".")[0]` (not hardcoded) to support both dev and production installs.
- Atomic state writes only — temp file + `os.replace` for every sidecar JSON.
- No comments unless asked.
