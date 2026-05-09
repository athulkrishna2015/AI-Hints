
import re

def clean_output(text: str) -> str:
    if not text:
        return ""
    
    # Strip trailing JSON or technical metadata hallucinations
    # We use \\* to match any number of backslashes before the quote (escaped JSON).
    text = re.sub(r'\s*\{[\s\S]*\\*"(?:hints|options|c\d+)\\*"\s*:[\s\S]*\}\s*$', '', text)
    
    # Strip prefixes
    text = re.sub(r'^(?:Answer|Option|Hint|Choice|Distractor)\s*:\s*', '', text, flags=re.IGNORECASE)
    
    # Strip surrounding quotes
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        text = text[1:-1]
        
    return text.strip()

def test_regex():
    print("--- Running Regex Sanitization Tests ---")
    
    test_cases = [
        ('Carbon:C {"c1": {"hints": ["..."], "options": ["..."]}}', "Carbon:C"),
        ('Carbon:C {\\"c1\\": {\\"hints\\\": [\\\"...\\\"]}}', "Carbon:C"),
        ('Oxygen:O {"options": ["O", "O2"]}', "Oxygen:O"),
        ('Answer: Beta', "Beta"),
        ('Option: "Alpha"', "Alpha"),
        ('"Quoted Option"', "Quoted Option")
    ]

    success_count = 0
    for inp, exp in test_cases:
        out = clean_output(inp)
        if out == exp:
            print(f"PASS: '{inp}' -> '{out}'")
            success_count += 1
        else:
            print(f"FAIL: '{inp}' -> expected '{exp}', got '{out}'")

    if success_count == len(test_cases):
        print("\nALL REGEX TESTS PASSED")
    else:
        print(f"\n{len(test_cases) - success_count} TESTS FAILED")
        exit(1)

if __name__ == "__main__":
    test_regex()
