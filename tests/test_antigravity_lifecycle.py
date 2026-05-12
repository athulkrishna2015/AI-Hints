
import sys
import os
import time
import json
import urllib.request
from unittest.mock import MagicMock

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

# Mock logger to avoid file creation in wrong places
import addon.logger
addon.logger.logger = MagicMock()

from addon.proxy_manager import proxy_manager
from addon.ai_client import AIClient

def test_antigravity():
    print("--- Antigravity Proxy Lifecycle Test ---")
    
    config = {
        "antigravity_proxy": {
            "enabled": True,
            "port": 3000
        },
        "ai_provider": "antigravity",
        "models": {
            "antigravity": "gemini-1.5-flash"
        }
    }
    
    if not os.path.exists(proxy_manager.executable):
        print(f"FAILED: Proxy binary not found at {proxy_manager.executable}")
        return

    print("Starting proxy...")
    proxy_manager.start(config)
    
    # Wait for proxy to boot
    max_retries = 10
    started = False
    print("Waiting for proxy to respond on port 3000...")
    for i in range(max_retries):
        try:
            req = urllib.request.Request("http://localhost:3000/v1/models")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    print(f"Proxy is UP after {i+1} seconds.")
                    started = True
                    break
        except Exception:
            time.sleep(1)
            print(".", end="", flush=True)
    
    if not started:
        print("\nFAILED: Proxy failed to start or respond.")
        proxy_manager.stop()
        return

    print("\nRunning test generation...")
    client = AIClient(config)
    front = "What is the capital of Germany?"
    back = "Berlin"
    
    try:
        res = client.generate_options(front, back, override_provider="antigravity")
        print("\nGENERATION SUCCESS:")
        print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"\nGENERATION FAILED: {e}")
    
    print("\nStopping proxy...")
    proxy_manager.stop()
    print("Test complete.")

if __name__ == "__main__":
    test_antigravity()
