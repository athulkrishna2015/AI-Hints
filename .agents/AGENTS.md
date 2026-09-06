# AGENTS.md

Guidance for AI coding assistants and contributors working on the **AI-Hints** Anki add-on.

## Project Layout

```
addon/                       # The actual add-on payload (zipped into .ankiaddon)
  __init__.py                # Add-on entry point; startup, profile open, config migration
  ai_client.py               # Provider registry, fetch_models, chat calls, model blacklist
  reviewer_hooks.py          # Reviewer integration: card load, generation, bleed guard, undo
  batch_manager.py           # Batch generation, queue state, multi-threaded workers
  card_parser.py             # Card field parsing, depth-aware JSON extractor
  config_ui/                 # Qt settings dialog (main_dialog, tab_*, widgets)
  config_io.py               # merge-safe meta.json writer / reader
  logger.py                  # Rotating file handler, log_context, level filtering
  mobile_sync.py             # One-click mobile template install/sync
  json_repair/ latex_fixer/  # Vendored helpers
  web/template.js            # Injected into the mobile media folder
  VERSION  manifest.json     # Package metadata
docs/                        # User-facing documentation (markdown)
  index.md setup.md          # Start here
  configuration.md features.md mobile-setup.md batch-generation.md
  config-reference.md data-format.md storage.md troubleshooting.md frontend.md
tests/                       # unittest-based regression tests
make_ankiaddon.py            # Build script: bumps VERSION, packages addon/ -> .ankiaddon
bump.py                      # Version bump helper (used by make_ankiaddon.py)
changelog.md                 # User-facing changelog (add a bullet per PR)
AGENTS.md                    # This file
```

## Where things live at runtime

