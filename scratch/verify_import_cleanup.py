import sys
import os
import re
import html
import json

# Add addon directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from addon.card_parser import CardParser

class MockNote(dict):
    def __init__(self, fields):
        super().__init__(fields)
        self.id = 999
    def keys(self):
        return list(super().keys())
    def values(self):
        return list(super().values())

def test_user_data_cleanup():
    parser = CardParser(storage_mode="json")

    # User's provided content (simplified snippet of the first complex note)
    raw_field = """1911-ലെ ചൈനീസ് വിപ്ലവത്തിൻ്റെ നേതാവായ സൺ-യാത്-സൺ ചൈനയുടെ പുനർനിർമ്മാണത്തിനായി ആവിഷ്കരിച്ച മൂന്നു തത്വങ്ങളാണ് {{c1::ദേശീയത}}, {{c2::ജനാധിപത്യം}}, {{c3::സോഷ്യലിസം}} എന്നിവ.

<div class="ai-hints-container" data-ai-hints-addon-id="2119980872" contenteditable="false" data-show-hints="true" data-show-options="true" data-ai-hints-card-id="1780852544449" data-ai-hints-card-ord="2">
    <hr>
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>ജനങ്ങളുടെ സാമ്പത്തിക ക്ഷേമത്തിലും ഉപജീവനത്തിലും ഊന്നൽ നൽകുന്ന തത്വം</li><li>സ്വകാര്യ സ്വത്തവകാശത്തിന് പകരം പൊതുവായ സാമൂഹിക ഉടമസ്ഥാവകാശം എന്ന ആശയം</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>സോഷ്യലിസം</li><li>കമ്മ്യൂണിസം</li><li>ക്യാപിറ്റലിസം</li><li>ഇംപീരിയലിസം</li></ul>
</div>


<div class="ai-hints-container" data-ai-hints-addon-id="2119980872" contenteditable="false" data-show-hints="true" data-show-options="true" data-ai-hints-card-id="1780852544450" data-ai-hints-card-ord="0">
    <hr>
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>സൺ-യാത്-സണ്ണിന്റെ 'ത്രീ പ്രിൻസിപ്പിൾസ് ഓഫ് ദി പീപ്പിൾ' (Three Principles of the People) എന്ന ആശയത്തെക്കുറിച്ച് ചിന്തിക്കുക.</li><li>ചൈനയുടെ ദേശീയ സ്വത്വത്തെയും സ്വാതന്ത്ര്യത്തെയും ഊന്നൽ നൽകുന്ന ഒരു ആശയമാണിത്.</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>ദേശീയത</li><li>രാജവാഴ്ച</li><li>മുതലാളിത്തം</li><li>ഏകാധിപത്യം</li></ul>
</div>


<div class="ai-hints-container" data-ai-hints-addon-id="2119980872" contenteditable="false" data-show-hints="true" data-show-options="true" data-ai-hints-card-id="1780852544451" data-ai-hints-card-ord="1">
    <hr>
    <b>AI Hints:</b><br><ul class="ai-hints-hint-list"><li>സൺ യാത് സെന്റെ 'സാൻ മിൻ' തത്വത്തിലെ രണ്ടാമത്തെ ഘഘടകം.</li><li>ജനങ്ങളുടെ ഭരണാധികാരം (Minquan) എന്നർത്ഥം വരുന്ന പദം.</li></ul>
    <b>AI Options:</b><br><ul class="ai-hints-list"><li>ജനാധിപത്യം</li><li>കമ്മ്യൂണിസം</li><li>മാർക്സിസം</li><li>റിപ്പബ്ലിക്കനിസം</li></ul>
</div>"""

    # We need to unescape quotes if they were escaped in the input (like in the text file)
    raw_field = raw_field.replace('""', '"')

    note = MockNote({"Content": raw_field})

    print("--- STEP 1: DETECTION ---")
    all_blocks = parser._extract_all_hints_from_fields(note)
    print(f"Found {len(all_blocks)} blocks in the field.")

    for i, b in enumerate(all_blocks):
        print(f"Block {i+1}: Card Key={b['card_key']}, Hints Count={len(b['data']['hints'])}")

    if len(all_blocks) != 3:
        print("FAILED: Expected 3 blocks extracted from HTML.")
        return

    print("\n--- STEP 2: CONSOLIDATION ---")
    # Simulate the logic in on_convert_html_to_json
    parser._remove_all_hints_from_fields(note)
    all_blocks.sort(key=lambda x: x.get("card_key", "") if x.get("card_key") else "")

    current_val = note["Content"]
    for block in all_blocks:
        current_val = parser._update_json_block_in_field(
            current_val, block["data"], block["card_key"], block.get("toggles", {})
        )

    note["Content"] = current_val

    # VERIFY RESULT
    # Should have one JSON block with c1, c2, c3
    if 'class="ai-hints-json"' not in current_val:
        print("FAILED: No JSON block found in result.")
        return

    if "ai-hints-container" in current_val:
        print("FAILED: Old HTML blocks still exist in result.")
        return

    # Extract JSON payload for deep verification
    m = re.search(r'ai-hints-json.*?>(.*?)</div>', current_val, re.DOTALL)
    if not m:
        print("FAILED: Could not locate JSON payload.")
        return

    payload = json.loads(html.unescape(m.group(1)))
    print(f"Final Keys in JSON: {list(payload.keys())}")

    if set(payload.keys()) == {"c1", "c2", "c3"}:
        print("\nSUCCESS: All 3 HTML blocks merged into 1 hidden JSON block!")
        print(f"Sample data from c3: {payload['c3']['hints'][0][:40]}...")
    else:
        print(f"FAILED: Missing keys in final JSON. Found: {list(payload.keys())}")

if __name__ == "__main__":
    test_user_data_cleanup()
