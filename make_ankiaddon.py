import os
import argparse
import sys
import zipfile
import fnmatch
from datetime import datetime
from pathlib import Path

from bump import (
    bump_version as bump_patch_version,
    read_current_version,
    sync_version,
    validate_version,
)

# Configuration
ADDON_NAME = "AI_Hints"
ADDON_DIR = "addon"

def load_gitignore_patterns(root_dir: Path) -> list[str]:
    gitignore_path = root_dir / ".gitignore"
    if not gitignore_path.exists():
        return []
    
    patterns = []
    with gitignore_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns

def is_ignored(path: Path, root_dir: Path, patterns: list[str]) -> bool:
    rel_path = path.relative_to(root_dir).as_posix()
    parts = rel_path.split("/")
    
    # Exclude standard built-in git files unconditionally
    if ".git" in parts:
        return True
        
    for pattern in patterns:
        p = pattern
        is_dir_only = p.endswith("/")
        if is_dir_only:
            p = p[:-1]
            
        # 1. Match full relative path or any individual part/sub-path
        if fnmatch.fnmatch(rel_path, p) or any(fnmatch.fnmatch(part, p) for part in parts):
            return True
            
        # 2. Match directory prefix (e.g. pattern is 'scratch' and path is 'scratch/file.txt')
        for i in range(1, len(parts) + 1):
            sub_path = "/".join(parts[:i])
            if fnmatch.fnmatch(sub_path, p):
                return True
                
    return False

def artifact_names(
    addon_name: str,
    version: str,
    when: datetime | None = None,
) -> tuple[str, str]:
    dt = when or datetime.today()
    timestamp = dt.strftime("%Y%m%d%H%M")
    base = f"{addon_name}_v{version}_{timestamp}"
    return f"{base}.zip", f"{base}.ankiaddon"

def bump_version(addon_path: Path | None = None) -> int:
    target = addon_path or Path(ADDON_DIR)
    return bump_patch_version(target)

def resolve_build_version(
    addon_path: Path,
    explicit_version: str | None = None,
) -> str:
    if explicit_version is None:
        code = bump_version(addon_path)
        if code != 0:
            raise RuntimeError("Failed to bump version.")
        return read_current_version(addon_path)

    version = validate_version(explicit_version)
    sync_version(version, addon_path)
    print(f"Using explicit version: {version}")
    return version

def create_ankiaddon(explicit_version: str | None = None) -> int:
    # Get the project root and addon directory
    root_dir = Path(__file__).resolve().parent
    addon_path = root_dir / ADDON_DIR

    if not addon_path.exists():
        print(f"Error: {ADDON_DIR} directory not found.")
        return 1

    try:
        build_version = resolve_build_version(addon_path, explicit_version)
    except Exception as e:
        print(f"Error: Could not prepare build version: {e}")
        return 1

    zip_name, final_name = artifact_names(ADDON_NAME, build_version)

    # Clean up any existing .ankiaddon files in the root directory first to keep it tidy
    for f in root_dir.glob("*.ankiaddon"):
        try:
            os.remove(f)
        except Exception:
            pass

    # Load gitignore patterns to filter files dynamically
    gitignore_patterns = load_gitignore_patterns(root_dir)

    print(f"Creating {final_name} from {ADDON_DIR} using .gitignore rules...")

    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the addon directory specifically
        for root, dirs, files in os.walk(addon_path):
            # Prune directories in-place using gitignore
            pruned_dirs = []
            for d in dirs:
                dir_path = Path(root) / d
                if not is_ignored(dir_path, root_dir, gitignore_patterns):
                    pruned_dirs.append(d)
            dirs[:] = pruned_dirs
            
            for file in files:
                file_path = Path(root) / file
                
                # Check if file matches gitignore rules
                if is_ignored(file_path, root_dir, gitignore_patterns):
                    continue
                
                # Skip proxy binaries by matching prefix (since these are built binary artifacts)
                # Keep only what is not gitignored or is actual source
                if any(file.startswith(n) for n in ['antigravity-proxy-linux', 'antigravity-proxy-windows', 'antigravity-proxy-darwin']):
                    continue
                
                # Calculate the path relative to the 'addon/' folder 
                # so that __init__.py is at the root of the zip
                archive_name = file_path.relative_to(addon_path)
                zipf.write(file_path, archive_name)

    # Rename to .ankiaddon
    if os.path.exists(final_name):
        os.remove(final_name)
    os.rename(zip_name, final_name)
    print(f"Successfully created: {final_name}")
    return 0

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create .ankiaddon package. "
            "If no version is provided, patch version is auto-bumped via bump.py."
        )
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Optional explicit version (major.minor[.patch]) to set before packaging.",
    )
    return parser.parse_args(argv[1:])

def main(argv: list[str]) -> int:
    args = parse_args(argv)
    return create_ankiaddon(args.version)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
