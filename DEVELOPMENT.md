# AI-Hints - Developer Documentation

This repository contains the source code for the **AI-Hints** Anki add-on.

## Quick Links

- **Main Repository**: https://github.com/athulkrishna2015/AI-Hints
- **Install via AnkiWeb**: https://ankiweb.net/shared/info/2119980872
- **Report an Issue**: https://github.com/athulkrishna2015/AI-Hints/issues

---

## Project Structure

- `addon/`: The core add-on code.
- `addon/latex_fixer/`: Robust LaTeX/MathJax normalization logic.
- `addon/json_repair/`: Lightweight library to fix malformed JSON from AI models.
- `addon/ai_client.py`: Multi-provider AI client (Gemini, Groq, OpenRouter, etc.).
- `addon/config_ui.py`: Configuration GUI with dynamic field selectors.
- `addon/reviewer_hooks.py`: Logic for generating hints during review.
- `tests/`: 
  - `local_verify.py`: Comprehensive logic verification (Mocks Anki/Qt).
  - `live_test.py`: Live AI generation test using keys from `meta.json`.
- `make_ankiaddon.py`: Build script for the `.ankiaddon` package.
- `bump.py`: Standalone script to increment the version.

---

## Development Workflow

### 1. Local Testing (Symlinking)
The fastest way to test changes is to symlink the `addon/` folder into your Anki add-ons directory.

**Linux/macOS:**
```shell
ln -s "$(pwd)/addon" ~/.local/share/Anki2/addons21/ai_hints_dev
```

**Windows (Admin PowerShell):**
```powershell
New-Item -ItemType SymbolicLink -Path "$env:APPDATA\Anki2\addons21\ai_hints_dev" -Target "$pwd\addon"
```

### 2. Building and Versioning
- Build locally (auto-bumps version):
```shell
python make_ankiaddon.py
```

- Manually bump the version (auto-increment):
```shell
python bump.py
```

- Set an explicit version:
```shell
python make_ankiaddon.py 2.7
```

**Versioning rule:** versions follow `major.minor` or `major.minor.patch` (e.g., `2.7` or `2.7.1`).

### 3. Running Tests
- **Unit Test Suite**:
  Run all local unit tests:
  ```shell
  python3 -B -m unittest discover -s tests -p "test_*.py"
  ```

- **Logic Verification (Local)**:
  Run the logic verification suite (no API keys required, mocks Anki/Qt):
  ```shell
  python3 -B tests/local_verify.py
  ```

- **LaTeX Fixer Tests**:
  Verify LaTeX and MathJax formatting normalization:
  ```shell
  python3 -B tests/test_latex_fixer.py
  ```

- **Live Provider Test**:
  Test your API keys and provider connectivity (requires `addon/meta.json` with keys):
  ```shell
  python3 tests/live_test.py
  ```

### 4. Scratch Scripts & Diagnostics
The `scratch/` directory is used for holding temporary scripts, API diagnostic runs, and raw JSON logs.
- **Fetch All Models Script** (`scratch/fetch_all_models.py`):
  Used to pull all available models and pricing endpoints directly from the active API providers to diagnose and test active models.
  ```shell
  python3 scratch/fetch_all_models.py
  ```
- **Diagnostics Output** (`scratch/all_available_models.json`):
  Stores the diagnostic JSON output of all parsed and fetched models.

### 5. Creating a Release on GitHub
1. **Commit and Tag**:
```bash
git add .
git commit -m "Bump version to v1.1.4"
git tag v1.1.4
git push origin master --tags
```
2. **Build and Upload to Releases**:
Build the `.ankiaddon` package and upload it directly to the GitHub release assets:
```shell
python make_ankiaddon.py
```

---

## Code Standards
We follow clean coding practices. Please ensure any modifications maintain compatibility with Anki's UI APIs and importer behavior.
