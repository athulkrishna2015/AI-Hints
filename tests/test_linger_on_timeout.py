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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon import ai_client as ai_mod
from addon.ai_client import AIClient, _LingerPool, state
from blacklist_helpers import isolate_blacklist

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
        isolate_blacklist(self)
        state.GLOBAL_STOP = False
        # Never probe the real network during these tests, and pin the shared
        # network state to online: the background monitor thread may otherwise
        # flip it to False mid-test (no network in CI), aborting wait_for_any.
        self._net_patch = patch.object(ai_mod, "_check_network_online", lambda: True)
        self._net_patch.start()
        self._netstate_patch = patch.object(ai_mod, "_NETWORK_STATE", {"online": True})
        self._netstate_patch.start()

    def tearDown(self):
        self._net_patch.stop()
        self._netstate_patch.stop()
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

    def _generate_with_events(self, cfg):
        """Runs generate_options on a client whose status_cb records events."""
        client = AIClient(cfg)
        events = []
        client.status_cb = events.append
        with self._patch_backend(self._backend_holder[0]):
            res = client.generate_options("Front text", "Back text")
        return res, events

    def test_f_priority_policy_late_higher_priority_result_wins(self):
        # Default policy: anthropic succeeds fast while openai's lingered retry
        # is still running — generation must WAIT and prefer openai (candidate #1).
        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): GOOD,
            ("gemini", "m-c"): BOOM,
        }
        self._backend_holder = [ScriptedBackend(script, linger_delay=0.4)]
        t0 = time.monotonic()
        res, events = self._generate_with_events(base_config())
        elapsed = time.monotonic() - t0
        self.assertEqual(res.get("_model"), "m-a")
        self.assertEqual(res.get("_provider"), "openai")
        self.assertGreaterEqual(elapsed, 0.3, "priority policy did not wait for the lingered attempt")
        self.assertIn("Lingering", events)
        self.assertIs(events[-1], None)

    def test_g_first_policy_fast_success_wins_immediately(self):
        # "first" policy: the fast lower-priority success wins without waiting.
        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): GOOD,
            ("gemini", "m-c"): BOOM,
        }
        self._backend_holder = [ScriptedBackend(script, linger_delay=0.4)]
        t0 = time.monotonic()
        res, events = self._generate_with_events(base_config(linger_race_policy="first"))
        elapsed = time.monotonic() - t0
        self.assertEqual(res.get("_model"), "m-b")
        self.assertEqual(res.get("_provider"), "anthropic")
        self.assertLess(elapsed, 2.0, f"'first' policy waited anyway: {elapsed:.1f}s")
        # Spawn still announces itself, but no blocking wait cycle runs
        # (a wait always emits a trailing None when it finishes).
        self.assertNotIn(None, events)

    def test_h_pending_tracking_and_policy_helper(self):
        pool = _LingerPool(base_config(), 900, "sys", "prompt")
        release = threading.Event()

        def hang():
            release.wait(5)

        with patch.object(AIClient, "_call_provider", lambda s, p, sp, pr, override_model="": hang()):
            pool.spawn(2, "openai", "m-x")
        try:
            self.assertTrue(pool.has_pending_before(3))
            self.assertFalse(pool.has_pending_before(2))  # strictly EARLIER orders only
            client = AIClient(base_config())
            self.assertTrue(client._linger_prefers_priority)
            client2 = AIClient(base_config(linger_race_policy="first"))
            self.assertFalse(client2._linger_prefers_priority)
        finally:
            release.set()

    def test_i_timeout_resolution_overrides_extend_only(self):
        # Each flow has its own base budget; custom model/provider timeouts are
        # honored for EVERY flow but only when GREATER than that base — a
        # smaller override never shortens the budget.
        # Foreground base = request_timeout
        self.assertEqual(AIClient(base_config(request_timeout=20)).timeout, 20)
        # Provider overrides need request context (set per-request by callers)
        fg_prov = AIClient(base_config(request_timeout=20, provider_timeouts={"openai": 44}))
        fg_prov._request_provider = "openai"
        self.assertEqual(fg_prov.timeout, 44)
        # Smaller-than-base override is ignored (20 stays 20)
        self.assertEqual(
            AIClient(base_config(request_timeout=20, model_timeouts={"openai": {"m-a": 15}})).timeout, 20
        )
        # Batch base = batch_request_timeout (default 120); overrides only extend
        self.assertEqual(AIClient(base_config(), is_batch=True).timeout, 120)
        self.assertEqual(AIClient(base_config(batch_request_timeout=75), is_batch=True).timeout, 75)
        cfg = base_config(
            batch_request_timeout=75,
            model_timeouts={"openai": {"m-a": 33}},   # < 75 -> ignored
            provider_timeouts={"openai": 200},        # > 75 -> wins
        )
        c = AIClient(cfg, is_batch=True)
        c._request_provider = "openai"
        c._request_model = "m-a"
        self.assertEqual(c.timeout, 200)
        # Pregen base = pregen_request_timeout; same extend-only rule
        p = AIClient(base_config(model_timeouts={"openai": {"m-a": 300}}), is_pregen=True)
        p._request_provider = "openai"
        p._request_model = "m-a"
        self.assertEqual(p.timeout, 300)  # 300 > default 120
        p2 = AIClient(base_config(pregen_request_timeout=60), is_pregen=True)
        p2._request_provider = "openai"
        p2._request_model = "m-a"
        self.assertEqual(p2.timeout, 60)
        # Model override beats provider override when both exceed base
        c2 = AIClient(base_config(
            request_timeout=20,
            model_timeouts={"openai": {"m-a": 33}},
            provider_timeouts={"openai": 25},
        ))
        c2._request_provider = "openai"
        c2._request_model = "m-a"
        self.assertEqual(c2.timeout, 33)

    def test_j_batch_style_single_candidate_rescues_pending_only(self):
        # Batch generates with only_this_provider=True. A lone model timeout
        # returns an EMPTY dict without raising, so last_exception stays None;
        # the rescue must still wait for the spawned lingering retry.
        script = {
            # Foreground candidate (batch passes no model override): times out.
            # The lingering thread never consults the script — it always
            # succeeds after linger_delay.
            ("openai", ""): TIMEOUT,
            ("anthropic", "m-b"): GOOD,   # never reached: only_this_provider
        }
        backend = ScriptedBackend(script, linger_delay=0.3)
        t0 = time.monotonic()
        # Explicit only_this_provider call (batch_manager.py style):
        client = AIClient(base_config(request_timeout=20))
        events = []
        client.status_cb = events.append
        with self._patch_backend(backend):
            res = client.generate_options(
                "Front text", "Back text",
                override_provider="openai", only_this_provider=True,
            )
        elapsed = time.monotonic() - t0
        self.assertEqual(res.get("_provider"), "openai")
        self.assertTrue(res.get("hints"))
        # Provider-level re-dispatch is model-agnostic (the outer loop never
        # knew which inner model timed out), so the model tag stays empty.
        self.assertEqual(res.get("_model"), "")
        self.assertGreaterEqual(elapsed, 0.3, "pending-only rescue did not wait for the linger")
        self.assertIn("Lingering", events)

    def test_k_pregen_client_lingers_too(self):
        # Pregen uses the same generate_options walk; the late result must be
        # rescued when every foreground candidate fails.
        script = {
            ("openai", "m-a"): TIMEOUT,
            ("anthropic", "m-b"): BOOM,
            ("gemini", "m-c"): {},
        }
        backend = ScriptedBackend(script, linger_delay=0.2)
        client = AIClient(base_config(), is_pregen=True)
        with self._patch_backend(backend):
            res = client.generate_options("Front text", "Back text")
        self.assertEqual(res.get("_model"), "m-a")
        self.assertTrue(res.get("hints"))

    def test_l_model_test_read_timeout_with_no_linger_does_not_crash(self):
        # Regression: during a model test the linger_pool is None, so the inner
        # custom-provider loop's _active_linger hook is (None, order). A read
        # timeout there must NOT call .spawn() on the None pool — previously it
        # raised "'NoneType' object has no attribute 'spawn'".
        from addon.logger import log_context
        cfg = base_config(custom_providers={
            "trustedrouter": {"url": "http://custom.api/v1", "model": "m1", "api_key": "k"},
        })
        client = AIClient(cfg)
        client._active_linger = (None, 0)
        log_context.source = "model_test"
        try:
            with patch.object(AIClient, "_post_json", side_effect=lambda *a, **k: (_ for _ in ()).throw(TIMEOUT)):
                res = client._call_custom_provider("trustedrouter", "sys", "prompt")
        finally:
            log_context.source = None
        self.assertEqual(res, {"hints": [], "options": []})

    def test_m_openai_compatible_read_timeout_with_no_linger_does_not_crash(self):
        # Same regression for the OpenAI-compatible loop (e.g. poolside): during
        # a model test the linger_pool is None, so _active_linger is
        # (None, order) — a read timeout there must NOT call .spawn() on None.
        from addon.logger import log_context
        cfg = base_config(api_keys={"poolside": "k"})
        client = AIClient(cfg)
        client._active_linger = (None, 0)
        log_context.source = "model_test"
        try:
            with patch.object(AIClient, "_post_json", side_effect=lambda *a, **k: (_ for _ in ()).throw(TIMEOUT)):
                res = client._call_openai_compatible("poolside", "sys", "prompt", override_model="m1")
        finally:
            log_context.source = None
        self.assertEqual(res, {"hints": [], "options": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
