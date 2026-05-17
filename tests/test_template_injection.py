import re
import unittest

def get_full_template_block(use_emojis=False, show_extra=False):
    config_js = f"window.aiHintsMobileConfig = {{ useEmojis: {'true' if use_emojis else 'false'}, showExtraButtons: {'true' if show_extra else 'false'} }};"
    return (
        "<!-- AI-HINTS-BEGIN -->\n"
        "<ai-hints></ai-hints>\n"
        "<script>\n"
        f"{config_js}\n"
        "</script>\n"
        "<script src='_ai_hints_template.js'></script>\n"
        "<!-- AI-HINTS-END -->"
    )

def inject_into_html(old_html, new_block):
    if "<!-- AI-HINTS-BEGIN -->" in old_html:
        pattern = r"<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
        new_html = re.sub(pattern, new_block, old_html, flags=re.DOTALL)
        return new_html
    else:
        return old_html + "\n\n" + new_block

class InjectionTests(unittest.TestCase):
    def test_first_time_injection(self):
        html = "<div>Front</div>"
        block = get_full_template_block()
        result = inject_into_html(html, block)
        self.assertIn("<div>Front</div>", result)
        self.assertIn("<!-- AI-HINTS-BEGIN -->", result)
        self.assertIn("_ai_hints_template.js", result)

    def test_update_injection(self):
        old_block = get_full_template_block(use_emojis=False)
        html = f"<div>Front</div>\n\n{old_block}"
        new_block = get_full_template_block(use_emojis=True)
        
        result = inject_into_html(html, new_block)
        
        self.assertIn("<div>Front</div>", result)
        self.assertIn("useEmojis: true", result)
        self.assertEqual(result.count("<!-- AI-HINTS-BEGIN -->"), 1)

    def test_removal_regex(self):
        block = get_full_template_block()
        html = f"<div>Front</div>\n\n{block}"
        pattern = r"(\n\n)?<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
        result = re.sub(pattern, "", html, flags=re.DOTALL)
        self.assertEqual(result.strip(), "<div>Front</div>")

if __name__ == "__main__":
    unittest.main()
