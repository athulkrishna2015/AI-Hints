# AI-Hints — Developer Documentation

This repository contains the source code for the **AI-Hints** Anki add-on.

## Quick Links

- **Main Repository**: https://github.com/athulkrishna2015/AI-Hints
- **Install via AnkiWeb**: https://ankiweb.net/shared/info/2119980872
- **Report an Issue**: https://github.com/athulkrishna2015/AI-Hints/issues
- **LaTeX Fixer Submodule**: https://github.com/athulkrishna2015/ai-latex-fixer
- **Releases**: https://github.com/athulkrishna2015/AI-Hints/releases

---

## Project Structure

```
AI-Hints/
├── addon/                        # Core add-on package (this is what Anki loads)
│   ├── __init__.py               # Entry point: registers hooks, starts proxy
│   ├── ai_client.py              # Multi-provider AI client + fallback engine
│   ├── reviewer_hooks.py         # Review-time hint generation and UI injection
│   ├── proxy_manager.py          # Antigravity Proxy lifecycle (start/stop/download)
│   ├── batch_manager.py          # Batch generation queue and async job tracking
│   ├── card_parser.py            # Card content extraction and cloze parsing
│   ├── logger.py                 # Shared logging setup (file + Anki log)
│   ├── config_ui/                # Configuration GUI (multi-file Mixin architecture)
│   │   ├── __init__.py           # Exports ConfigDialog, on_config_dialog, ADDON_PACKAGE
│   │   ├── main_dialog.py        # Core dialog shell: save, load, timers, tab routing
│   │   ├── widgets.py            # ProviderRowWidget, CustomProviderDialog, ADDON_PACKAGE
│   │   ├── tab_general.py        # Tab 1: General settings
│   │   ├── tab_providers.py      # Tab 2: API keys, models, Local, priority
│   │   ├── tab_advanced.py       # Tab 3: System prompt, note type fields, raw JSON
│   │   ├── tab_shortcuts.py      # Tab 4: Keyboard shortcuts
│   │   ├── tab_batch.py          # Tab 5: Batch generation controls
│   │   ├── tab_support.py        # Tab 6: Support / about
│   │   └── tab_logs.py           # Tab 7: Live log viewer
│   ├── bin/                      # Runtime-only assets (not full source)
│   │   ├── config.json           # ✅ Proxy daemon static configuration (tracked in git)
│   │   └── runtime assets        # ❌ OS-specific binaries / tokens are not tracked
│   ├── latex_fixer/              # Git submodule: ai-latex-fixer library
│   ├── json_repair/              # Vendored: json_repair library
│   └── config.json               # Default configuration (factory reset source)
├── tests/
│   ├── local_verify.py           # Logic verification (mocks Anki/Qt, no keys needed)
│   ├── live_test.py              # Live AI generation test (requires meta.json with keys)
│   ├── test_latex_fixer.py       # LaTeX normalization regression suite (9 tests)
│   └── test_json_repair_integration.py
├── scratch/                      # Temporary scripts and diagnostic outputs
│   ├── fetch_all_models.py       # Pulls all available models from active providers
│   └── all_available_models.json # Diagnostic output from fetch_all_models.py
├── make_ankiaddon.py             # Packaging script → produces .ankiaddon file
├── bump.py                       # Version auto-increment script
└── update_deps.py                # Refreshes vendored dependencies (json_repair, latex_fixer, proxy config)
```

---

## Development Workflow

### 1. Initial Setup (Clone + Submodules)

When cloning for the first time, initialize the `ai-latex-fixer` Git submodule:

```shell
git clone https://github.com/athulkrishna2015/AI-Hints.git
cd AI-Hints
git submodule update --init
```

This populates `addon/latex_fixer/` from https://github.com/athulkrishna2015/ai-latex-fixer.

### 2. Local Testing (Symlinking)

The fastest way to test changes is to symlink the `addon/` folder directly into your Anki add-ons directory so Anki loads your live code on every restart.

**Linux/macOS:**
```shell
ln -s "$(pwd)/addon" ~/.local/share/Anki2/addons21/ai_hints_dev
```

**Windows (Admin PowerShell):**
```powershell
New-Item -ItemType SymbolicLink -Path "$env:APPDATA\Anki2\addons21\ai_hints_dev" -Target "$pwd\addon"
```

### 3. Reviewer & Mobile Script Sync

If you modify the frontend logic in `addon/web/template.js`, you must sync it to your Anki profile's media folder as `_ai_hints_template.js` for the changes to take effect in the reviewer. While the add-on syncs this automatically on startup (delayed), manual sync is faster during development.

**Linux Example:**
```shell
cp addon/web/template.js ~/.local/share/Anki2/default/collection.media/_ai_hints_template.js && echo "Synced successfully"
```

### 4. Vendored Dependencies

AI-Hints vendors some third-party libraries and configurations directly in the `addon/` tree to stay self-contained (no pip install required for users).

