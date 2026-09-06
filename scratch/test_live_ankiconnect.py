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

def test_live_ankiconnect():
    print("--- Running AnkiConnect Live Database Test on Zhared::test ---")
    
    # 1. Check connection
    version = ankiconnect_request("version")
    if not version:
        print("FAIL: AnkiConnect not running or not responding.")
        sys.exit(1)
    print(f"Connected to Anki (AnkiConnect version {version})")

    # 2. Find cards in Zhared::test
    cards = ankiconnect_request("findCards", query='deck:"Zhared::test"')
    if not cards:
        print("FAIL: No cards found in 'Zhared::test' deck. Please make sure this deck exists and has at least one card.")
        sys.exit(1)
    
    print(f"Found {len(cards)} cards in 'Zhared::test'.")
    card_id = cards[0]
    
    # 3. Try to find a card we can update and verify
    verification_success = False
    for card_idx in range(min(5, len(cards))):
        card_id = cards[card_idx]
        card_info = ankiconnect_request("cardsInfo", cards=[card_id])
        note_id = card_info[0].get("note")
        note_info = ankiconnect_request("notesInfo", notes=[note_id])
        
        fields = note_info[0].get("fields", {})
        target_field = list(fields.keys())[0]
        original_val = fields[target_field].get("value", "")
        
        print(f"\n[Attempt {card_idx + 1}] Targeting note {note_id}, field '{target_field}'")
        
        test_json_block = (
            f'{original_val}<div class="ai-hints-json" style="display:none;">'
            '{"c1": {"hints": ["Test Hint"], "options": ["Opt 1"], '
            '"_generation_type": "manual", "_version": "5.2.0"}}</div>'
        )
        
        print("Writing test JSON block to database...")
        res = ankiconnect_request(
            "updateNoteFields", 
            note={
                "id": note_id,
                "fields": {
                    target_field: test_json_block
                }
            }
        )
        print("updateNoteFields response:", repr(res))
        
        # Read note back from database to verify persistence
        verified_note = ankiconnect_request("notesInfo", notes=[note_id])
        verified_val = verified_note[0].get("fields", {}).get(target_field, {}).get("value", "")
        
        if "ai-hints-json" in verified_val and "_generation_type" in verified_val and "_version" in verified_val:
            print("  PASS: metadata keys successfully written and verified.")
            verification_success = True
            
            # Clean up: restore original field value
            print("Restoring original note content...")
            ankiconnect_request(
                "updateNoteFields", 
                note={
                    "id": note_id,
                    "fields": {
                        target_field: original_val
                    }
                }
            )
            break
        else:
            print("  FAIL: note did not save JSON block (might be locked by open editor). Trying next card...")
            # Restore just in case it did save but returned different content
            ankiconnect_request(
                "updateNoteFields", 
                note={
                    "id": note_id,
                    "fields": {
                        target_field: original_val
                    }
                }
            )
        
    if verification_success:
        print("SUCCESS: Live AnkiConnect test passed cleanly.")
    else:
        sys.exit(1)

if __name__ == "__main__":
    test_live_ankiconnect()
