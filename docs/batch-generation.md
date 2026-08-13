# Batch Generation

Batch generation lets you generate hints and MCQ options for **entire decks** in the background, so you don't have to generate each card manually during review.

## Getting Started

1. Go to **Tools → Add-ons → AI-Hints → Config → Batch Generation**.
2. Choose a **Source Deck** (autocomplete supported; or select cards in the browser first).
3. Optionally set a **Force Provider** / **Force Model**.
4. Set the **Batch Limit** (max cards, default 1000).
5. Click **🚀 Initiate Queue**.

The batch runs in a dedicated background thread, so you can keep studying while it works.

## Methods

### Sequential Local Queue (Recommended)

Processes cards one-by-one in the background. Supports **all providers** and fallbacks, and is free-tier friendly. This is the default.

### Native Async API (Cloud)

Bundles requests and submits them to a cloud provider's native async API. **Gemini only**, requires **paid billing**, and does **not** support fallbacks. Use it when you need very high throughput.

## Options

- **Force Provider** — override which provider the batch uses (default: `Standard Config (Follows Fallback Matrix)`).
- **Force Model** — override which model to use (default: `System Default`).
- **Skip cards that already have AI Hints generated** — skip cards that already have hints.
- **🧹 Force FULL scan (ignore last-scan cursor)** — re-check every card, bypassing the incremental cursor.
- **Except if Generated Version <** — cards with a version older than this value are still queued.
- **Batch Limit** — max cards to process (1–1,000,000).
- **Concurrent Multi-Provider Generation (Multithreaded)** — generate in parallel using all ready/enabled providers (bypasses the Force Provider/Model overrides).

## Incremental Fast Scan

By default, re-running a batch **only scans notes created since the deck's last full scan**. This cursor is tracked **per deck** (including all sub-decks), so scanning a sub-deck never wrongly skips cards based on another deck's timestamp.

The cursor only advances after a **full, eligible pass** (no cards dropped to the safety limit, and not a browser selection). Use **Force FULL scan** to re-check everything.

## Multiple Queued Jobs

You can add another deck, browser selection, or sidebar group while a batch is already running:

- **Reorder** pending jobs.
- **Cancel** or **clear** pending jobs.
- View the **next 5 pending cards** directly in the Batch tab status with individual **[✖ Discard]** buttons.

## Reliability

- **Continuous checkpointing**: progress is saved to disk (`batch_state.json`) after *every single card*.
- **Accidental quit protection**: close Anki or crash mid-batch and your progress is preserved; queues resume on restart.
- **Concurrent multi-provider**: use multiple providers in parallel with independent fallback queues.
- **Automatic verification passes**: the system automatically retries cards that failed to generate (up to 10 sequential passes).

## Starting from the Deck Browser

You can also start batch generation directly from the **deck browser's cogwheel options menu**.

## Note Tagging & Fast Scan

When note tagging is enabled, generated notes get the `ai-hints` tag and untagged notes are the only ones scanned during batch runs, making repeat scans near-instant. Use **🏷️ Tag All Cards with Hints** in the Advanced tab to tag cards created before tagging was enabled.
