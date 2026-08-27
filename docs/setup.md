# Installation & API Keys

## Requirements

- **Anki** 25.x or newer (Qt 6, PyQt 6, Python 3.10+).
- An account/key for at least one supported AI provider.

## Install from AnkiWeb

The easiest way to install is through AnkiWeb:

1. Open Anki.
2. Go to **Tools → Add-ons → Get Add-ons…**.
3. Paste the code `2119980872` and press **OK**.
4. Restart Anki.

Or install directly: <https://ankiweb.net/shared/info/2119980872>

## Install from GitHub (development)

The repo is `https://github.com/athulkrishna2015/AI-Hints`. The packaged add-on lives in `addon/`, the user docs in `docs/`, and the regression tests in `tests/`. For the full code map, see [Architecture & Code](architecture.md); for runtime files see [Data Storage, Files & State](storage.md).

### 1. Initial Setup (Clone + Submodules)

When cloning for the first time, initialize the `ai-latex-fixer` Git submodule so `addon/latex_fixer/` is populated:

```shell
git clone https://github.com/athulkrishna2015/AI-Hints.git
cd AI-Hints
git submodule update --init
```

### 2. Local Testing (Symlinking)

The fastest way to test changes is to symlink the `addon/` folder directly into your Anki add-ons directory so Anki loads your live code on every restart.

**Linux / macOS:**

```shell
ln -s "$(pwd)/addon" ~/.local/share/Anki2/addons21/ai_hints_dev
```

**Windows (Admin PowerShell):**

```powershell
New-Item -ItemType SymbolicLink -Path "$env:APPDATA\Anki2\addons21\ai_hints_dev" -Target "$pwd\addon"
```

### 3. Reviewer & Mobile Script Sync

If you modify `addon/web/template.js`, sync it to your Anki profile's media folder as `_ai_hints_template.js` for the changes to take effect in the reviewer. The add-on syncs it automatically on startup (delayed), but manual sync is faster during development.

**Linux example:**

```shell
cp addon/web/template.js ~/.local/share/Anki2/default/collection.media/_ai_hints_template.js && echo "Synced successfully"
```

For the runtime globals, data contract, and `pycmd` protocol the script uses, see [Frontend (JavaScript) Reference](frontend.md).

### 4. Vendored Dependencies

AI-Hints vendors third-party libraries and configurations directly in the `addon/` tree to stay self-contained (no `pip install` required for users).

- **`json_repair`** (`addon/json_repair/`) — robust AI response JSON parser.
- **`latex_fixer`** (`addon/latex_fixer/`) — LaTeX/MathJax normalization engine.

To refresh every vendored dependency to its latest GitHub master/main:

```shell
python3 update_deps.py
```

> While `latex_fixer` is initially set up as a Git submodule, `update_deps.py` syncs its core files without managing submodule pointers manually.

## Building

```shell
# Auto-bump patch version and build:
python make_ankiaddon.py

# Set an explicit version:
python make_ankiaddon.py 1.6.1

# Remove older local packages before building:
python make_ankiaddon.py --clean
```

This produces a timestamped file like `AI_Hints_v7.0.5_202608280017.ankiaddon` in the repo root. Existing `.ankiaddon` packages are preserved by default; pass `--clean` to remove them.

**What gets included in the package** (all Python source under `addon/`, `addon/latex_fixer/`, `addon/json_repair/`, `addon/config.json`, `VERSION`, `manifest.json`).

**What is excluded** (`__pycache__/`, `.pyc`, `.md`, `.png`, `meta.json`, `ai_hints.log*`, `tests/`, and anything matched by `.gitignore`).

To bump the version without building:

```shell
python bump.py            # patch
python bump.py minor      # minor
python bump.py major      # major
```

`bump.py` follows `major.minor.patch` semver (e.g. `7.0.4` → `7.0.5`).

## Running Tests

The project includes a regression suite covering core logic, UI behavior, and network integrations.

### 1. Logic Verification (Quick Sanity)

Mocks the Anki / Qt environment. No API keys or internet required.

```shell
python3 -B tests/local_verify.py
```

### 2. Specialized Logic Suites

Targeted unit tests for core internal engines.

```shell
python3 -B tests/test_latex_fixer.py
python3 tests/test_json_repair_integration.py
python3 tests/test_card_parser.py
python3 tests/test_sanitization_regex.py
```

