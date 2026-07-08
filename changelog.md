# Changelog

All notable changes to the AI-Hints Anki Add-on will be documented in this file.

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

## June 4, 2026 (v3.0.1)
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

## May 23, 2026
- **Flicker-Free UI**: Re-engineered the template rendering engine to be fully idempotent. Eliminated the annoying "flash" and intermittent click failures by preventing redundant DOM reconstructions during card transitions and state updates.
- **Enhanced Cloze Support**: Added support for `c2`/`c3` keyed hints, allowing independent AI hints for different cloze deletions on the same note.
- **Improved UI Layout**: Refactored the configuration dialog's "General" tab to prevent layout squishing and improved the visual polish of the reviewer buttons with smoother transitions and animations.
- **PyQt6 Compatibility**: Updated internal dialog execution calls for better compatibility with modern Anki versions.
- **Reversed Template Fix**: Corrected front/back detection for "Basic (and reversed card)" templates to ensure hints are generated for the correct face.
- **Unicode Stability**: Fixed potential `UnicodeDecodeError` when reading addon metadata.
- **Smart Render Guards**: Added protection against re-rendering while editing fields and implemented more aggressive stale data pruning.

## May 21, 2026
- **Log Viewer Decoding Fix**: Added `errors="replace"` to the log file reading logic in the configuration dialog to prevent Anki from raising a `UnicodeDecodeError` when logs contain invalid UTF-8/ANSI characters.
- **Crash Fix**: Resolved a `TypeError` crash in `CardParser.__init__` caused by obsolete configuration arguments (`target_fields` and `note_type_fields`).
- **Robust Note Updates**: Updated note saving logic to use `mw.col.update_note(note)` instead of the deprecated `note.flush()` method to ensure database consistency.
- **Enhanced Data Extraction**: Implemented robust field-scanning extraction methods for the migration utility.
- **First Field Storage Priority**: Forced AI hints storage to the first field of all cards (improving front-side card rendering compatibility).
- **Data Migration Tool**: Added a dedicated migration utility in the config dialog to scan, clean, and move all existing AI hints to the first fields of notes safely with progress and stop/resume controls.
- **Card Shuffling Fix**: Ensured the correct answer option is tracked through the shuffle logic.
- **Reviewer Refresh Races**: Resolved races in reviewer AI hints refresh logic.
- **Data Ghosting Resolution**: Restored multi-block rendering to completely resolve Web-review card data ghosting.

## May 19, 2026
- **Optimized Startup**: Delayed heavy initialization of the Antigravity Proxy and Mobile Sync to prevent resource contention and potential crashes during Anki startup.
- **Resource Efficiency**: Replaced the heavy `AnkiWebView` used for the Ko-fi widget with a native `QPushButton` to reduce memory overhead and improve UI responsiveness.
- **Stable Update Notifications**: Added a delay to automatic support dialog popups after updates and fixed the tab index to correctly open the "Support Authors" tab.
- **Cross-Platform Keyboard Shortcuts**: Implemented review screen keyboard shortcuts for both Desktop (native python hook) and Mobile/Standalone (JavaScript keydown listener).
- **Customizable Default Mappings**: Swapped default toggle mappings so `Alt+2` toggles hints and `Alt+3` toggles options.

## May 18, 2026
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

## May 13, 2026
- **Improved Pre-generation Strategy**: Implemented smarter queue-peeking for Anki v3 scheduler.
- **Robust Network Monitoring**: Added background network status monitor.
- **Global Emergency Stop**: Added instant-kill signal for all AI generations.
- **Optimized Provider Failover**: Enhanced 404/Timeout recovery.
- **Missing Cloze Handling**: Graceful detection and skipping for cards with missing clozes.
