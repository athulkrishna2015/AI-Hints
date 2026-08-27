# Configuration Reference — All Keys

This is the complete reference for every configuration key AI-Hints reads. Keys are stored in `addon/config.json` (the factory defaults) and saved in your Anki profile. Values not present in the dialog can be edited via the **Advanced → Show Raw JSON Editor**.

> Most keys map directly to a control in the [Configuration](configuration.md) tabs. This reference documents the raw key, its default, and its purpose. Defaults shown are from the shipped `config.json`.

## Top-Level Keys

### Core / Provider

| Key | Default | Purpose |
|-----|---------|---------|
| `ai_provider` | (auto) | The primary provider for hint generation, auto-derived from the first usable entry in the fallback priority list: local endpoints and custom providers (URL-based) need no API key, built-in providers need one configured. |
| `api_keys` | `{}` | Map of `provider -> key(s)`. Supports multiple named keys per provider. |
| `models` | (see config) | Map of `provider -> active model name`. |
| `model_fallbacks` | (see config) | Map of `provider -> ordered list of fallback models`. |
| `provider_priority` | (see config) | Ordered list of providers by priority. |
| `disabled_providers` | `[]` | Providers disabled from fallback. |
| `disabled_fallback_models` | `{}` | Per-provider models excluded from fallback. |
| `disabled_global_model_priority` | `[]` | Models unchecked in the Advanced Global Fallback dialog. Separate from per-provider disabled fallback models. |
| `custom_providers` | `{}` | Map of custom OpenAI-compatible endpoint configs. |

Each custom provider entry is an object with the following keys:

| Key | Purpose |
|-----|---------|
| `url` | Endpoint base URL (auto-appended `/chat/completions`). Required for the provider to be usable. |
| `models_url` | Optional separate URL for model discovery (defaults to `url` + `/models`). |
| `api_key` | Optional API key (not required — some providers are keyless). |
| `model` | Default model name. Used only as a last resort; the first **enabled** fallback model is authoritative. |
| `model_fallbacks` | Ordered list of fallback models. |
| `headers` | `{}` | Extra request headers merged over the defaults (`Content-Type`, `Accept`, `Authorization: Bearer <api_key>`). |
| `body_params` | `{}` | Extra JSON fields merged into the request body alongside `model` and `messages` (e.g. `{"stream": false}`, `{"web_search_options": {}}`, `{"think": "low"}`). |

Example:

```json
{
  "custom_providers": {
    "orca": {
      "url": "https://api.example.com/v1",
      "models_url": "https://api.example.com/v1/models",
      "api_key": "sk-...",
      "model": "orcarouter/free",
      "headers": {"X-Custom-Host": "prod"},
      "body_params": {"stream": false, "web_search_options": {}}
    }
  }
}
```

> The `headers` map must contain JSON-compatible string values (nested objects are not supported); `body_params` may contain nested objects/arrays.
| `use_global_model_priority` | `false` | Use the global flat priority list instead of per-provider fallbacks. |
| `global_model_priority` | `[]` | The global cross-provider model priority list. |

### Model Runtime

| Key | Default | Purpose |
|-----|---------|---------|
| `thinking_levels` | `{}` | Per-model thinking level (`off`/`low`/`medium`/`high`). |
| `model_timeouts` | `{}` | Per-model request timeout overrides (seconds). |
| `provider_timeouts` | `{}` | Per-provider request timeout (0 = use global). |
| `request_timeout` | `60` | Global active-review request timeout (seconds). |
| `pregen_request_timeout` | `120` | Pre-generation request timeout (seconds). |

**Timeout overrides (`model_timeouts` / `provider_timeouts`)** apply to **every** generation flow — explicit review, pregen, and batch — but only as an *extension*: a custom value greater than the flow's base budget wins; a smaller one never shortens it. So unattended budgets keep their headroom while genuinely slow models can be granted more everywhere.| `model_cooldown_minutes` | `10` | Failure lockout duration (minutes). |
| `model_blacklist_data` | `{}` | Internal blacklist/cooldown state (provider-model-key combos). |

