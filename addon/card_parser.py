import re
import json
import html
from typing import Any, List, Optional, Tuple, Dict
try:
    from .latex_fixer import fix_latex, normalize_math_text, repair_latex_control_chars
except ImportError:
    # Fallback/debug info
    fix_latex = lambda x, **kwargs: x
    normalize_math_text = lambda x, **kwargs: x
    repair_latex_control_chars = lambda x: x

class CardParser:

    def __init__(self, mathjax_format: str = "delimiters", fix_latex: bool = False, **kwargs):
        self.mathjax_format = mathjax_format
        self.fix_latex = fix_latex
        self.container_class = "ai-hints-container"
        self.json_class = "ai-hints-json"

    def _fix_lazy_latex(self, text: str) -> str:
        """Repairs common AI math errors like missing backslashes or joined commands."""
        return fix_latex(text, output_format=self._latex_output_format(), fix_latex=self.fix_latex)

    def normalize_hint_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize generated hint text before storage or direct reviewer injection."""
        if not isinstance(data, dict):
            return {"hints": [], "options": []}

        # Handle skipped cards
        if data.get("_skipped"):
            return {"hints": [], "options": [], "_skipped": True}

        # Handle new format with separate correct_answer and distractors.
        # We keep correct_answer so it survives into JSON storage; it is NOT
        # rendered in the UI (the frontend only reads "hints" and "options").
        correct_answer_raw = None
        if "correct_answer" in data and "distractors" in data:
            ans = data.get("correct_answer", "")
            dist = data.get("distractors", [])
            if not isinstance(dist, list):
                dist = [dist]
            data["options"] = [ans] + dist
            correct_answer_raw = ans  # remember before merging

        # Check if it's a hints/options object
        if "hints" in data or "options" in data:
            normalized = {"hints": [], "options": []}
            for key in ("hints", "options"):
                values = data.get(key, [])
                if not isinstance(values, list):
                    values = [values]
                
                seen = set()
                for value in values:
                    text = str(value).strip()
                    # Strip hallucinations before any math normalization
                    text = self._strip_ai_hallucinations(text)
                    
                    text = self._normalize_math_text(text)
                    if self.mathjax_format == "tags":
                        text = self._convert_to_mathjax_tags(text)
                    
                    # Only dedupe options, hints can be similar
                    if key == "options":
                        if not text:
                            continue
                        # Normalize whitespace for comparison
                        cmp_text = " ".join(text.strip().casefold().split())
                        if cmp_text in seen:
                            continue
                        seen.add(cmp_text)
                    
                    normalized[key].append(text)

            # Persist the correct answer in the JSON payload (storage-only,
            # not rendered by the frontend) so it can be used later for
            # answer-checking, analytics, or export.
            if correct_answer_raw is not None:
                ca = str(correct_answer_raw).strip()
                ca = self._strip_ai_hallucinations(ca)
                ca = self._normalize_math_text(ca)
                if self.mathjax_format == "tags":
                    ca = self._convert_to_mathjax_tags(ca)
                normalized["correct_answer"] = ca
            elif "correct_answer" in data:
                # Already in options-only format but caller included correct_answer key
                ca = str(data["correct_answer"]).strip()
                ca = self._strip_ai_hallucinations(ca)
                ca = self._normalize_math_text(ca)
                if self.mathjax_format == "tags":
                    ca = self._convert_to_mathjax_tags(ca)
                normalized["correct_answer"] = ca

            # Preserve metadata keys (starting with '_')
            for k, v in data.items():
                if k.startswith("_") and k not in normalized:
                    normalized[k] = v

            return normalized
        
        # Handle keyed structure (e.g. c1, c2)
        normalized = {}
        for k, v in data.items():
            if isinstance(v, dict):
                normalized[k] = self.normalize_hint_data(v)
            elif k.startswith("_"):
                normalized[k] = v
            else:
                pass # skip unknown fields
        return normalized



    def _strip_ai_hallucinations(self, text: str) -> str:
        if not text:
            return ""
        
        # 1. Strip trailing JSON or technical metadata hallucinations
        # We look for a trailing { ... } that contains technical keys.
        # We use \\* to match any number of backslashes before the quote (escaped JSON).
        text = re.sub(r'\s*\{[\s\S]*\\*"(?:hints|options|c\d+)\\*"\s*:[\s\S]*\}\s*$', '', text)
        
        # 2. Strip "Answer: " or "Option: " prefixes if AI included them
        # We ensure it's a prefix by using ^ and check for optional space after colon
        text = re.sub(r'^(?:Answer|Option|Hint|Choice|Distractor)\s*:\s*', '', text, flags=re.IGNORECASE)
        
        # 3. Strip surrounding quotes if the AI wrapped the entire string in them
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
            text = text[1:-1]
            
        return text.strip()

    def _normalize_math_text(self, text: str) -> str:
        return normalize_math_text(text, output_format=self._latex_output_format(), fix_latex=self.fix_latex)

    def _latex_output_format(self) -> str:
        if str(self.mathjax_format).lower() in {"inline", "dollar", "dollars"}:
            return "dollars"
        return "anki"

    def _fix_latex_span(self, span: str) -> str:
        # Note: We keep this for internal calls, but it's now just a pass-through to the library.
        # However, many methods in CardParser were private helpers for this.
        # Since they are no longer used by the main logic (which moved to the library),
        # we can remove them.
        try:
            from .latex_fixer.latex_fixer import _fix_latex_span
        except ImportError:
            return span
        return _fix_latex_span(span)

    def _convert_to_mathjax_tags(self, text: str) -> str:
        r"""Converts standard LaTeX delimiters \( \) and \[ \] to Anki's <anki-mathjax> tags."""
        if not isinstance(text, str):
            return text

        text = normalize_math_text(text, output_format="anki", fix_latex=self.fix_latex)
        
        # Replace \( ... \) and \[ ... \] with <anki-mathjax> ... </anki-mathjax>
        text = re.sub(r'\\\((.*?)\\\)', r'<anki-mathjax>\1</anki-mathjax>', text, flags=re.DOTALL)
        text = re.sub(r'\\\[(.*?)\\\]', r'<anki-mathjax>\1</anki-mathjax>', text, flags=re.DOTALL)
        return text

    def get_note_content(self, note, card=None) -> Tuple[str, str]:
        """Extracts front and back content for AI context.
        Uses the first field as Front and all others as Back context.
        For reversed cards (card.ord > 0 on non-cloze notes), reads the card
        template's qfmt to determine the actual front field and swaps accordingly."""
        model = note.model()
        model_name = model["name"].lower()
        fields = list(note.items())
        if not fields:
            return "", ""

        front = fields[0][1]
        back = ""

        # If it's a Cloze card, we focus on the specific cloze
        # Check both name and internal model type (1 = Cloze)
        if "cloze" in model_name or model.get("type") == 1:
            front, back, found = self._focus_current_cloze(front, card)
            if not found:
                return "", ""
        else:
            # Detect reversed card templates by inspecting the card's template qfmt.
            # For "Basic (and reversed card)", card.ord==1 uses the second template
            # which shows Field[1] on the front and Field[0] on the back.
            front_field_index = 0
            if card is not None:
                try:
                    model = note.model()
                    templates = model.get("tmpls", [])
                    card_ord = self._card_ord(card)
                    if card_ord is not None and card_ord < len(templates):
                        tmpl = templates[card_ord]
                        qfmt = tmpl.get("qfmt", "")
                        # Find which field name appears first in the question template.
                        # fields is a list of (field_name, value) tuples.
                        first_match_idx = None
                        first_match_pos = len(qfmt) + 1
                        for idx, (fname, _) in enumerate(fields):
                            # Search for field references like {{Field}}, {{type:Field}}, {{cloze:Field}}, etc., with optional spaces
                            pattern = re.compile(r'\{\{\s*(?:[^}]*?:)?\s*' + re.escape(fname) + r'\s*\}\}')
                            match = pattern.search(qfmt)
                            if match:
                                pos = match.start()
                                if pos < first_match_pos:
                                    first_match_pos = pos
                                    first_match_idx = idx
                        if first_match_idx is not None and first_match_idx != 0:
                            front_field_index = first_match_idx
                except Exception:
                    pass  # Fall back to default field[0] as front

            if front_field_index != 0:
                # Reversed: the front field is not field[0]
                front = fields[front_field_index][1]
                # The back field for a reversed card is typically the first field (index 0)
                back = fields[0][1] if len(fields) > 0 else ""
            else:
                front = fields[0][1]
                # In standard cards, only the front and back (index 0 and 1) fields are sent
                back = fields[1][1] if len(fields) > 1 else ""

        return self._clean_html(front), self._clean_html(back)


    def _clean_html(self, html_text: str) -> str:
        """Remove most HTML tags to reduce tokens and noise."""
        import os
        if not isinstance(html_text, str):
            html_text = str(html_text or "")
        
        # Remove scripts and styles
        html_text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
        
        # Aggressively remove AI-Hints blocks (JSON and container) including their content
        # to prevent existing hints from polluting the AI prompt context.
        html_text = re.sub(
            r'<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>', 
            "", 
            html_text, 
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert images to a textual placeholder with their source filename / alt text
        def replace_img(match):
            tag = match.group(0)
            src_match = re.search(r'src=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            alt_match = re.search(r'alt=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            
            src_val = os.path.basename(src_match.group(1)) if src_match else ""
            alt_val = alt_match.group(1) if alt_match else ""
            
            parts = []
            if alt_val:
                parts.append(alt_val)
            if src_val:
                parts.append(src_val)
            
            if parts:
                return " [Image: " + " - ".join(parts) + "] "
            return " [Image] "

        html_text = re.sub(r"<img\b[^>]*>", replace_img, html_text, flags=re.IGNORECASE)

        # Remove all other tags but keep content
        text = re.sub(r"<.*?>", " ", html_text)
        text = html.unescape(text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _split_cloze_content(self, content: str) -> Tuple[str, str]:
        """Splits content into (answer, hint) while being depth-aware of nested clozes."""
        depth = 0
        i = 0
        while i < len(content):
            if content.startswith("{{", i):
                depth += 1
                i += 2
            elif content.startswith("}}", i):
                depth -= 1
                i += 2
            elif content.startswith("::", i) and depth == 0:
                return content[:i], content[i+2:]
            else:
                i += 1
        return content, ""

    def _resolve_nested_clozes(self, text: str) -> str:
        """Recursively resolves clozes within an answer."""
        iteration_limit = 50
        while iteration_limit > 0:
            # Find the FIRST cloze to start resolving its depth
            match = re.search(r"\{\{c(\d+)::", text)
            if not match:
                break
            
            start_pos = match.start()
            search_pos = match.end()
            depth = 1
            
            found_end = False
            while search_pos < len(text):
                if text.startswith("{{", search_pos):
                    depth += 1
                    search_pos += 2
                elif text.startswith("}}", search_pos):
                    depth -= 1
                    if depth == 0:
                        # Found the end of THIS cloze
                        inner_content = text[start_pos+2:search_pos]
                        # Resolve its internal content (answer vs hint)
                        tag_parts = inner_content.split("::", 1)
                        if len(tag_parts) < 2:
                            answer = inner_content
                        else:
                            content_after_tag = tag_parts[1]
                            answer, _hint = self._split_cloze_content(content_after_tag)
                        
                        # Recurse on the resolved part in case it has MORE nested clozes
                        answer = self._resolve_nested_clozes(answer)
                        
                        text = text[:start_pos] + answer + text[search_pos+2:]
                        found_end = True
                        break
                    search_pos += 2
                else:
                    search_pos += 1
            
            if not found_end:
                # Malformed: strip the start to avoid loop
                text = text[:start_pos] + text[start_pos+2:]
            
            iteration_limit -= 1
        return text

    def _focus_current_cloze(self, text: str, card=None) -> Tuple[str, str, bool]:
        """Mark the cloze deletion for the current card and extract all active answers."""
        from .logger import logger
        cloze_number = self._card_ord(card)
        if cloze_number is None:
            return text, "", False
        cloze_number += 1
        
        logger.debug(f"AI-Hints CardParser focusing cloze #{cloze_number} (card.ord={self._card_ord(card)})")

        answers_map = {} # {original_pos: cleaned_ans}

        ACTIVE_MARKER_START = "@@@AI_HINTS_ACTIVE_START@@@"
        ACTIVE_MARKER_END = "@@@AI_HINTS_ACTIVE_END@@@"

        def resolve_cloze_match(match_text: str, start_pos_in_original: int) -> str:
            """Resolves a single {{c1::answer::hint}} block."""
            # Strip outer {{ and }}
            inner = match_text[2:-2]
            
            # Format: c1::Answer::Hint
            parts = inner.split("::", 1)
            if len(parts) < 2:
                return match_text
            
            tag = parts[0]
            content_after_tag = parts[1]
            answer, hint = self._split_cloze_content(content_after_tag)
                
            try:
                num_match = re.search(r"\d+", tag)
                number = int(num_match.group()) if num_match else 0
            except (ValueError, AttributeError):
                return match_text

            if number != cloze_number:
                return self._resolve_nested_clozes(answer)

            # This IS the active cloze.
            resolved_answer = self._resolve_nested_clozes(answer)
            cleaned_ans = self._clean_html(resolved_answer)
            answers_map[start_pos_in_original] = cleaned_ans
            
            res = f"{ACTIVE_MARKER_START}[...]"
            if hint:
                res += f" (existing hint: {hint})"
            res += ACTIVE_MARKER_END
            return res

        def process_recursive(content: str) -> str:
            """Iteratively resolves the innermost clozes first using depth-aware logic."""
            iteration_limit = 100
            while iteration_limit > 0:
                # Find ALL starting clozes
                matches = list(re.finditer(r"\{\{c(\d+)::", content))
                if not matches:
                    break
                
                # Take the LAST one (most likely innermost)
                match = matches[-1]
                
                depth = 1
                start_pos = match.start()
                search_pos = match.end()
                
                found_end = False
                while search_pos < len(content):
                    if content.startswith("{{", search_pos):
                        depth += 1
                        search_pos += 2
                    elif content.startswith("}}", search_pos):
                        depth -= 1
                        if depth == 0:
                            cloze_text = content[start_pos:search_pos+2]
                            resolved = resolve_cloze_match(cloze_text, start_pos)
                            content = content[:start_pos] + resolved + content[search_pos+2:]
                            found_end = True
                            break
                        search_pos += 2
                    else:
                        search_pos += 1
                
                if not found_end:
                    # Malformed: skip this start by temporarily masking it
                    content = content[:start_pos] + "MASKED_START" + content[start_pos+2:]
                    continue 
                
                iteration_limit -= 1
            
            content = content.replace("MASKED_START", "{{")
            content = content.replace(ACTIVE_MARKER_START, "Current cloze deletion: ")
            content = content.replace(ACTIVE_MARKER_END, "")
            return content

        focused_text = process_recursive(text)
        sorted_answers = [answers_map[k] for k in sorted(answers_map.keys())]
        cloze_found = len(answers_map) > 0
        return focused_text, " ; ".join(sorted_answers), cloze_found

    def update_note_with_hints(self, note, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None, skip_if_exists: bool = False) -> bool:
        """Appends or replaces the AI hints block in the target field."""
        if not data or (not data.get("hints") and not data.get("options") and not data.get("_skipped")):
            return False

        # Safety check: Abort if data exists and we were instructed not to overwrite
        if skip_if_exists:
            existing = self.find_hints_block(note, card)
            if existing:
                return False

        data = self.normalize_hint_data(data)

        # Determine the key for this card (e.g., 'c1' for cloze ord 0)
        card_key = None
        card_ord = self._card_ord(card)
        if card_ord is not None:
            card_key = f"c{card_ord + 1}"
        
        # Find target field
        field_name = self._find_target_field(note)
        if not field_name:
            # Fallback to last field if no target found
            note_keys = list(note.keys())
            if not note_keys:
                return False
            field_name = note_keys[-1]

        current_val = note[field_name]
        if not isinstance(current_val, str):
            current_val = str(current_val or "")
        
        new_val = self._update_json_block_in_field(current_val, data, card_key, toggles, card, note)
        note[field_name] = new_val
        return True

    def _update_json_block_in_field(self, current_val: str, new_data: Dict[str, List[str]], card_key: Optional[str], toggles: Dict[str, bool], card=None, note=None) -> str:
        # 1. First, try to find ANY existing block (JSON or HTML) that matches THIS specific card.
        # This is the most surgical update.
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        matches = list(pattern.finditer(current_val))
        
        # Priority 1: Update block that specifically matches this card
        for match in matches:
            block_html = match.group(0)
            if self._block_matches_card(block_html, card):
                # Found it! Now check if it's JSON or HTML.
                if self.json_class in block_html:
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if not isinstance(parsed, dict): parsed = {}
                        
                        # Merge or set data
                        if card_key:
                             # Ensure it is keyed
                             if not self._is_keyed_payload(parsed):
                                  if "hints" in parsed or "options" in parsed:
                                       parsed = {"c1": parsed}
                                  else:
                                       parsed = {}
                             
                             parsed[card_key] = new_data
                        else:
                             parsed.update(new_data)
                             
                        new_payload = self.serialize_json_payload(parsed)
                        new_attrs = self._build_attrs(toggles, card if not card_key else None)
                        new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                        return current_val[:match.start()] + new_block + current_val[match.end():]
                    except:
                        pass
                
                # If it matched card but was HTML-only or failed JSON parse, replace it entirely.
                new_block = self.build_hints_block({card_key: new_data} if card_key else new_data, toggles, card)
                return current_val[:match.start()] + new_block + current_val[match.end():]

        # Priority 2: Update ANY universal or legacy block found in the note
        if card_key:
            for match in matches:
                block_html = match.group(0)
                
                # If it's a JSON block, parse and merge
                if self.json_class in block_html:
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if isinstance(parsed, dict):
                            # Ensure it's keyed format
                            if not self._is_keyed_payload(parsed):
                                if "hints" in parsed or "options" in parsed:
                                    parsed = {"c1": parsed}
                                else:
                                    parsed = {}
                                
                                # (obsolete/polluted cloze keys purge removed)
                            
                            # Merge data
                            parsed[card_key] = new_data
                            new_payload = self.serialize_json_payload(parsed)
                            new_attrs = self._build_attrs(toggles, None) # keep universal
                            new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                            return current_val[:match.start()] + new_block + current_val[match.end():]
                    except:
                        pass
                
                # If it's an HTML block, extract its data, convert to JSON, and merge!
                elif self.container_class in block_html:
                    legacy_data = self._extract_data_from_html_block(block_html)
                    if legacy_data:
                        # Determine its original key
                        block_ord = self._data_attr(block_html, "data-ai-hints-card-ord")
                        legacy_key = f"c{int(block_ord) + 1}" if block_ord else "c1"
                        
                        parsed = {legacy_key: legacy_data}
                        parsed[card_key] = new_data
                        
                        new_payload = self.serialize_json_payload(parsed)
                        new_attrs = self._build_attrs(toggles, None) # universal
                        new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                        return current_val[:match.start()] + new_block + current_val[match.end():]

        # 3. No match found: Append new block
        payload = {card_key: new_data} if card_key else new_data
        content_block = self.build_hints_block(payload, toggles, card if not card_key else None)
        if not current_val.strip():
            return content_block
        return current_val.strip() + "\n\n" + content_block

    def build_hints_block(self, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> str:
        """Build the persisted/injected hints block as invisible JSON."""
        data = self.normalize_hint_data(data)
        attrs = self._build_attrs(toggles, card)
        payload = self.serialize_json_payload(data)
        return f'<div class="{self.json_class}" {attrs} style="display:none">{payload}</div>'

    def _find_target_field(self, note) -> Optional[str]:
        # User requested to ALWAYS save to the first field of all cards
        # because other fields might not render in front of card.
        note_keys = list(note.keys())
        if not note_keys:
            return None
        return note_keys[0]

    def _build_attrs(self, toggles: Dict[str, bool] = None, card=None) -> str:
        attrs = [f'data-ai-hints-addon-id="2119980872"', 'contenteditable="false"']
        if toggles:
            attrs.extend([
                f'data-show-hints="{str(toggles.get("show_hints_button", True)).lower()}"',
                f'data-show-options="{str(toggles.get("show_options_button", True)).lower()}"',
            ])

        card_id = self._card_attr(card, "id")
        card_ord = self._card_ord(card)
        if card_id:
            attrs.append(f'data-ai-hints-card-id="{html.escape(card_id, quote=True)}"')
        if card_ord is not None:
            attrs.append(f'data-ai-hints-card-ord="{card_ord}"')
        return " ".join(attrs)

    def _card_attr(self, card, attr: str) -> str:
        if card is None:
            return ""
        value = getattr(card, attr, "")
        if callable(value):
            return ""
        text = str(value).strip()
        if not text or text.startswith("<"):
            return ""
        return text

    def _card_ord(self, card) -> Optional[int]:
        if card is None:
            return None
        value = getattr(card, "ord", None)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def find_hints_block(self, note, card=None) -> Optional[str]:
        """Searches all fields of the note for an AI hints block matching the card."""
        # More flexible regex for class matching (allows any order of classes)
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        # Anki Note objects have a .fields attribute (list of strings)
        fields = getattr(note, "fields", [])
        if not fields and hasattr(note, "values"):
            try:
                fields = list(note.values())
            except Exception:
                fields = []
        
        for f_val in fields:
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                block = match.group(0)
                # Check if this block is scoped to the card
                if self._block_matches_card(block, card):
                    # Check if the block actually HAS data for this specific card
                    if self._json_block_has_data_for_card(block, match.group(1), card, note):
                        return block
        return None

    def find_all_hints_blocks(self, note) -> List[str]:
        """Extracts all AI hints blocks from all fields of the note."""
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        blocks = []
        fields = list(note.values()) if hasattr(note, "values") else getattr(note, "fields", [])
        for f_val in fields:
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                blocks.append(match.group(0))
        return blocks

    def get_orphaned_hints(self, note) -> List[Tuple[str, str, Any]]:
        """Scans the note and returns a list of orphaned hints.
        Each entry is a tuple: (block_html, key, payload)
        """
        raw_blocks = self.find_all_hints_blocks(note)
        if not raw_blocks:
            return []

        # Get active cards and their keys
        if hasattr(note, "cards") and callable(note.cards):
            active_ords = {c.ord for c in note.cards()}
        else:
            active_ords = None
        
        # Check if Cloze note
        model = note.model()
        model_name = model["name"].lower() if model else ""
        is_cloze = model and ("cloze" in model_name or model.get("type") == 1)

        if is_cloze:
            # Find all cloze numbers actually present in the note fields
            active_cloze_nums = set()
            fields_to_scan = []
            if hasattr(note, "values"):
                fields_to_scan = note.values()
            elif hasattr(note, "items"):
                fields_to_scan = [v for k, v in note.items()]
            
            for field_val in fields_to_scan:
                if isinstance(field_val, str):
                    for m in re.finditer(r'(?i)\{\{\s*c(\d+)\s*::', field_val):
                        active_cloze_nums.add(int(m.group(1)))
            if active_ords is not None:
                valid_keys = {f"c{num}" for num in active_cloze_nums if (num - 1) in active_ords}
            else:
                valid_keys = {f"c{num}" for num in active_cloze_nums}
        else:
            if active_ords is not None:
                valid_keys = {f"c{ord + 1}" for ord in active_ords}
            else:
                valid_keys = {"c1"} # default for standard note

        note_orphans = []
        for block in raw_blocks:
            if self.json_class in block:
                # Use re.search to extract the JSON payload
                m = re.search(
                    r'<div\b[^>]*class=["\'][^"\']*ai-hints-json[^"\']*["\'][^>]*>(.*?)</div>',
                    block, re.DOTALL | re.IGNORECASE
                )
                if m:
                    raw = html.unescape(m.group(1) or "")
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(parsed, dict) and self._is_keyed_payload(parsed):
                        for key in list(parsed.keys()):
                            if re.fullmatch(r"c\d+", str(key)) and key not in valid_keys:
                                note_orphans.append((block, key, parsed[key]))
        return note_orphans


    def _extract_all_hints_from_fields(self, note) -> List[Dict[str, Any]]:
        """Scans all fields and returns a list of parsed data objects with metadata."""
        all_data = []
        for f_name in note.keys():
            data = self._extract_hints_from_field(note[f_name])
            if data:
                all_data.extend(data)
        return all_data

    def _extract_hints_from_field(self, field_val: str, card_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extracts AI data from a single field string."""
        if not isinstance(field_val, str):
            return []
            
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        extracted = []
        for match in pattern.finditer(field_val):
            block = match.group(0)
            content = match.group(1)
            parsed = None
            try:
                parsed = self._parse_json_payload(content)
            except Exception:
                # Fallback: Attempt to extract from HTML structure
                parsed = self._extract_data_from_html_block(block)
                
            if not parsed:
                continue

            # Determine the key for this block if possible
            # We check the block attributes directly
            block_ord = self._data_attr(block, "data-ai-hints-card-ord")
            current_card_key = card_key
            if not current_card_key and block_ord:
                current_card_key = f"c{int(block_ord) + 1}"

            if self._is_keyed_payload(parsed):
                if current_card_key:
                    if current_card_key in parsed:
                        extracted.append({"data": parsed[current_card_key], "card_key": current_card_key, "toggles": self._extract_toggles_from_block(block)})
                else:
                    for k, v in parsed.items():
                        extracted.append({"data": v, "card_key": k, "toggles": self._extract_toggles_from_block(block)})
            else:
                extracted.append({"data": parsed, "card_key": current_card_key, "toggles": self._extract_toggles_from_block(block)})
                    
        return extracted

    def _extract_data_from_html_block(self, block_html: str) -> Optional[Dict[str, List[str]]]:
        """Heuristic extraction of hint/option data from rendered HTML containers."""
        hints = []
        options = []
        
        # Extract hints
        hint_list_match = re.search(r'class=["\']ai-hints-hint-list["\'][^>]*>(.*?)</ul>', block_html, re.DOTALL)
        if hint_list_match:
            hints = [re.sub(r'<[^>]+>', '', li).strip() for li in re.findall(r'<li>(.*?)</li>', hint_list_match.group(1), re.DOTALL)]
            
        # Extract options
        opt_list_match = re.search(r'class=["\']ai-hints-list["\'][^>]*>(.*?)</ul>', block_html, re.DOTALL)
        if opt_list_match:
            options = [re.sub(r'<[^>]+>', '', li).strip() for li in re.findall(r'<li>(.*?)</li>', opt_list_match.group(1), re.DOTALL)]
            
        if not hints and not options:
            return None
            
        return {"hints": hints, "options": options}

    def _extract_toggles_from_block(self, block_html: str) -> Dict[str, bool]:
        """Reads data attributes for visibility toggles."""
        return {
            "show_hints_button": self._data_attr(block_html, "data-show-hints") != "false",
            "show_options_button": self._data_attr(block_html, "data-show-options") != "false"
        }

    def _remove_all_hints_from_fields(self, note) -> bool:
        """Forcefully removes all AI hints blocks from all fields of the note."""
        pattern = re.compile(
            r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*',
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleared = False
        for f_name in note.keys():
            val = note[f_name]
            if not isinstance(val, str):
                continue
            new_val = re.sub(pattern, "", val)
            if new_val != val:
                note[f_name] = new_val.strip()
                cleared = True
        return cleared

    def unskip_hints_from_note(self, note, card=None) -> bool:
        """Removes only the skipped AI hints indicators matching the card from all fields (both JSON and HTML blocks)."""
        card_ord = self._card_ord(card)
        card_key = f"c{card_ord + 1}" if card_ord is not None else None
        cleared = False

        # Regex to match div blocks of either class
        ws_pattern = r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*'
        pattern = re.compile(
            rf'{ws_pattern}<div\b[^>]*class=["\']([^"\']*)(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>{ws_pattern}',
            flags=re.DOTALL | re.IGNORECASE,
        )

        for f_name in note.keys():
            current_val = note[f_name]
            if not isinstance(current_val, str):
                continue

            new_val = current_val
            field_cleared = False
            matches = list(pattern.finditer(current_val))

            for match in reversed(matches):
                block_html = match.group(0)
                class_str = match.group(1)
                
                # Check if it matches this card
                if not self._block_matches_card(block_html, card):
                    continue

                # Case A: JSON block
                if self.json_class in block_html:
                    try:
                        raw_payload = match.group(2)
                        parsed = self._parse_json_payload(raw_payload)
                        if isinstance(parsed, dict):
                            # Keyed JSON format
                            if self._is_keyed_payload(parsed):
                                if card_key and card_key in parsed:
                                    card_data = parsed[card_key]
                                    if isinstance(card_data, dict) and "_skipped" in card_data:
                                        # Only delete the "_skipped" attribute, preserve other data (hints/options)
                                        del card_data["_skipped"]
                                        # If the card's data is now completely empty (meaning no hints or options),
                                        # and there are no other cards with active hints/options in this JSON,
                                        # we can delete the block. Otherwise, save the updated JSON block.
                                        has_active_data = False
                                        for k, v in parsed.items():
                                            if isinstance(v, dict) and (v.get("hints") or v.get("options") or v.get("_skipped")):
                                                has_active_data = True
                                                break
                                                
                                        if has_active_data:
                                            new_payload = self.serialize_json_payload(parsed)
                                            new_val = new_val[:match.start(2)] + new_payload + new_val[match.end(2):]
                                            field_cleared = True
                                        else:
                                            # No active cards left in this JSON block, remove entire block
                                            new_val = new_val[:match.start()] + new_val[match.end():]
                                            field_cleared = True
                            else:
                                # Legacy/Universal block
                                if "_skipped" in parsed:
                                    del parsed["_skipped"]
                                    # If it still has other data, update the JSON. Otherwise, remove the block.
                                    if parsed.get("hints") or parsed.get("options"):
                                        new_payload = self.serialize_json_payload(parsed)
                                        new_val = new_val[:match.start(2)] + new_payload + new_val[match.end(2):]
                                        field_cleared = True
                                    else:
                                        new_val = new_val[:match.start()] + new_val[match.end():]
                                        field_cleared = True
                    except Exception as e:
                        logger.error(f"Error parsing JSON block during unskip: {e}")

                # Case B: HTML block
                elif self.container_class in block_html:
                    if 'data-ai-hints-skipped="true"' in block_html or "data-ai-hints-skipped='true'" in block_html:
                        # Remove the entire HTML block
                        new_val = new_val[:match.start()] + new_val[match.end():]
                        field_cleared = True

            if field_cleared:
                note[f_name] = new_val
                cleared = True

        return cleared

    def clear_hints_from_note(self, note, card=None) -> bool:
        """Removes AI hints blocks matching the card from all fields, including HTML line breaks."""
        # Regex updated to match leading/trailing whitespace, <br> tags, and &nbsp;
        # We use a greedy match for surrounding whitespace to clean up as much as possible
        ws_pattern = r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*'
        pattern = re.compile(
            rf'{ws_pattern}<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>{ws_pattern}',
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleared = False
        card_ord = self._card_ord(card)
        card_key = f"c{card_ord + 1}" if card_ord is not None else None

        for f_name in note.keys():
            current_val = note[f_name]
            if not isinstance(current_val, str):
                continue
            
            new_val = current_val
            field_cleared = False
            
            # 1. Clean standard div container blocks
            matches = list(pattern.finditer(current_val))
            # Work backwards to avoid offset issues
            for match in reversed(matches):
                block_html = match.group(0)
                
                if self.json_class in block_html and card_key:
                    # Try partial clear from keyed JSON
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if isinstance(parsed, dict) and card_key in parsed:
                            del parsed[card_key]
                            if parsed:
                                # Re-save updated JSON
                                new_payload = self.serialize_json_payload(parsed)
                                # We only replace the inner payload, keep the outer div
                                new_val = new_val[:match.start(1)] + new_payload + new_val[match.end(1):]
                                field_cleared = True
                                continue
                            # Else if empty, fall through to full removal
                        elif isinstance(parsed, dict) and self._is_keyed_payload(parsed):
                            continue
                    except Exception:
                        pass

                if self._block_matches_card(block_html, card):
                    # Replace the entire matched block (including surrounding <br>/whitespace) with a single newline or nothing
                    new_val = new_val[:match.start()] + new_val[match.end():]
                    field_cleared = True

            # 2. Clean naked/raw JSON strings left behind by older versions or failures
            def find_json_candidates(text):
                candidates = []
                start = -1
                depth = 0
                for i, char in enumerate(text):
                    if char == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif char == '}':
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and start != -1:
                                candidates.append((start, i + 1, text[start:i+1]))
                return candidates

            import json
            for start_idx, end_idx, candidate in reversed(find_json_candidates(new_val)):
                try:
                    # Clean candidate of internal HTML tags for parsing safety
                    clean_candidate = re.sub(r'<[^>]+>', '', candidate)
                    parsed = json.loads(clean_candidate)
                    if isinstance(parsed, dict):
                        is_ai_hints = False
                        is_keyed = False
                        if "hints" in parsed or "options" in parsed or "correct_answer" in parsed:
                            is_ai_hints = True
                        elif any(isinstance(val, dict) and ("hints" in val or "options" in val) for val in parsed.values()):
                            is_ai_hints = True
                            is_keyed = True
                        
                        if is_ai_hints:
                            if is_keyed:
                                if card_key and card_key in parsed:
                                    del parsed[card_key]
                                    if parsed:
                                        # Re-serialize and replace inner content
                                        new_payload = json.dumps(parsed, indent=2)
                                        new_val = new_val[:start_idx] + new_payload + new_val[end_idx:]
                                        field_cleared = True
                                        continue
                                else:
                                    # Key not in payload, do not touch this block
                                    continue
                            
                            # Otherwise full removal including surrounding whitespace/HTML linebreaks
                            left_str = new_val[:start_idx]
                            right_str = new_val[end_idx:]
                            
                            left_str = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', left_str, flags=re.IGNORECASE)
                            right_str = re.sub(r'^(?:<br\s*/?>|\s|&nbsp;)+', '', right_str, flags=re.IGNORECASE)
                            
                            new_val = left_str + right_str
                            field_cleared = True
                except Exception:
                    pass
            
            if field_cleared:
                # Systematic cleanup of multiple <br> tags at the end of the field
                new_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', new_val, flags=re.IGNORECASE)
                note[f_name] = new_val.strip()
                cleared = True
        
        return cleared

    def remove_warning_hint_from_note(self, note, card=None) -> bool:
        """Finds any hints block on the note matching the card, and filters out
        any hint containing a warning (i.e. '⚠️').
        Returns True if a warning was found and removed, False otherwise.
        """
        card_ord = self._card_ord(card)
        card_key = f"c{card_ord + 1}" if card_ord is not None else None
        
        modified = False
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )

        for f_name in note.keys():
            current_val = note[f_name]
            if not isinstance(current_val, str):
                continue
                
            matches = list(pattern.finditer(current_val))
            field_modified = False
            new_val = current_val
            
            # Work backwards to avoid offset issues
            for match in reversed(matches):
                block_html = match.group(0)
                if self._block_matches_card(block_html, card):
                    if self.json_class in block_html:
                        try:
                            raw_payload = match.group(1)
                            parsed = self._parse_json_payload(raw_payload)
                            if not isinstance(parsed, dict):
                                continue
                                
                            block_modified = False
                            # If keyed format
                            if self._is_keyed_payload(parsed):
                                if card_key and card_key in parsed:
                                    data = parsed[card_key]
                                    if isinstance(data, dict) and "hints" in data:
                                        orig_len = len(data["hints"])
                                        data["hints"] = [h for h in data["hints"] if "⚠️" not in str(h) and "⚠" not in str(h)]
                                        if len(data["hints"]) < orig_len:
                                            block_modified = True
                            else:
                                # Not keyed format
                                if "hints" in parsed:
                                    orig_len = len(parsed["hints"])
                                    parsed["hints"] = [h for h in parsed["hints"] if "⚠️" not in str(h) and "⚠" not in str(h)]
                                    if len(parsed["hints"]) < orig_len:
                                        block_modified = True
                                        
                            if block_modified:
                                new_payload = self.serialize_json_payload(parsed)
                                new_attrs = block_html.split(">", 1)[0].replace(f'<div class="{self.json_class}"', "").strip()
                                new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                                new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                                field_modified = True
                                modified = True
                        except Exception as e:
                            logger.error(f"Error removing warning from JSON: {e}")
                    else:
                        # HTML format
                        # Warnings are inside list items. Let's find <li> elements containing ⚠️ or ⚠
                        li_pattern = re.compile(r'<li\b[^>]*>[^<]*(?:⚠️|⚠).*?</li>', flags=re.DOTALL | re.IGNORECASE)
                        new_block_content, count = li_pattern.subn('', match.group(1))
                        if count > 0:
                            # Rebuild HTML block
                            new_block = block_html.replace(match.group(1), new_block_content)
                            new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                            field_modified = True
                            modified = True
            
            if field_modified:
                note[f_name] = new_val.strip()
                
        return modified

    def _replace_or_append_block(self, current_val: str, content_block: str, card=None) -> str:
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        matches = list(pattern.finditer(current_val))
        if not matches:
            return current_val + "\n" + content_block

        for match in matches:
            if self._block_matches_card(match.group(0), card):
                return current_val[:match.start()] + content_block + current_val[match.end():]

        for match in matches:
            if not self._block_has_card_scope(match.group(0)):
                return current_val[:match.start()] + content_block + current_val[match.end():]

        return current_val.strip() + "\n\n" + content_block

    def _block_matches_card(self, block: str, card=None) -> bool:
        if card is None:
            return not self._block_has_card_scope(block)

        card_id = self._card_attr(card, "id")
        card_ord = self._card_ord(card)

        block_id = self._data_attr(block, "data-ai-hints-card-id")
        if card_id and block_id:
            return card_id == block_id

        block_ord = self._data_attr(block, "data-ai-hints-card-ord")
        if card_ord is not None and block_ord:
            return str(card_ord) == block_ord

        # If block has no specific scope, it matches all cards of the note
        return not self._block_has_card_scope(block)

    def _block_has_card_scope(self, block: str) -> bool:
        return bool(
            self._data_attr(block, "data-ai-hints-card-id")
            or self._data_attr(block, "data-ai-hints-card-ord")
        )

    def _data_attr(self, block: str, name: str) -> str:
        match = re.search(rf'\b{re.escape(name)}\s*=\s*["\']([^"\']*)["\']', block, flags=re.IGNORECASE)
        return html.unescape(match.group(1)) if match else ""



    def _parse_json_payload(self, raw_payload: str) -> Any:
        if not raw_payload:
            return {}
        # Clean up any HTML line breaks, divs, p tags, or styling tags that Anki's editor might have inserted
        cleaned = raw_payload.replace("&nbsp;", " ").replace("\xa0", " ")
        cleaned = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*\b[^>]*>', '\n', cleaned)
        parsed = json.loads(html.unescape(cleaned))

        def repair_val(val: Any) -> Any:
            if isinstance(val, dict):
                return {k: repair_val(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [repair_val(item) for item in val]
            elif isinstance(val, str):
                return repair_latex_control_chars(val)
            return val

        return repair_val(parsed)

    def _is_keyed_payload(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        if "hints" in payload or "options" in payload or "_skipped" in payload:
            return False
        return any(re.fullmatch(r"c\d+", str(key)) for key in payload.keys())

    def _json_block_has_data_for_card(self, block: str, raw_payload: str, card=None, note=None) -> bool:
        if self.json_class not in block:
            # HTML-only blocks always count as having data (we don't know what's in them)
            return True

        card_ord = self._card_ord(card)
        
        try:
            parsed = self._parse_json_payload(raw_payload)
        except Exception:
            # Corrupt JSON: count as NO data so we can replace/append
            return False

        if not isinstance(parsed, dict) or not parsed:
            return False

        if self._is_keyed_payload(parsed):
            if card_ord is None:
                return any(
                    isinstance(val, dict) and (bool(val.get("hints")) or bool(val.get("options")) or bool(val.get("_skipped")))
                    for val in parsed.values()
                )
            card_key = f"c{card_ord + 1}"
            if card_key not in parsed:
                return False
            card_data = parsed[card_key]
            if not isinstance(card_data, dict):
                return False
            return bool(card_data.get("hints")) or bool(card_data.get("options")) or bool(card_data.get("_skipped"))
            
        # Legacy/Universal block: check for hints/options
        has_hints = bool(parsed.get("hints")) or bool(parsed.get("options")) or bool(parsed.get("_skipped"))
        
        if (
            has_hints
            and not self._block_has_card_scope(block)
            and card_ord is not None
            and card_ord > 0
        ):
            # Legacy blocks only match c1
            return False
            
        return has_hints

    def _build_html_block(self, data: Dict[str, List[str]], attrs: str = "") -> str:
        if data.get("_skipped"):
             return f'<div class="{self.container_class}" {attrs} data-ai-hints-skipped="true"><hr><i>AI generation skipped for this card.</i></div>'

        hints = data.get("hints", [])
        options = data.get("options", [])
        
        hints_html = ""
        if hints:
            items = "".join([f"<li>{self._safe_hint_item_html(h)}</li>" for h in hints])
            hints_html = f'<b>AI Hints:</b><br><ul class="ai-hints-hint-list">{items}</ul>'
            
        options_html = ""
        if options:
            items = "".join([f"<li>{self._safe_hint_item_html(o)}</li>" for o in options])
            options_html = f'<b>AI Options:</b><br><ul class="ai-hints-list">{items}</ul>'
            
        return f"""
<div class="{self.container_class}" {attrs}>
    <hr>
    {hints_html}
    {options_html}
</div>
"""

    def _safe_hint_item_html(self, value) -> str:
        escaped = html.escape(str(value), quote=True)
        escaped = re.sub(r'&lt;(anki-mathjax)&gt;', r'<\1>', escaped, flags=re.IGNORECASE)
        escaped = re.sub(r'&lt;/(anki-mathjax)&gt;', r'</\1>', escaped, flags=re.IGNORECASE)
        return escaped

    def serialize_json_payload(self, data: dict) -> str:
        """Serializes JSON payload with pretty 2-space indentation, no ASCII encoding, and HTML escaping."""
        pretty_json = json.dumps(data, indent=2, ensure_ascii=False)
        return html.escape(pretty_json, quote=False)

    def format_unformatted_blocks_in_note(self, note, card=None) -> bool:
        """
        Scans all fields of the note for any JSON hints blocks.
        If a block is flat (legacy) or unformatted (compact/escaped), 
        it migrates/formats it, saves the note, and returns True.
        """
        fields = list(note.keys()) if hasattr(note, "keys") else []
        if not fields:
            return False
            
        note_changed = False
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*{self.json_class}[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        for f_name in fields:
            val = note[f_name]
            if not isinstance(val, str) or self.json_class not in val:
                continue
                
            new_val = val
            matches = list(pattern.finditer(val))
            for match in reversed(matches):
                block_html = match.group(0)
                raw_payload = match.group(1)
                try:
                    parsed = self._parse_json_payload(raw_payload)
                    if not isinstance(parsed, dict) or not parsed:
                        continue
                        
                    # 1. Check if it's a legacy flat block (no keys like c1, c2)
                    is_flat = not self._is_keyed_payload(parsed)
                    if is_flat:
                        parsed = {"c1": parsed}
                        
                    # 2. Serialize to pretty format
                    formatted_payload = self.serialize_json_payload(parsed)
                    
                    # 3. If either it was flat, or raw_payload has unicode escapes, or has different whitespace:
                    if is_flat or raw_payload != formatted_payload:
                        # Rebuild the div block
                        new_val = new_val[:match.start(1)] + formatted_payload + new_val[match.end(1):]
                        note_changed = True
                except Exception as e:
                    from .logger import logger
                    logger.error(f"Error checking/formatting JSON block: {e}")
                    
            if note_changed:
                note[f_name] = new_val
                
        return note_changed
