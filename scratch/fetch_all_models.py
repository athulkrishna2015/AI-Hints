import json
import urllib.request
import urllib.error
import ssl

def fetch_models(provider, url, api_key, auth_header="Authorization", auth_prefix="Bearer "):
    print(f"--- Fetching {provider} ---")
    headers = {auth_header: f"{auth_prefix}{api_key}"}
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode())
            if "data" in data:
                models = [m.get("id") for m in data["data"] if m.get("id")]
            elif isinstance(data, list):
                models = [m.get("id") if isinstance(m, dict) else m for m in data]
            else:
                models = []
            
            # Filter and sort
            models = sorted(list(set(models)))
            print(f"Found {len(models)} models.")
            return models
    except Exception as e:
        print(f"Error fetching {provider}: {e}")
        return []

def main():
    with open("addon/config.json", "r") as f:
        config = json.load(f)
    
    api_keys = config.get("api_keys", {})
    results = {}
    
    providers = {
        "openai": "https://api.openai.com/v1/models",
        "groq": "https://api.groq.com/openai/v1/models",
        "openrouter": "https://openrouter.ai/api/v1/models",
        "mistral": "https://api.mistral.ai/v1/models",
        "together": "https://api.together.xyz/v1/models",
        "sambanova": "https://api.sambanova.ai/v1/models",
        "cerebras": "https://api.cerebras.ai/v1/models",
        "nvidia": "https://integrate.api.nvidia.com/v1/models",
        "deepseek": "https://api.deepseek.com/models",
        "huggingface": "https://router.huggingface.co/v1/models"
    }
    
    for p, url in providers.items():
        key = api_keys.get(p)
        if key:
            models = fetch_models(p, url, key)
            if models:
                results[p] = models
    
    with open("scratch/all_available_models.json", "w") as f:
        json.dump(results, f, indent=4)
    print("\nResults saved to artifacts/all_available_models.json")

if __name__ == "__main__":
    main()