The add-on reads its on-disk config from `addon/meta.json` but **writes log/state files to the Anki profile folder** (e.g. `~/Library/Application Support/Anki2/User 1/` on macOS, `%APPDATA%\Anki2\User 1\` on Windows, `~/.local/share/Anki2/User 1/` on Linux).

Profile-scoped paths (resolved by `resolve_data_file()` / `logger._log_path()`):

| Path | Purpose |
|------|---------|
| `<profile>/ai_hints_bin/ai_hints.log` | **Current session log** — canonical, shared by file handler, Logs tab, and Clear Log. |
| `<profile>/ai_hints_bin/ai_hints.log.1` `.2` `.3` | Three prior sessions (rotated at profile open; `RotatingFileHandler`, `maxBytes=5*1024*1024`, `backupCount=3`). |
| `<profile>/ai_hints_bin/blacklist.json` | Model cooldown / blacklist (atomic writes). |
| `<profile>/ai_hints_bin/pregen_cache.json` | Pre-generation cache (atomic writes). |
| `<profile>/ai_hints_bin/batch_scan_cursors.json` | Per-deck fast-scan cursors. |
| `<profile>/ai_hints_bin/orphan_scan_state.json` | Last orphan-hints scan timestamp. |
| `<profile>/ai_hints_bin/ai_hints_batch_state.json` | Persistent batch queue state. |

These survive addon updates/uninstalls and are **not** checked into the repository. **When debugging or asking the user for logs, always reference `<profile>/ai_hints_bin/ai_hints.log`** (and the `.1`/`.2`/`.3` rotations if needed). Legacy `addon/ai_hints.log*` files are not written anymore and can be deleted.

The full log file / terms reference lives in `docs/storage.md` § 5 — see [storage.md → Log Files](docs/storage.md#5-log-files-ai_hintslog) for the canonical list of files, levels, prefixes, and how to read them.

## Conventions

- **No hardcoded model names.** `DEFAULT_MODELS`, `MODEL_SUGGESTIONS`, `MODEL_FALLBACKS`, `LEGACY_MODEL_REPLACEMENTS` are intentionally empty. Models come from **Fetch Models** or are typed in by the user and persisted in `config["models"]`. Adding a hardcoded entry will rot.
- **No new built-in providers without strong reason.** Prefer **Custom Providers** for any new OpenAI-compatible endpoint. Only add a hardcoded provider if it has genuinely provider-specific behavior (Gemini, Anthropic, Groq are the three current exceptions; OpenRouter is a thin wrapper).
- **Config writes go through the merge-safe writer.** `addonManager.writeConfig` (default, non-pretty path) or `write_pretty_config_preserve_keys`; both are serialized and never let an incoming snapshot drop on-disk keys. Never use a raw `open("addon/meta.json", "w")`.
- **No comments unless asked.** Code style is comment-light; keep it that way.
- **Atomic state writes.** Sidecar files (blacklist, pregen, batch cursors) are written with temp-file + `os.replace`.
- **Per-thread AIClient in batch mode.** Each batch worker thread gets its own `AIClient`; per-request state (`_request_provider`, `_request_model`) is not thread-safe.
- **Respect `is_batch` / `log_context.source`.** Test endpoints and model-blacklisting must skip lingering retries and never poison production cooldowns.

## Testing

```
python3 -m unittest discover -s tests -p "test_*.py"
```

Individual files can also be run directly (`python3 -m unittest tests.test_xxx`). Pytest is not required.

## Release flow

1. Make changes; commit on `master` (this repo does not use branches for releases).
2. Bump + build:
   ```
   python3 make_ankiaddon.py
   ```
   This auto-bumps the patch version in `addon/VERSION` + `addon/manifest.json` and writes `AI_Hints_v<version>_<timestamp>.ankiaddon` in the repo root.
3. Add a `## <version> (YYYY-MM-DD)` entry to `changelog.md` (move anything in `## Unreleased` into the new version section).
4. Commit: `release: AI-Hints vX.Y.Z`.
5. Tag and push:
   ```
   git tag -a vX.Y.Z -m "AI-Hints vX.Y.Z"
   git push origin master
   git push origin vX.Y.Z
   ```
6. Create the GitHub release with the `.ankiaddon` asset:
   ```
   gh release create vX.Y.Z AI_Hints_vX.Y.Z_*.ankiaddon \
     --title "AI-Hints vX.Y.Z" \
     --notes "<release notes>"
   ```

## Common edit pitfalls

- **`fetch_models` returning 0 models silently** → check (a) the custom provider is actually in `config["custom_providers"]` and matches by name (lookups are case-insensitive), (b) the response object's model field is one of `id` / `model_id` / `model` / `name` (the `_model_id()` helper covers all four), (c) the URL/key are correct, (d) the provider isn't actually a `local_providers` entry. See `addon/ai_client.py`.
- **Custom provider `url` ends with `/v1/chat/completions`** → the code auto-rewrites it to `/v1/models` for fetching, but only if `models_url` is empty. If the models endpoint is on a different host (e.g. AIHubMix's `https://aihubmix.com/api/v1/models` vs `https://aihubmix.com/v1/chat/completions`), set `models_url` explicitly.
- **Bleed between cards** → enable `debug_logging`; the `[BLEED]` / `[BLEED-WRITE]` lines expose the card-load source, scope attrs, and target/reviewer card match. See `reviewer_hooks.py`.
- **Read-timeout on the first model of a provider** → the linger pool should re-dispatch in the background; if it isn't, check that `linger_on_timeout` is `true` and that the calling site uses one of the four inner provider loops (Gemini / OpenAI-compatible / Anthropic / custom) which all spawn the lingering retry.
- **meta.json was wiped** → restore from `addon/meta.json.bak`, `.bak.1`, or `.bak.2`. The merge-safe writer in `config_io.py` and the per-write backup prevent this from happening again.

## When you are stuck

- Logs: ask the user to paste `ai_hints.log` (and `.1`/`.2`/`.3` if relevant) from the profile folder.
- Config: `addon/meta.json` (or the most recent `.bak*` if a write just failed).
- Code questions: search the repo first (`grep -r`); the codebase is heavily commented via the test suite in `tests/` and the changelog.