### 3. Lifecycle and Integration

Verifies the orchestration of background processes and UI states.

```shell
python3 tests/test_generation_cycle.py
python3 tests/test_local_ai.py
```

### 4. Live Network Tests

Requires real API keys configured in `addon/config.json` or a local `meta.json`.

```shell
python3 tests/live_test.py
python3 tests/test_raw_local.py
```

### 5. Live AnkiConnect Verification

Requires the **AnkiConnect** add-on (<https://ankiweb.net/shared/info/2055492159>) enabled and Anki running with the plugin listening on `localhost:8765`. These scripts talk to the *live* collection, so run them on a disposable profile / deck:

```shell
python3 tests/test_ankiconnect_live.py
python3 tests/test_live_ankiconnect.py
```

### 6. Full Suite

Run all discovery-compatible tests using Python's standard unittest runner:

```shell
python3 -B -m unittest discover -s tests -p "test_*.py"
```

(The two AnkiConnect scripts above are `__main__`-driven and are not auto-discovered here, so the full suite needs no live Anki running.)

## Release Flow

1. Make changes; commit on `master` (this repo does not use branches for releases).
2. Bump + build:

   ```shell
   python3 make_ankiaddon.py
   ```

   This auto-bumps the patch version in `addon/VERSION` + `addon/manifest.json` and writes `AI_Hints_v<version>_<timestamp>.ankiaddon` in the repo root.
3. Add a `## <version> (YYYY-MM-DD)` entry to `changelog.md` (move anything in `## Unreleased` into the new version section).
4. Commit: `release: AI-Hints vX.Y.Z`.
5. Tag and push:

   ```shell
   git tag -a vX.Y.Z -m "AI-Hints vX.Y.Z"
   git push origin master
   git push origin vX.Y.Z
   ```
6. Create the GitHub release with the `.ankiaddon` asset:

   ```shell
   gh release create vX.Y.Z AI_Hints_vX.Y.Z_*.ankiaddon \
     --title "AI-Hints vX.Y.Z" \
     --notes "<release notes>"
   ```
7. Upload the same `.ankiaddon` to AnkiWeb: <https://ankiweb.net/shared/upload>.

## Get Your API Keys

AI-Hints is provider-agnostic. Get a key from one (or more) of the supported providers:

| Provider | Key page |
|----------|----------|
| **Google Gemini** | https://aistudio.google.com/app/apikey |
| **OpenAI** | https://platform.openai.com/api-keys |
| **Anthropic** | https://console.anthropic.com/ |
| **Groq** | https://console.groq.com/keys |
| **SambaNova** | https://cloud.sambanova.ai/apis |
| **Hugging Face** | https://huggingface.co/settings/tokens |
| **OpenRouter** | https://openrouter.ai/keys |
| **DeepSeek**, **Grok (xAI)**, **NVIDIA**, **Mistral**, **Cerebras** | visit each provider's developer portal |

## Where to Enter Your Keys

1. Open Anki.
2. Go to **Tools → Add-ons → AI-Hints → Config**.
3. Open the **AI Providers** tab.
4. Select a provider, paste your API key into its field, pick a model, and click **Test** to verify connectivity.

### Multiple API Keys per Provider

Each provider key field supports **multiple keys** for automatic rotation and fallback:

- `name:key` — a named key
- `key (name)` — a named key
- Separate multiple keys with commas, semicolons, or newlines.

You can also click the **🔑** button next to a provider to open the **Manage Multiple API Keys** dialog, where keys can be labeled, individually enabled/disabled, and rotated.

### Custom Providers (local / OpenAI-compatible)

You can add any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, AIHubMix, etc.):

1. In the **AI Providers** tab, click **Add** under Custom Providers.
2. Fill in a **Provider Name**, **Endpoint URL**, and optionally an **API Key**.
3. Click **Fetch** to load models, then select one.

Local endpoints without authentication can leave the API key blank.

## Verify Your Setup

After entering a key:

1. Click **Test** on the provider row. A ✅ status means the connection works.
2. Optionally click **Test All** to check every configured provider.
3. Review a card and click the **Generate** button (or use a shortcut) to confirm hints and options appear.

If you run into issues, see [Troubleshooting](troubleshooting.md).