### Generation

| Key | Default | Purpose |
|-----|---------|---------|
| `generate_hints_enabled` | `true` | Master switch for hint generation everywhere. |
| `generate_options_enabled` | `true` | Master switch for MCQ/options generation. |
| `options_count` | `4` | Number of MCQ options generated per card. |
| `system_prompt` | (see config) | The core system prompt (not editable from dialog). |
| `additional_system_instructions` | `""` | User text appended to the core prompt. |
| `fix_latex` | `false` | Auto-repair common AI LaTeX errors. |
| `answer_display_position` | `between` | `between` or `bottom` — where AI data renders on the answer side. |

### Auto-Show

| Key | Default | Purpose |
|-----|---------|---------|
| `auto_show_hints` | `true` | Auto-show hints on card load (front). |
| `auto_show_options` | `true` | Auto-show options on card load (front). |
| `auto_show_hints_answer` | `true` | Auto-show hints on the answer side. |
| `auto_show_options_answer` | `true` | Auto-show options on the answer side. |
| `options_before_hints` | `true` | Render the options section above the hints section (default). Set to `false` for hints first, then options. Also reorders toggle buttons. |
| `linger_on_timeout` | `true` | Keep timed-out requests alive in a background thread while fallback continues; use the slow result if it arrives first. |
| `timeout_linger_seconds` | `0` | Extended deadline (seconds) for lingering background attempts. `0` = auto: 3x request timeout, clamped to 180–900s. |
| `linger_race_policy` | `priority` | Who wins when a lower-priority candidate succeeds while a higher-priority lingering attempt is still running. `priority`: wait out the lingered attempt's deadline and prefer its result (usually the smarter model; the card button shows an amber "Waiting for higher-priority model…" state). `first`: first usable result wins immediately. |
| `batch_request_timeout` | `120` | Per-request base timeout (seconds) for background batch-generation workers. Configurable in **Advanced tab → Batch Timeout (seconds)**. Per-model / per-provider overrides still apply, but only when greater than this value (extend-only). |
| `manual_show_hints` | `true` | Auto-show hints after manual generation. |
| `manual_show_options` | `false` | Auto-show options after manual generation. |

### Auto-Regeneration

| Key | Default | Purpose |
|-----|---------|---------|
| `auto_generate_new` | `false` | Master switch for automatic generation. |
| `auto_regenerate_all` | `false` | Always overwrite existing data. |
| `auto_regenerate_if_old_version` | `false` | Regenerate if version is old. |
| `auto_regenerate_min_version` | `""` | The version threshold (e.g. `1.4.2`). |
| `auto_regenerate_if_old_time` | `false` | Regenerate if generated before a date. |
| `auto_regenerate_min_time` | `""` | The date threshold (`YYYY-MM-DD`). |
| `auto_regenerate_if_modified` | `false` | Regenerate if the note was modified after generation. |

### Pre-generation

| Key | Default | Purpose |
|-----|---------|---------|
| `pre_generate_next` | `true` | Pre-generate upcoming cards in the background. |
| `pre_generate_count` | `3` | Pre-generation buffer size (1–10). |

### Auto-Rating

| Key | Default | Purpose |
|-----|---------|---------|
| `rate_good_on_correct` | `false` | Auto-rate "Good" on correct option selection. |
| `rate_again_on_wrong` | `false` | Auto-rate "Again" on wrong option selection. |
| `rate_good_delay_ms` | `0` | Delay before "Good" (milliseconds). |
| `rate_again_delay_ms` | `1000` | Delay before "Again" (milliseconds). |

### Note Tagging

| Key | Default | Purpose |
|-----|---------|---------|
| `tag_hinted_notes` | `true` | Tag notes when hints are generated. |
| `tag_skipped_notes` | `true` | Tag notes when AI is skipped. |
| `hint_tag` | `ai-hints` | The tag for hinted notes. |
| `skip_tag` | `ai-hints::skipped` | The tag for skipped notes. |

