import sys
import os
import json
import html
from unittest.mock import MagicMock

# Add addon directory to path
addon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon")
sys.path.append(addon_path)

from card_parser import CardParser

def test_cloze_storage():
    parser = CardParser(target_fields=["Extra"], storage_mode="json")
    
    # Mock note
    note = {"Extra": ""}
    def set_item(key, val): note[key] = val
    def get_item(key): return note[key]
    def keys(): return note.keys()
    
    mock_note = MagicMock()
    mock_note.__setitem__.side_effect = set_item
    mock_note.__getitem__.side_effect = get_item
    mock_note.keys.side_effect = keys
    
    # Mock cards
    card_c1 = MagicMock()
    card_c1.ord = 0
    card_c1.id = 101
    
    card_c2 = MagicMock()
    card_c2.ord = 1
    card_c2.id = 102
    
    # Data for c1
    data_c1 = {"hints": ["hint1"], "options": ["opt1", "opt2"]}
    
    print("Updating c1...")
    parser.update_note_with_hints(mock_note, data_c1, card=card_c1)
    print(f"Field content: {note['Extra']}")
    
    # Data for c2
    data_c2 = {"hints": ["hint2"], "options": ["opt3", "opt4"]}
    
    print("\nUpdating c2...")
    parser.update_note_with_hints(mock_note, data_c2, card=card_c2)
    print(f"Field content: {note['Extra']}")
    
    # Verify JSON structure
    pattern = r'<div.*?class="ai-hints-json".*?>(.*?)</div>'
    import re
    match = re.search(pattern, note['Extra'], re.DOTALL)
    assert match, "JSON block not found"
    
    payload = json.loads(html.unescape(match.group(1)))
    assert "c1" in payload, "c1 key missing"
    assert "c2" in payload, "c2 key missing"
    assert payload["c1"]["hints"] == ["hint1"]
    assert payload["c2"]["hints"] == ["hint2"]
    
    print("\nVerification successful: Unified JSON block contains both c1 and c2 data.")
    
    # Test clearing c1
    print("\nClearing c1...")
    parser.clear_hints_from_note(mock_note, card=card_c1)
    print(f"Field content after clearing c1: {note['Extra']}")
    
    match = re.search(pattern, note['Extra'], re.DOTALL)
    payload = json.loads(html.unescape(match.group(1)))
    assert "c1" not in payload, "c1 key still present"
    assert "c2" in payload, "c2 key missing after clearing c1"
    
    print("Verification successful: c1 cleared, c2 remains.")
    
    # Test clearing c2
    print("\nClearing c2...")
    parser.clear_hints_from_note(mock_note, card=card_c2)
    print(f"Field content after clearing c2: '{note['Extra'].strip()}'")
    assert "ai-hints-json" not in note["Extra"], "Block still present after clearing everything"
    
    print("Verification successful: Block removed when empty.")

if __name__ == "__main__":
    try:
        test_cloze_storage()
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
