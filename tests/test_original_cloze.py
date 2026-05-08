import sys
import os
import json
import html
from unittest.mock import MagicMock
import re

# Add addon directory to path
addon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon")
sys.path.append(addon_path)

from card_parser import CardParser

def test_cloze_storage_original():
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
    
    # Verify blocks
    blocks = re.findall(r'<div.*?class="ai-hints-json".*?>.*?</div>', note['Extra'], re.DOTALL)
    print(f"\nNumber of blocks found: {len(blocks)}")
    
    if len(blocks) == 2:
        print("Success: Original code supports multiple blocks for multiple clozes.")
    else:
        print(f"Failure: Original code produced {len(blocks)} blocks.")

    # Test clearing c1
    print("\nClearing c1...")
    parser.clear_hints_from_note(mock_note, card=card_c1)
    print(f"Field content after clearing c1: {note['Extra']}")
    
    blocks = re.findall(r'<div.*?class="ai-hints-json".*?>.*?</div>', note['Extra'], re.DOTALL)
    print(f"Number of blocks after clearing c1: {len(blocks)}")
    
    # Test finding block for c2
    print("\nFinding block for c2...")
    found = parser.find_hints_block(mock_note, card=card_c2)
    if found and 'data-ai-hints-card-ord="1"' in found:
        print("Success: Correct block found for c2.")
    else:
        print("Failure: Could not find correct block for c2.")

if __name__ == "__main__":
    test_cloze_storage_original()
