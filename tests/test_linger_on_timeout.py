"""Regression tests: linger-on-timeout fallback racing.

When a candidate model hits a read timeout, the request is re-dispatched in a
background thread (_LingerPool) with an extended deadline while the fallback
loop continues. Verifies:

  A. Mid-race claim: a timed-out earlier candidate that finishes in the
     background wins over starting later candidates.
  B. End-of-loop rescue: when ALL foreground candidates fail, the late result
     is used instead of failing.
  C. Total failure: if lingering attempts also fail, the original exception is
     raised after a bounded wait (no hang).
  D. Toggle-off: linger_on_timeout=false restores strict sequential behavior
     (no lingering threads).
  E. Emergency stop: wait_for_any() aborts promptly on GLOBAL_STOP.
"""
import os
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from addon import ai_client as ai_mod
from addon.ai_client import AIClient, _LingerPool, state

GOOD = {"hints": ["h1", "h2", "h3"], "options": ["opt1", "opt2", "opt3", "opt4"], "correct_answer": "opt1"}

PRIORITY = [("openai", "m-a"), ("anthropic", "m-b"), ("gemini", "m-c")]


def base_config(**extra):
    cfg = {
        "ai_provider": "openai",
        "api_keys": {"openai": "k-o", "anthropic": "k-a", "gemini": "k-g"},
        "use_global_model_priority": True,
        "global_model_priority": list(PRIORITY),
        "request_timeout": 60,
    }
    cfg.update(extra)
    return cfg


class ScriptedBackend:
    """Per-(provider, model) scripted behaviors for the foreground thread;
    lingering threads (named ai-hints-linger-*) always succeed after a delay."""

    def __init__(self, foreground_script, linger_delay=0.3, linger_result=None):
        self.script = foreground_script
        self.linger_delay = linger_delay
        # NB: explicit None-check — {} is a meaningful value here (unusable
        # late response) and must not fall back to GOOD via `or`.
        self.linger_result = GOOD if linger_result is None else linger_result
        self.calls = []

    def __call__(self, client_self, provider, system_prompt, prompt, override_model=""):
        self.calls.append((provider, override_model, threading.current_thread().name))
        if threading.current_thread().name.startswith("ai-hints-linger"):
            time.sleep(self.linger_delay)
            return dict(self.linger_result, _provider=provider, _model=override_model)
        behavior = self.script[(provider, override_model)]
        if isinstance(behavior, Exception):
            raise behavior
        if callable(behavior):
            behavior()
            return {}
        return dict(behavior, _provider=provider, _model=override_model)


TIMEOUT = socket.timeout("The read operation timed out")
BOOM = ValueError("generic provider error")


class LingerOnTimeoutTests(unittest.TestCase):
    def setUp(self):
        state.GLOBAL_STOP = False
        # Never probe the real network during these tests.
        self._net_patch = patch.object(ai_mod, "_check_network_online", lambda: True)
        self._net_patch.start()

    def tearDown(self):
        self._net_patch.stop()
        state.GLOBAL_STOP = False

    def _generate(self, cfg):
        client = AIClient(cfg)
        return client.generate_options("Front text", "Back text")

    @staticmethod
    def _patch_backend(backend):
        # Plain-function wrapper so Python binds `self` correctly on access.
        def wrapper(client_self, provider, system_prompt, prompt, override_model=""):
            return backend(client_self, provider, system_prompt, prompt, override_model)
        return patch.object(AIClient, "_call_provider", wrapper)

    def test_a_mid_race_claim_prefers_earlier_candidate(self):
        # openai times out (spawns linger), anthropic fails fast, gemini would
        # succeed — but the openai linger finishes first and must be used.
        def slow_fail():
            time.sleep(0.5)
            raise BOOM

        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): slow_fail,  # busy while the linger completes
            ("gemini", "m-c"): GOOD,
        }
        backend = ScriptedBackend(script, linger_delay=0.2)
        with self._patch_backend(backend):
            res = self._generate(base_config())
        self.assertEqual(res.get("_model"), "m-a")
        self.assertEqual(res.get("_provider"), "openai")
        # The race was resolved before gemini ever ran.
        self.assertNotIn(("gemini", "m-c"), [(p, m) for p, m, _ in backend.calls])

    def test_b_end_of_loop_rescue_when_all_fail(self):
        script = {
            ("openai", "m-a"): TIMEOUT,   # spawns linger -> succeeds late
            ("anthropic", "m-b"): BOOM,   # generic failure, no linger
            ("gemini", "m-c"): {},        # unusable empty response
        }
        backend = ScriptedBackend(script, linger_delay=0.2)
        with self._patch_backend(backend):
            res = self._generate(base_config())
        self.assertEqual(res.get("_model"), "m-a")
        self.assertTrue(res.get("hints"))

    def test_c_total_failure_raises_after_bounded_wait(self):
        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): BOOM,
            ("gemini", "m-c"): BOOM,
        }
        # Lingering attempt also fails (immediately).
        backend = ScriptedBackend(script, linger_delay=0.05, linger_result={})
        t0 = time.monotonic()
        with self._patch_backend(backend):
            with self.assertRaises(ValueError):
                self._generate(base_config())
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 10, f"total failure took too long: {elapsed:.1f}s")

    def test_d_disabled_toggle_keeps_sequential_behavior(self):
        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): GOOD,
            ("gemini", "m-c"): BOOM,
        }
        backend = ScriptedBackend(script)
        cfg = base_config(linger_on_timeout=False)
        with self._patch_backend(backend), \
             patch.object(_LingerPool, "spawn", side_effect=AssertionError("spawn must not be called")):
            res = self._generate(cfg)
        self.assertEqual(res.get("_model"), "m-b")  # plain sequential fallback

    def test_e_wait_aborts_on_emergency_stop(self):
        pool = _LingerPool(base_config(), 900, "sys", "prompt")
        started = threading.Event()

        def hang():
            started.set()
            time.sleep(30)

        with patch.object(AIClient, "_call_provider", lambda s, p, sp, pr, override_model="": hang()):
            pool.spawn(0, "openai", "m-a")
        self.assertTrue(started.wait(2))
        time.sleep(0.1)
        state.GLOBAL_STOP = True
        t0 = time.monotonic()
        self.assertIsNone(pool.wait_for_any())
        self.assertLess(time.monotonic() - t0, 3, "emergency stop did not abort the wait")


if __name__ == "__main__":
    unittest.main(verbosity=2)
