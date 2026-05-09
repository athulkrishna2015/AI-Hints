#!/usr/bin/env python3
import os
import urllib.request
import sys

"""
This script updates the vendored dependencies for the AI-Hints addon.
It downloads the latest core files from the respective source repositories.
"""

DEPENDENCIES = {
    "json_repair": {
        "base_url": "https://raw.githubusercontent.com/mangiucugna/json_repair/master/src/json_repair",
        "target_dir": "addon/json_repair",
        "files": [
            "__init__.py",
            "json_repair.py",
            "json_parser.py",
            "parse_array.py",
            "parse_boolean.py",
            "parse_null.py",
            "parse_number.py",
            "parse_object.py",
            "parse_string.py",
            "parser_parenthesized.py",
            "parser_schema.py",
            "schema_repair.py",
            "parse_comment.py",
            "py.typed"
        ],
        "subdirs": {
            "parse_string_helpers": [
                "__init__.py",
                "object_value_context.py",
                "parse_boolean_or_null.py",
                "parse_json_llm_block.py"
            ],
            "utils": [
                "__init__.py",
                "constants.py",
                "json_context.py",
                "object_comparer.py",
                "pattern_properties.py",
                "string_file_wrapper.py"
            ]
        }
    }
}

def download_file(url, local_path):
    print(f"  Downloading: {url} -> {local_path}")
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        urllib.request.urlretrieve(url, local_path)
    except Exception as e:
        print(f"  ERROR downloading {url}: {e}")
        return False
    return True

def update_json_repair():
    cfg = DEPENDENCIES["json_repair"]
    target_root = cfg["target_dir"]
    base_url = cfg["base_url"]
    
    print(f"Updating {target_root} from {base_url}...")
    
    # 1. Download root files
    for filename in cfg["files"]:
        url = f"{base_url}/{filename}"
        path = os.path.join(target_root, filename)
        download_file(url, path)
        
    # 2. Download subdirectories
    for subdir, files in cfg["subdirs"].items():
        for filename in files:
            url = f"{base_url}/{subdir}/{filename}"
            path = os.path.join(target_root, subdir, filename)
            download_file(url, path)
            
    print("\nSuccessfully updated json_repair.")
    print("Recommendation: Run 'python3 tests/test_json_repair_integration.py' to verify.")

def main():
    update_json_repair()

if __name__ == "__main__":
    main()
