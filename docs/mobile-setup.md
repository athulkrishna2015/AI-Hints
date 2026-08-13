# Mobile Support

AI-Hints supports **AnkiDroid**, **AnkiMobile (iOS)**, and **AnkiWeb** through a "Zero-Addon" architecture. While the desktop add-on (Python) generates the data, mobile devices only need the generated data plus a lightweight JavaScript renderer — no mobile add-on required.

## ⚡ Getting Started (One-Click Setup)

1. Go to **Tools → Add-ons → AI-Hints → Config → Mobile Support**.
2. Click **One-Click Install: Setup All Note Types**. This inserts the safe injection tags into your templates and copies the modern `_ai_hints_template.js` script to your media folder automatically.
3. **Sync Anki on PC** to upload the fresh template script to AnkiWeb.
4. **Sync AnkiDroid / AnkiMobile** on your phone to download the new files.

## Mobile Display Options

- **Use Emojis instead of text labels (saves space)** — use 💡/🎯 instead of "Show Hints"/"Show Options".
- **Show extra button (Refresh)** — add the 🔄 Refresh button (📝 Show JSON is always available).

## Manual Installation

If you prefer to install manually:

1. In the **Mobile Support** tab, open the **Manual Installation (Alternative)** section.
2. Click **Copy Manual Script to Clipboard**.
3. Open your note type's template editor in Anki and paste the script block into the front and back templates.

## Removing from Mobile

1. Go to the **Mobile Support** tab.
2. Click **Remove from All Note Types**. This strips the injection code from all templates, **automatically deletes** the `_ai_hints_template.js` file from your media folder, and triggers a sync to push the cleanup to AnkiWeb.

## ⚠️ Troubleshooting AnkiDroid Cache (WebView)

If you recently updated the add-on and still see the old card style, duplicate labels (e.g. "AI Hints:"), or missing buttons on **AnkiDroid**, it's because Android's WebView aggressively caches local JavaScript files.

To force AnkiDroid to load the new script:

1. **Sync AnkiDroid** to ensure all files are downloaded.
2. **Force-Close the App**: swipe AnkiDroid away from your phone's **Recent Apps** list. This terminates the persistent WebView session and clears the cache.
3. **Reopen AnkiDroid** and review a card. The clean desktop-style UI will render.

## ⚠️ Troubleshooting AnkiMobile "undefined" on Tap

On **AnkiMobile (iOS)**, tapping an answer option used to blank the card and show the literal text `undefined`.

**Cause:** AnkiMobile has no JavaScript API for showing the answer. Older builds called `pycmd('ans')` / `showAnswer()` when an option was tapped; on iOS that navigates to a blank `undefined` page.

**Fix (built into v5.8.2+):** On iOS the add-on detects the AnkiMobile WebView bridge and skips the JS reveal call entirely — tapping an option only saves your selection and lets AnkiMobile's native **tap-to-reveal** flip the card. Desktop and AnkiDroid keep their platform JS reveal APIs.

> [!IMPORTANT]
> Keep **Review → Tap Zones → When Question Shown → "tap anywhere" (or a zone covering the options) → Show Answer** enabled in AnkiMobile preferences. If you choose a more restrictive zone, tapping an option in the middle won't flip the card.

## ⚠️ AnkiWeb Option Reveal

On **AnkiWeb** (ankiuser.net/study) there is no JS reveal API, so tapping an option now simulates a click on the reviewer's own **Show Answer** button (`#ansarea .btn.btn-primary.btn-lg`), so options flip the card correctly.

> [!TIP]
> **Quick Script Force-Refresh:** Sometimes after an update, to guarantee loading the latest JavaScript template, go to **Mobile Support**, first click **Remove from All Note Types** to clean old assets, then click **One-Click Install: Setup All Note Types** again. Then sync your devices.