### Button Visibility

| Key | Default | Purpose |
|-----|---------|---------|
| `show_hints_button` | `true` | Show the collapsible Hints container. |
| `show_options_button` | `true` | Show the clickable Options container. |
| `show_on_card` | `true` | Embed generation controls inline on the card. |
| `show_in_bottom_bar` | `false` | (Legacy) Show controls in the bottom bar. |

### Batch

| Key | Default | Purpose |
|-----|---------|---------|
| `batch_limit` | `1000` | Max cards per batch. |
| `multithread_providers` | `false` | Concurrent multi-provider generation. |
| `batch_full_scan` | `false` | Force full scan (ignore incremental cursor). |
| `deck_last_scan_nid` | `{}` | Internal per-deck incremental scan cursor. |

### Fields / Parsing

| Key | Default | Purpose |
|-----|---------|---------|
| `target_fields` | `["Extras","Back","Text","Extra"]` | Candidate fields scanned for card content. |
| `note_type_fields` | (see config) | Map of note type -> fields used. |

### Maintenance

| Key | Default | Purpose |
|-----|---------|---------|
| `maint_only_modified` | `true` | Only scan notes modified since last clean scan. |
| `last_orphans_check_time` | `""` | Internal timestamp for orphan-scan cursor. |

### Mobile

| Key | Default | Purpose |
|-----|---------|---------|
| `mobile_use_emojis` | `false` | Use emoji labels instead of text on mobile. |
| `mobile_show_extra_buttons` | `false` | Show the 🔄 Refresh extra button on mobile. |
| `mobile_setup_completed` | `false` | Whether mobile templates were installed. |

### Shortcuts

| Key | Default | Purpose |
|-----|---------|---------|
| `shortcuts` | `{}` | Shortcut map (see below). |

`shortcuts` sub-keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `modifier` | `alt` | Modifier for primary shortcuts. |
| `generate` | `1` | Generate / Regenerate. |
| `toggle-options` | `3` | Toggle options. |
| `toggle-hints` | `2` | Toggle hints. |
| `clear` | `4` | Clear stored hints. |
| `refresh` | `5` | Refresh card data. |
| `show-json` | `6` | Show JSON debug panel. |
| `select-options-modifier` | `none` | Modifier for MCQ selection. |
| `select-options-keys` | `1-9` | Keys to select options. |

### Visual / Logging

| Key | Default | Purpose |
|-----|---------|---------|
| `hints_font_size` | `""` | Font size for hints/options (empty = inherit). |
| `auto_clear_logs` | `true` | Clear the log file every Anki start. |
| `debug_logging` | `false` | Enable verbose DEBUG logging. |

### Internal / Version

| Key | Default | Purpose |
|-----|---------|---------|
| `config_version` | `3` | Config schema version (for migration). |
| `last_active_tab` | `0` | Last selected config tab (restored on reopen). |
| `supporter_opt_out` | `false` | Hide the Support tab auto-open (stored in addon meta). |

## Legacy / No-Longer-Shown Keys

These exist in code/config for backward compatibility but are not exposed in the current dialog:

| Key | Notes |
|-----|-------|
| `show_in_popup` | Legacy; no longer shown. |
| `local_providers`, `local_endpoint`, `local_provider_override` | Legacy local-AI UI; not constructed. |
| `antigravity_proxy`, `antigravity_accounts` | The built-in Antigravity provider and its local proxy were fully removed (v7.0.3/v7.0.4). Leftover values in existing `meta.json` files are inert and can be deleted. Use a **Custom Provider** instead if you need a local OpenAI-compatible endpoint. |

---

## Related Documentation

- [Configuration (UI guide)](configuration.md) — the settings window, tab by tab.
- [Data & Storage Format](data-format.md) — the per-card JSON payload.
- [Features](features.md) — overview of everything the add-on does.
