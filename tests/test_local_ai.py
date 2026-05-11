
import sys
import os
import json
import asyncio
from unittest.mock import MagicMock

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

# Mock logger
mock_logger = MagicMock()
sys.modules['logger'] = mock_logger
sys.modules['.logger'] = mock_logger

# Import components
from addon.ai_client import AIClient
from addon.card_parser import CardParser

async def test_local_ai():
    print("--- Running Local AI Test (Ollama/LM Studio) ---")
    
    # Load config
    config_path = os.path.join(ADDON_DIR, 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Force local provider
    config["ai_provider"] = "local"
    config["local_endpoint"]["enabled"] = True
    
    client = AIClient(config)
    parser = CardParser(target_fields=["Back"])

    front = "What is the capital of France?"
    back = "Paris. It is known as the City of Light."

    print(f"Targeting: {config['local_endpoint']['base_url']} with model {config['local_endpoint']['model']}")
    
    try:
        loop = asyncio.get_event_loop()
        # client.generate_options is a blocking call that uses requests
        future = loop.run_in_executor(None, client.generate_options, front, back)
        res = await future
        
        if not res or ("hints" not in res and "options" not in res and "correct_answer" not in res):
            print("FAILED: No valid data received from Local AI.")
            print(f"Response: {res}")
        else:
            print("SUCCESS: Received data from Local AI:")
            print(json.dumps(res, indent=2))
            
            # Verify parsing
            normalized = parser.normalize_hint_data(res)
            print("\nNormalized for Anki:")
            print(json.dumps(normalized, indent=2))

    except Exception as e:
        print(f"ERROR: Local AI test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_local_ai())
