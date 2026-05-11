
import sys
import os
import json
import urllib.request
import urllib.error

# Setup paths
sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(PROJECT_ROOT, 'addon')
sys.path.insert(0, PROJECT_ROOT)

def test_raw_local():
    print("--- Running Raw Local AI Test ---")
    
    # Load config
    config_path = os.path.join(ADDON_DIR, 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    local_cfg = config.get("local_endpoint", {})
    base_url = local_cfg.get("base_url", "http://localhost:11434/v1")
    model = local_cfg.get("model", "llama3")
    url = f"{base_url}/chat/completions"
    
    print(f"Targeting: {url} with model {model}")
    
    system_prompt = config.get("system_prompt", "Return JSON")
    user_prompt = "What is the capital of France?"
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1
    }
    
    # Do NOT use response_format for llama3/Ollama unless we know it supports it
    # But wait, our client DOES use it for some providers. 
    # Let's try WITHOUT it first to see what we get.
    
    req = urllib.request.Request(url)
    req.add_header('Content-Type', 'application/json')
    
    try:
        response = urllib.request.urlopen(req, data=json.dumps(data).encode('utf-8'), timeout=30)
        res_data = json.loads(response.read().decode('utf-8'))
        content = res_data['choices'][0]['message']['content']
        print("\nRAW CONTENT FROM MODEL:")
        print("-" * 30)
        print(content)
        print("-" * 30)
        
        try:
            # Try to find JSON block
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                print("\nPARSED JSON:")
                print(json.dumps(parsed, indent=2))
            else:
                print("\nNo JSON block found in response.")
        except Exception as pe:
            print(f"\nFailed to parse JSON from content: {pe}")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_raw_local()
