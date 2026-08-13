# Troubleshooting

Common issues and their fixes.

## No Hints / Options Are Generated

1. **Check your API key**: Go to **Config → AI Providers**, select your provider, paste the key, and click **Test**. A ❌ means the key or endpoint is wrong.
2. **Check the master switches**: In **General**, ensure **Generate Hints** and **Generate Options (MCQ)** are enabled. Turning both off disables all generation.
3. **Check auto-show settings**: If data exists but isn't visible, the hints/options may be collapsed. Verify **Auto Show Hints** / **Auto Show Options** (front and answer side) in the General tab.
4. **Check the model**: Some models may refuse or return empty output. Try **Fetch** to update the model list, or switch models.
5. **View the logs**: Open the **Logs** tab and look for errors. Enable **Debug logging** for detailed request/response info.

## The Generate Button Does Nothing / Is Disabled

- If the button is **disabled**, both **Generate Hints** and **Generate Options (MCQ)** are turned off. Re-enable at least one in the General tab.

## Rate Limits / API Errors

AI-Hints automatically falls back to the next provider/model in your priority list. If you're hitting limits:

- Add **more providers** with keys, or add **multiple keys per provider** (rotation).
- Increase the **Default Failure Lockout** or adjust timeouts in the Advanced tab.
- Models that fail repeatedly are temporarily blacklisted; use **Clear All Cooldowns** in Advanced to reset.

## My Manual Edits to Hints / Options Keep Getting Overwritten

- AI-Hints uses an immutable snapshot of the cloze answer to detect stale data, so genuine manual edits are preserved. If a cloze's text was genuinely changed, the data is treated as stale and regenerated (this is intentional).
- Turn off **Force Regenerate Even if Data Exists** (General tab) to prevent overwriting existing data.

## Old Card Style on AnkiDroid (WebView Cache)

Android's WebView aggressively caches `_ai_hints_template.js`. See [Mobile Support → AnkiDroid Cache](mobile-setup.md#-troubleshooting-ankidroid-cache-webview).

## AnkiMobile Shows "undefined" When Tapping an Option

This is fixed in v5.8.2+. Ensure your `_ai_hints_template.js` is up to date and keep a tap zone set to "Show Answer". See [Mobile Support → AnkiMobile](mobile-setup.md#-troubleshooting-ankimobile-undefined-on-tap).

## Batch Generation Skipping Cards

- Re-running a batch uses an **incremental per-deck cursor** and skips cards already generated. Use **Force FULL scan** to re-check everything.
- Notes tagged with the `ai-hints` tag are skipped during fast scans. Use **Tag All Cards with Hints** to tag older cards.

## Where Are the Logs?

- The **Logs** tab shows real-time logs. Enable **Debug logging** and **Clear on startup** toggles there.
- Log files are stored in the addon folder (`ai_hints.log`) with rotation.

## Still Stuck?

- Check the [Changelog](../changelog.md) for known fixes.
- Report an issue: https://github.com/athulkrishna2015/AI-Hints/issues
- Attach your log output (with Debug logging enabled) when reporting.
