import json
import sys
import os

# Add workspace to path so we can import addon modules
sys.path.insert(0, "/mnt/0946E88701BE265B/portable/anki/addons/AI-Hints")

# Mock the global `mw` and logging needed by ai_client
from unittest.mock import MagicMock
import logging
import urllib.request

# Define minimalistic sys modules to prevent import errors
class MockLogger:
    def info(self, *args): print("INFO:", *args)
    def warning(self, *args): print("WARNING:", *args)
    def error(self, *args): print("ERROR:", *args)
    def debug(self, *args): print("DEBUG:", *args)

sys.modules["aqt"] = MagicMock()
sys.modules["aqt.utils"] = MagicMock()
sys.modules["anki"] = MagicMock()

# Import the client AFTER mocking
try:
    from addon.ai_client import AIClient
except ImportError:
    print("Could not import addon.ai_client. Retrying absolute.")
    sys.path.insert(0, os.path.abspath("."))
    from addon.ai_client import AIClient

def main():
    meta_path = "/mnt/0946E88701BE265B/portable/anki/addons/AI-Hints/addon/meta.json"
    output_path = "/mnt/0946E88701BE265B/portable/anki/addons/AI-Hints/scratch/all_available_models.json"
    
    print("Reading meta.json...")
    with open(meta_path, 'r') as f:
        meta = json.load(f)
    
    config = meta.get("config", {})
    api_keys = config.get("api_keys", {})
    print(f"Found {len([k for k,v in api_keys.items() if v])} configured providers.")

    # Read existing models to preserve other providers' old data
    final_results = {}
    if os.path.exists(output_path):
        with open(output_path, 'r') as f:
            try:
                final_results = json.load(f)
            except:
                pass

    # Instantiate the client with extracted config
    client = AIClient(config=config)
    
    providers = [
        "gemini", "groq", "openrouter", "huggingface", 
        "together", "sambanova", "cerebras", "openai", 
        "anthropic", "deepseek", "mistral", "nvidia", "grok"
    ]

    for provider in providers:
        key = api_keys.get(provider, "").strip()
        if not key:
            print(f"Skipping {provider} - no API key.")
            continue
            
        print(f"Fetching models for {provider}...")
        try:
            # Directly call fetch_models from our class
            models = client.fetch_models(provider)
            if models:
                models.sort()
                print(f"  Success! Found {len(models)} models.")
                final_results[provider] = models
            else:
                print(f"  No models returned for {provider}.")
        except Exception as e:
            print(f"  FAILED {provider}: {e}")

    # Write out final combined result
    print(f"Writing all results to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(final_results, f, indent=4)
    print("Operation complete.")

if __name__ == "__main__":
    main()
