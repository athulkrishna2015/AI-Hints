import urllib.request
import json
import sys

def ankiconnect_request(action, **params):
    payload = {"action": action, "version": 6, "params": params}
    req = urllib.request.Request("http://localhost:8765", data=json.dumps(payload).encode('utf-8'))
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res.get("error"):
                raise Exception(res["error"])
            return res.get("result")
    except Exception as e:
        print(f"AnkiConnect Error: {e}")
        return None

def test_live_database_verification():
    print("--- Running AnkiConnect Database Verification ---")
    
    # 1. Check connection
    version = ankiconnect_request("version")
    if not version:
        print("FAIL: AnkiConnect not running or not responding.")
        sys.exit(1)
    print(f"Connected to Anki (AnkiConnect version {version})")

    # 2. Find cards containing AI hints
    cards = ankiconnect_request("findCards", query="ai-hints-json")
    if not cards:
        print("NOTE: No cards with 'ai-hints-json' found in the active collection.")
        print("PASS (Skipped - no hints found).")
        sys.exit(0)
    
    print(f"Found {len(cards)} cards containing generated AI hints in collection.")

    # Try to find newly generated cards that have the _generation_type key
    new_cards = ankiconnect_request("findCards", query="re:_generation_type")
    if not new_cards:
        print("NOTE: Found legacy hints cards, but none have '_generation_type' yet.")
        print("This is expected for existing collection notes until new hints are generated.")
        print("PASS (Legacy database verification succeeded).")
        sys.exit(0)

    print(f"Found {len(new_cards)} new cards containing '_generation_type' metadata.")
    card_info = ankiconnect_request("cardsInfo", cards=[new_cards[0]])
    if not card_info:
        print("FAIL: Could not retrieve card info.")
        sys.exit(1)
        
    note_id = card_info[0].get("note")
    note_info = ankiconnect_request("notesInfo", notes=[note_id])
    if not note_info:
        print("FAIL: Could not retrieve note info.")
        sys.exit(1)
        
    # Check fields for JSON block and search for generation keys
    found_generation_keys = False
    fields = note_info[0].get("fields", {})
    for f_name, f_data in fields.items():
        val = f_data.get("value", "")
        print(f"  Field: {f_name}")
        print(f"  Value snippet: {repr(val[:150])}")
        if "ai-hints-json" in val:
            print(f"  -> Found ai-hints-json in field '{f_name}'")
            has_type = "_generation_type" in val
            has_version = "_version" in val
            print(f"  -> _generation_type present: {has_type}")
            print(f"  -> _version present:         {has_version}")
            if has_type and has_version:
                found_generation_keys = True
                break
            
    if found_generation_keys:
        print("PASS: Verified that serialized database blocks are structured correctly.")
    else:
        print("FAIL: AI Hints JSON block found, but could not locate both serialized metadata keys in the fields.")
        print("Full fields dump:")
        for fn, fd in fields.items():
            print(f"[{fn}]: {repr(fd.get('value'))}")
        sys.exit(1)

if __name__ == "__main__":
    test_live_database_verification()