- **`json_repair`** (`addon/json_repair/`): Robust AI response JSON parser.
- **`latex_fixer`** (`addon/latex_fixer/`): LaTeX/MathJax normalization engine.
To refresh all vendored dependencies to their latest versions from their respective GitHub master/main branches:
```shell
python3 update_deps.py
```

> [!TIP]
> While `latex_fixer` is initially set up as a Git submodule, `update_deps.py` provides a convenient way to sync its core logic files without needing to manage submodule pointers manually.

---

## Config UI Architecture

The configuration dialog uses a **Python Multiple-Inheritance Mixin** pattern. Each tab is implemented as a standalone `class XxxTabMixin:` in its own file. The main `ConfigDialog` in `main_dialog.py` inherits from all of them:

```python
class ConfigDialog(QDialog,
                   GeneralTabMixin,
                   ProvidersTabMixin,
                   AdvancedTabMixin,
                   ShortcutsTabMixin,
                   BatchTabMixin,
                   SupportTabMixin,
                   LogTabMixin):
```

This means every mixin method shares the same `self` (including `self.config`, `self.tabs`, all widget refs) with no awkward cross-references or parameter passing. Adding a new tab means:
1. Create `addon/config_ui/tab_xxx.py` with `class XxxTabMixin`
2. Add it to the inheritance list in `main_dialog.py`
3. Call `self._create_xxx_tab()` inside `setup_ui()`

---

## Building and Versioning

### Build the `.ankiaddon` package

```shell
# Auto-bump patch version and build:
python make_ankiaddon.py

# Set an explicit version:
python make_ankiaddon.py 1.6.1
```

This produces a timestamped file like `AI_Hints_v1.6.1_202605121420.ankiaddon`.

**What gets included in the package:**
- All Python source files under `addon/`
- `addon/bin/config.json` (proxy static config)
- `addon/latex_fixer/` (submodule source)
- `addon/json_repair/` (vendored source)
- `addon/config.json` (default config)

**What is excluded:**
- `__pycache__/`, `.pyc`, `.md`, `.png` files
- `meta.json`, `ai_hints.log`, `tests/`

### Manually bump the version

```shell
python bump.py
```

Follows `major.minor.patch` semver (e.g., `1.6.0` → `1.6.1`).

---

## Running Tests

The project includes a comprehensive test suite covering core logic, UI behavior, and network integrations.

### 1. Logic Verification (Quick Sanity)
Mocks the Anki/Qt environment. No API keys or internet required.
```shell
python3 -B tests/local_verify.py
```
- **Tests**: Addon import, MathJax normalization logic, model name mapping.

### 2. Specialized Logic Suites
Targeted unit tests for core internal engines.
```shell
# LaTeX normalization regression tests:
python3 -B tests/test_latex_fixer.py

# JSON repair and malformed output recovery:
python3 tests/test_json_repair_integration.py

# Card content extraction and cloze parsing:
python3 tests/test_card_parser.py

# AI response sanitization (prefix/hallucination cleaning):
python3 tests/test_sanitization_regex.py
```

### 3. Lifecycle and Integration
Verifies the orchestration of background processes and UI states.
```shell
# Reviewer state management (generation cycle and UI reset):
python3 tests/test_generation_cycle.py

# Local AI (Ollama/LM Studio) integration:
python3 tests/test_local_ai.py
```

### 4. Live Network Tests
Requires real API keys configured in `addon/config.json` or a local `meta.json`.
```shell
# Full end-to-end generation test against active cloud providers:
python3 tests/live_test.py

# Direct low-level network check for local endpoints:
python3 tests/test_raw_local.py
```

### 5. Full Suite
Run all discovery-compatible tests using Python's standard unittest runner:
```shell
python3 -B -m unittest discover -s tests -p "test_*.py"
```

---

## Creating a Release

1. **Commit and tag:**
   ```shell
   git add .
   git commit -m "Release v1.6.1"
   git tag v1.6.1
   git push origin master --tags
   ```

2. **Build the package:**
   ```shell
   python make_ankiaddon.py 1.6.1
   ```

3. **Upload to GitHub Releases:**
   - Create a new GitHub Release for the tag `v1.6.1`
   - Attach the `.ankiaddon` file as a release asset

4. **Upload to AnkiWeb:**
   - Log in to https://ankiweb.net/shared/upload
   - Upload the `.ankiaddon` file to update the listing

---

## Code Standards

- Maintain compatibility with **Anki 25.x** (Qt 6, PyQt 6, Python 3.10+).
- All Qt UI code must run on the **main thread**. Background work uses `threading.Thread` + `mw.taskman.run_on_main()`.
- No blocking I/O inside `__init__` or tab constructors — defer with `QTimer.singleShot(0, ...)`.
- Keep `ADDON_PACKAGE` derived from `__name__.split(".")[0]` (not hardcoded) to support both dev and production installs.
