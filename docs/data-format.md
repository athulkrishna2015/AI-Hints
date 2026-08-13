# AI-Hints Data & Storage Format

When AI-Hints generates hints and options for a card, it stores the results in a hidden JSON block embedded in your note. This page explains what that data is and how it's used.

## Example Payload

```json
{
  "hints": ["2024 ലെ ടി 20 ലോകകപ്പ് വിജയികൾ ഇന്ത്യയായിരുന്നു.", "..."],
  "options": ["ഇന്ത്യ", "ഇംഗ്ലണ്ട്", "ഓസ്ട്രേലിയ", "ദക്ഷിണാഫ്രിക്ക", "പാകിസ്ഥാൻ"],
  "correct_answer": "ഇന്ത്യ",
  "_provider": "cerebras",
  "_model": "zai-glm-4.7",
  "_generated_at": "2026-08-12 17:46:16",
  "_generation_type": "batch",
  "_src": "ഇന്ത്യ"
}
```

## What Each Field Does

| Field | Purpose |
|-------|---------|
| `hints` | The generated hint list, rendered in the collapsible Hints panel. |
| `options` | The MCQ options shown to you (with distractors), rendered in the Options panel. |
| `correct_answer` | The **current/displayed** correct answer. Used to render the correct option and highlight it green. This value is **mutable** — inline-editing an option may change it. |
| `_provider` / `_model` | Which provider and model generated the data. |
| `_generated_at` | Timestamp of generation (used by time-based auto-regeneration). |
| `_generation_type` | How it was generated (`manual`, `auto`, `pregen`, `batch`, etc.). |
| `_src` | An **immutable snapshot** of the cloze answer at generation time, used only for stale-hint detection. |

## Why `correct_answer` and `_src` Look the Same

They are **not** duplicates — they serve different purposes:

- **`correct_answer`** can change (e.g. you edit the options inline) and drives the on-card display.
- **`_src`** is frozen at generation time. Stale detection compares the *current* cloze text against `_src`, never against your possibly-edited `correct_answer`. This ensures manual edits to hints/options are **never mistaken for stale data and wiped**. If a cloze's text was genuinely changed (e.g. copy-pasted to a different answer), the data is detected as stale and regenerated.

On a card where you haven't edited anything, the two are equal — hence you may see the same answer stored twice.

## Where the Data Lives

- Data is stored in a hidden `<div class="ai-hints-json">` block inside your note, so it survives and syncs like any other note content.
- Use the **Show JSON** shortcut (`Alt+6` by default) or the 📝 **Show JSON** button to inspect a card's payload during review.
- The **Advanced → Convert HTML to Hidden JSON** tool converts legacy visible HTML hint boxes into this hidden JSON format.

## Staleness & Auto-Regeneration Rules

AI-Hints can automatically regenerate data when it becomes stale:

- **Generated version older** than a threshold.
- **Generated time older** than a date.
- **Note modified** after generation.
- **Cloze text changed** vs. the `_src` snapshot.

See [Configuration → Auto-Show & Generation](configuration.md) for the toggles that control these.