# Features

AI-Hints is a comprehensive AI study companion for Anki. This page describes everything it does.

## 🧠 Multi-Provider AI Engine

- **Broad provider support**: OpenAI, Anthropic, Gemini, DeepSeek, Grok (xAI), Groq, OpenRouter, Hugging Face, SambaNova, NVIDIA, Mistral, Cerebras, and custom OpenAI-compatible endpoints (Ollama, LM Studio, vLLM).
- **Automated fallbacks**: If a provider fails (rate limit, key exhaustion, network error), the add-on automatically tries the next model/provider in your priority list.
- **API key rotation**: Register multiple keys per provider to prevent exhaustion and spread load.
- **Model cooldowns & blacklist**: Models that fail repeatedly are temporarily blacklisted to prevent lag, with configurable lockout duration.

### Intelligence-Ranked Fallback Hierarchy

Fallback providers are ranked by intelligence and reasoning capability. Default priority:

1. Anthropic (Claude 3.7/3.5 Sonnet)
2. OpenAI (GPT-4o)
3. DeepSeek (Reasoner/V3)
4. Grok (xAI)
5. Gemini (Gemini 2.0 Pro/Flash)
6. OpenRouter (Unified Router)
7. Hugging Face (Serverless DeepSeek-V3 / Llama 3.3)
8. Groq
9. SambaNova
10. NVIDIA
11. Mistral
12. Cerebras
13. Custom Providers (Ollama/LM Studio/Local Endpoints)

You can reorder this list, enable/disable individual providers, or enable the **global flat priority list** for cross-provider model-level control.

## 🎮 Interactive Review UI

### MCQ Options

- Select MCQ options on the front side via **click, touch, or hotkeys `1–9`**.
- **Color-coded results**: green for correct, red for incorrect (the true answer is also highlighted green on the back).
- **Auto-rating**: optionally rate the card automatically (Good on correct, Again on wrong) with configurable delays.
- Options are reshuffled with a fresh random seed on every review retry.

### Hints

- Generated hints render in a collapsible panel during review.
- **Auto-show** configurable for the front and answer sides (each card resets to your defaults on a fresh show).
- **Inline editor**: hold `Ctrl`/`Cmd` and click a hint or option to edit it directly on the card. Edits save on `Enter`, blur, or `Escape`.

### Keyboard Shortcuts

Customizable in the **Shortcuts** tab. Defaults (with the modifier, e.g. `Alt`):

- `Alt+1` — Generate / Regenerate
- `Alt+2` — Toggle hints
- `Alt+3` — Toggle options
- `Alt+4` — Clear stored hints (irrevocable)
- `Alt+5` — Refresh current card data
- `Alt+6` — Show JSON debug panel

On the **front** side, action keys also work **without** the modifier for faster review. MCQ option selection uses bare `1–9` by default.

### Factual Error Alerts

AI-Hints automatically detects factual errors in your notes and flags them with a warning (`⚠️`) and custom highlighting. Warnings can be dismissed inline during review.

### Skip AI Generation

Permanently skip AI generation for individual cards. Skipped cards show an **"AI generation skipped"** message (all buttons on desktop, message-only on mobile) until you generate or clear them. Can also be applied in bulk from the browser.

### LaTeX & Math Support

- Automatically parses and formats LaTeX math formulas.
- Normalizes `$...$`/`$$...$$` delimiters to Anki-standard `\(...\)`/`\[...\]`.
- Optional **Repair AI LaTeX Errors** setting fixes common AI math mistakes.

## ⚡ Batch & Maintenance Tools

- **Queued batch generation**: Queue multiple bulk generation runs for entire decks, processed in the background (optionally with concurrent multi-provider parallelism).
- **Incremental fast scan**: Re-running a batch only scans notes created since the deck's last full scan — tracked per-deck (including sub-decks). A **Force FULL scan** option re-checks everything.
- **Multiple queued jobs**: Add another deck/browser selection while one is running; reorder, cancel, or clear pending jobs.
- **Continuous checkpointing**: Progress saves to disk after every card, surviving crashes and restarts.
- **Non-blocking**: Runs in a dedicated background thread so you can keep studying.

### Auto-Regeneration

Automatically keep hints fresh:

- Regenerate if a card's generated version is older than a threshold.
- Regenerate if a card's generated time is older than a date.
- Regenerate if the note was modified after generation.

### Note Tagging

- Notes are auto-tagged (`ai-hints`) when hints are generated, and untagged when cleared/skipped.
- Skipped notes get a separate tag (`ai-hints::skipped`).
- Tagging enables fast batch scanning.

### Cloze Deletion Support

Fully compatible with cards containing multiple Cloze deletions on a single note, with robust stale-hint detection that preserves your manual edits. See [Data & Storage Format](data-format.md) for how the generated data is stored on your cards.

## 📱 Mobile Support

Run AI-Hints on **AnkiDroid**, **AnkiMobile**, and **AnkiWeb** through a "Zero-Addon" architecture: mobile devices only need the generated data plus a lightweight JavaScript renderer — no Python addon required. See [Mobile Support](mobile-setup.md).

## 🧰 Maintenance Tools (Advanced tab)

- **Migrate AI Data to First Fields** — move AI data into the first field.
- **Convert HTML to Hidden JSON** — convert legacy visible hint boxes to the optimized invisible JSON format.
- **Convert Unicode Escapes** — turn `\uXXXX` escapes into readable text.
- **Clean Orphaned Hints** — remove hint data for clozes that no longer exist.
- **Purge Naked JSON Blocks** — remove raw JSON pasted without the div wrapper.
- **Clear Pregen Cache** — clear the pre-generated disk cache.
- **Tag All Cards with Hints** — tag every note that has saved hint data.
