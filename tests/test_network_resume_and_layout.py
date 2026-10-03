"""Regression checks for the v8.3.3 fixes.

1. Network monitor polls fast while offline (so generation resumes quickly).
2. A card paused by the offline gate is retried when connectivity returns.
3. The `+ Add` row is out of flow (does not push card content down).
4. A failed/offline attempt restores the button's resting label, not the
   optimistic "Generating... (Stop)" text left behind by the click handler.
"""

import os
import re
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEMPLATE_JS = os.path.join(PROJECT_ROOT, "addon", "web", "template.js")


def _read_template():
    with open(TEMPLATE_JS, "r", encoding="utf-8") as f:
        return f.read()


class NetworkMonitorPollTests(unittest.TestCase):
    def test_offline_state_polls_faster_than_online(self):
        from addon import ai_client

        with open(ai_client.__file__, encoding="utf-8") as f:
            src = f.read()
        monitor = re.search(r"def monitor\(\):(.*?)\n\n", src, re.DOTALL)
        self.assertIsNotNone(monitor, "monitor() not found in ai_client.py")
        body = monitor.group(1)
        self.assertRegex(
            body,
            r"_sleep_event\.wait\(\s*3\s+if\s+_NETWORK_STATE\[.online.\]\s+is\s+False\s+else\s+30\s*\)",
            "monitor must poll every ~3s while offline instead of a flat 30s",
        )


class NetworkResumeTests(unittest.TestCase):
    def setUp(self):
        from addon import reviewer_hooks

        self.rh = reviewer_hooks
        self.rh._network_paused_card = None
        self.rh._generating_card_ids.clear()
        # Bare envs import the addon with mw=None; the resume path reads
        # mw.reviewer, so give it a reviewer double for the duration of the test.
        self._prev = {
            name: getattr(reviewer_hooks, name)
            for name in ("mw", "generate_hints", "_trigger_next_pregeneration")
        }
        reviewer_hooks.mw = MagicMock()
        reviewer_hooks.mw.reviewer.card = None

    def tearDown(self):
        # Restore every patched module global: leaving a MagicMock behind would
        # silently break the next test module in a full discover run. Mutate the
        # set in place rather than rebinding it — other modules hold their own
        # reference to the same object.
        for name, value in self._prev.items():
            setattr(self.rh, name, value)
        self.rh._generating_card_ids.clear()

    def test_resume_restarts_paused_card_instead_of_pregeneration(self):
        rh = self.rh
        card = MagicMock()
        card.id = 4242
        rh.mw.reviewer.card = card
        rh._network_paused_card = 4242
        rh.generate_hints = MagicMock()
        rh._trigger_next_pregeneration = MagicMock()

        rh._resume_generation_after_network_return()

        rh.generate_hints.assert_called_once()
        self.assertEqual(rh.generate_hints.call_args.kwargs["card"].id, 4242)
        rh._trigger_next_pregeneration.assert_not_called()

    def test_resume_falls_back_to_pregeneration_for_other_cards(self):
        rh = self.rh
        card = MagicMock()
        card.id = 1
        rh.mw.reviewer.card = card
        rh._network_paused_card = 4242
        rh.generate_hints = MagicMock()
        rh._trigger_next_pregeneration = MagicMock()

        rh._resume_generation_after_network_return()

        rh.generate_hints.assert_not_called()
        rh._trigger_next_pregeneration.assert_called_once()

    def test_resume_does_not_duplicate_an_in_flight_generation(self):
        rh = self.rh
        card = MagicMock()
        card.id = 4242
        rh.mw.reviewer.card = card
        rh._network_paused_card = 4242
        rh._generating_card_ids.add(4242)
        rh.generate_hints = MagicMock()
        rh._trigger_next_pregeneration = MagicMock()

        rh._resume_generation_after_network_return()

        rh.generate_hints.assert_not_called()
        rh._trigger_next_pregeneration.assert_called_once()


class AddRowLayoutTests(unittest.TestCase):
    def setUp(self):
        self.js = _read_template()

    def test_add_chip_shares_the_header_line_with_the_label(self):
        self.assertRegex(
            self.js,
            r"\.ai-hints-head \{ display: flex; align-items: center; justify-content: flex-start;",
            "the chip must ride in a flex header row, starting right after the label",
        )
        self.assertRegex(
            self.js,
            r"\.ai-hints-ctrl-active \.ai-hints-add-item \{ display: inline-block;",
            "the chip must flow inline on the label's line, not take its own row",
        )
        self.assertRegex(
            self.js,
            r"head\.appendChild\(addLi\);",
            "the + Add chip must be appended to the header row",
        )
        self.assertNotRegex(
            self.js,
            r"list\.appendChild\(addLi\);",
            "the + Add chip must not live inside the <ul> (it pushed content down)",
        )

    def test_labelless_header_costs_no_height(self):
        self.assertRegex(
            self.js,
            r"\.ai-hints-head--bare \{[^}]*height: 0;",
            "a section without a label must collapse its header row to zero height",
        )

    def test_add_chip_stays_visible_while_editing(self):
        self.assertRegex(
            self.js,
            r"\.ai-hints-add-item\.ai-hints-editing \{\s*display: block;",
            "editing add chip must remain visible after Ctrl is released",
        )

    def test_editing_chip_is_out_of_flow(self):
        block = re.search(
            r"\.ai-hints-add-item\.ai-hints-editing \{(.*?)\}", self.js, re.DOTALL
        )
        self.assertIsNotNone(block)
        self.assertIn("position: absolute", block.group(1))


class GeneratingButtonRestoreTests(unittest.TestCase):
    def setUp(self):
        self.js = _read_template()

    def test_rest_label_is_recorded_on_the_button(self):
        self.assertRegex(
            self.js,
            r"genBtn\.dataset\.restLabel = genBtn\.textContent;",
            "button must record its resting label before the click handler overwrites it",
        )

    def test_failed_offline_restore_uses_rest_label(self):
        block = re.search(
            r"if \(isThisCard && \(status === 'Failed' \|\| status === 'Offline'\)\) \{(.*?)\n                    \}",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(block, "Failed/Offline restore branch not found")
        self.assertIn(
            "btn.dataset.restLabel || btn.textContent",
            block.group(1),
            "restore must prefer the recorded resting label, not the current text",
        )


if __name__ == "__main__":
    unittest.main()