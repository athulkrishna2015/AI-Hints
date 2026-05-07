import re
from typing import List, Optional, Tuple
from aqt import mw

class CardParser:
    def __init__(self, target_fields: List[str], note_type_fields: Dict[str, List[str]] = None):
        self.target_fields = target_fields
        self.note_type_fields = note_type_fields or {}
        self.container_class = "ai-hints-container"

    def get_note_content(self, note) -> Tuple[str, str]:
        """Extracts front and back content for AI context based on note type config."""
        model_name = note.model()["name"]
        field_names = self.note_type_fields.get(model_name)
        
        if field_names:
            # Use specific fields from config
            content_parts = []
            for f_name in field_names:
                if f_name in note:
                    content_parts.append(note[f_name])
            return self._clean_html(" ".join(content_parts)), ""
        
        # Fallback to default heuristic
        fields = note.items()
        front = ""
        back = ""
        
        if fields:
            front = fields[0][1]
            # If it's a Cloze card, we often don't need the other fields for generating options
            if "cloze" in model_name.lower():
                back = ""
            else:
                back = "\n".join([v for k, v in fields[1:]])
        
        return self._clean_html(front), self._clean_html(back)

    def _clean_html(self, html: str) -> str:
        """Remove most HTML tags to reduce tokens and noise."""
        # Remove scripts and styles
        html = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other tags but keep content
        text = re.sub(r"<.*?>", " ", html)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def update_note_with_hints(self, note, options: List[str]) -> bool:
        """Appends or replaces the AI hints block in the target field."""
        if not options:
            return False

        # Build HTML
        html_block = self._build_html_block(options)
        
        # Find target field
        field_name = self._find_target_field(note)
        if not field_name:
            # Fallback to last field if no target found
            field_name = list(note.keys())[-1]

        current_val = note[field_name]
        
        # Check if container already exists
        pattern = rf'<div class="{self.container_class}".*?</div>'
        if re.search(pattern, current_val, re.DOTALL):
            new_val = re.sub(pattern, html_block, current_val, flags=re.DOTALL)
        else:
            new_val = current_val + "\n" + html_block

        note[field_name] = new_val
        return True

    def _find_target_field(self, note) -> Optional[str]:
        note_fields = note.keys()
        for target in self.target_fields:
            if target in note_fields:
                return target
        return None

    def _build_html_block(self, options: List[str]) -> str:
        items_html = "".join([f"<li>{opt}</li>" for opt in options])
        return f"""
<div class="{self.container_class}">
    <hr>
    <b>AI Generated Options:</b>
    <ul class="ai-hints-list">
        {items_html}
    </ul>
</div>
"""
