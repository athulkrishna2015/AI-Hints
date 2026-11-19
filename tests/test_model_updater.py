import unittest
import os
import sys
import io
import json
import time
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon.ai_client import (
    AIClient,
    PROVIDER_ZERO_QUOTA_UNTIL,
    LAST_FETCH_ERROR,
    ANTHROPIC_API_VERSION,
)
from addon.model_updater import _providers_to_update, run_auto_update


def _http_error(code: int) -> urllib.error.HTTPError:
    msg = {429: "Too Many Requests", 404: "Not Found", 401: "Unauthorized"}.get(code, "Error")
    return urllib.error.HTTPError("http://test", code, msg, None, None)


class TestFetchModelsKeyRotation(unittest.TestCase):
    """Key rotation in fetch_models must stop on URL/quote-level errors."""

    def setUp(self):
        PROVIDER_ZERO_QUOTA_UNTIL.pop("gemini", None)
        LAST_FETCH_ERROR.pop("gemini", None)

    def tearDown(self):
        PROVIDER_ZERO_QUOTA_UNTIL.pop("gemini", None)
        LAST_FETCH_ERROR.pop("gemini", None)

    def _client(self):
        return AIClient({
            "api_keys": {"gemini": "k1, k2, k3"},
            "models": {"gemini": "gemini-flash-latest"},
        })

    def test_429_rotates_through_all_keys(self):
        """A 429 is scoped to the key's project, so later keys must be tried."""
        client = self._client()
        calls = []
        with patch.object(AIClient, "_get_json", side_effect=lambda url, headers: calls.append(url) or self._raise(429)):
            models = client.fetch_models("gemini")
        self.assertEqual(models, [])
        self.assertEqual(len(calls), 3, "429 must keep rotating: other keys may be different projects")

    def test_404_stops_rotation(self):
        """A 404 is a URL-level error: rotating keys cannot fix it, so one request only."""
        client = self._client()
        calls = []
        with patch.object(AIClient, "_get_json", side_effect=lambda url, headers: calls.append(url) or self._raise(404)):
            models = client.fetch_models("gemini")
        self.assertEqual(models, [])
        self.assertEqual(len(calls), 1, "404 must break the key-rotation loop after the first attempt")

    def test_401_rotates_to_next_key(self):
        """Auth failures are per-key: rotation must continue through all keys."""
        client = self._client()
        calls = []
        with patch.object(AIClient, "_get_json", side_effect=lambda url, headers: calls.append(url) or self._raise(401)):
            models = client.fetch_models("gemini")
        self.assertEqual(models, [])
        self.assertEqual(len(calls), 3, "401 should keep rotating through every key")

    def test_rotation_recovers_on_second_key(self):
        """First key dead (401), second key works: models are still returned."""
        client = self._client()
        calls = []

        def _fake_get(url, headers):
            calls.append(url)
            if len(calls) == 1:
                raise self._raise(401)
            return {"models": [{"name": "models/gemini-flash-latest",
                                "supportedGenerationMethods": ["generateContent"]}]}

        with patch.object(AIClient, "_get_json", side_effect=_fake_get):
            models = client.fetch_models("gemini")
        self.assertEqual(models, ["gemini-flash-latest"])
        self.assertEqual(len(calls), 2)

    @staticmethod
    def _raise(code):
        raise _http_error(code)

    @staticmethod
    def _zero_quota_error():
        body = {
            "error": {
                "code": 429,
                "message": "Quota exceeded",
                "details": [{
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "domain": "googleapis.com",
                    "metadata": {
                        "quota_limit": "GenerateRequestsPerMinutePerProjectPerRegion",
                        "quota_limit_value": "0",
                    },
                }],
            },
        }
        return urllib.error.HTTPError(
            "http://test", 429, "Too Many Requests", {}, io.BytesIO(json.dumps(body).encode())
        )

    def test_zero_quota_key_falls_through_to_next_key(self):
        """quota_limit_value=0 is per-project: the next key may still work."""
        client = self._client()
        keys = []

        def _fake_get(url, headers):
            keys.append(headers.get("x-goog-api-key"))
            if headers.get("x-goog-api-key") == "k1":
                raise self._zero_quota_error()
            return {"models": [{"name": "models/gemini-4-carbon",
                                "supportedGenerationMethods": ["generateContent"]}]}

        with patch.object(AIClient, "_get_json", side_effect=_fake_get):
            models = client.fetch_models("gemini")

        self.assertEqual(models, ["gemini-4-carbon"])
        self.assertEqual(keys, ["k1", "k2"])
        self.assertNotIn("gemini", PROVIDER_ZERO_QUOTA_UNTIL)

    def test_all_keys_zero_quota_parks_provider(self):
        """When every project has zero quota, report it and stop retrying."""
        client = self._client()
        calls = []
        with patch.object(AIClient, "_get_json", side_effect=lambda url, headers: calls.append(url) or self._raise_zero_quota()):
            models = client.fetch_models("gemini")

        self.assertEqual(models, [])
        self.assertEqual(len(calls), 3, "every key must be tried before giving up")
        self.assertGreater(PROVIDER_ZERO_QUOTA_UNTIL.get("gemini", 0), time.time())
        self.assertIn("zero quota", LAST_FETCH_ERROR.get("gemini", ""))
        self.assertNotIn("retry in a minute", LAST_FETCH_ERROR.get("gemini", "").lower())

    @staticmethod
    def _raise_zero_quota():
        raise TestFetchModelsKeyRotation._zero_quota_error()


class TestFetchModelsPagination(unittest.TestCase):
    """models.list is paginated (50/page by default); newer models such as
    gemini-4-carbon/hydrogen sit on later pages and used to be dropped."""

    def test_follows_next_page_token(self):
        client = AIClient({
            "api_keys": {"gemini": "k1"},
            "models": {"gemini": "gemini-flash-latest"},
        })
        calls = []

        def _fake_get(url, headers):
            calls.append(url)
            if "pageToken" not in url:
                return {
                    "models": [{"name": "models/gemini-4-argon",
                                "supportedGenerationMethods": ["generateContent"]}],
                    "nextPageToken": "page-2",
                }
            return {
                "models": [
                    {"name": "models/gemini-4-carbon",
                     "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-4-hydrogen",
                     "supportedGenerationMethods": ["generateContent"]},
                ],
            }

        with patch.object(AIClient, "_get_json", side_effect=_fake_get):
            models = client.fetch_models("gemini")

        self.assertEqual(models, ["gemini-4-argon", "gemini-4-carbon", "gemini-4-hydrogen"])
        self.assertEqual(len(calls), 2)
        self.assertIn("pageSize=1000", calls[0])
        self.assertIn("pageToken=page-2", calls[1])


class TestProvidersToUpdate(unittest.TestCase):
    """The background updater must skip disabled providers entirely."""

    def test_disabled_custom_provider_skipped(self):
        config = {
            "custom_providers": {"opecode multi auth": {"url": "http://localhost:8080/v1"}},
            "disabled_providers": ["opecode multi auth"],
        }
        providers = _providers_to_update(config)
        self.assertNotIn("opecode multi auth", providers)

    def test_enabled_custom_provider_kept(self):
        config = {
            "custom_providers": {"CLIProxyAPI": {"url": "https://example.com/v1"}},
        }
        providers = _providers_to_update(config)
        self.assertIn("CLIProxyAPI", providers)

    def test_disabled_local_provider_skipped(self):
        config = {
            "local_providers": {
                "off-node": {"base_url": "http://localhost:11434/v1", "enabled": False},
                "on-node": {"base_url": "http://localhost:21434/v1", "enabled": True},
            },
        }
        providers = _providers_to_update(config)
        self.assertNotIn("off-node", providers)
        self.assertIn("on-node", providers)

    def test_disabled_builtin_provider_skipped(self):
        """A built-in provider in disabled_providers is not added even with keys stored."""
        config = {
            "api_keys": {"gemini": "k1", "openai": "k2"},
            "disabled_providers": ["openai"],
        }
        providers = _providers_to_update(config)
        self.assertIn("gemini", providers)
        self.assertNotIn("openai", providers)

    def test_disabled_provider_with_fallbacks_skipped(self):
        """Fallback lists alone must not resurrect a disabled provider."""
        config = {
            "model_fallbacks": {"gemini": ["m1"], "sambanova": ["m2"]},
            "disabled_providers": ["sambanova"],
        }
        providers = _providers_to_update(config)
        self.assertIn("gemini", providers)
        self.assertNotIn("sambanova", providers)

    def test_local_endpoint_respects_disabled(self):
        config = {"local_endpoint": {"base_url": "http://localhost:11434/v1"},
                  "disabled_providers": ["local"]}
        providers = _providers_to_update(config)
        self.assertNotIn("local", providers)


class TestAnthropicModelFetch(unittest.TestCase):
    """Anthropic has its own GET /v1/models with cursor pagination."""

    def _client(self):
        return AIClient({"api_keys": {"anthropic": "ak-test"}})

    def test_fetches_models_with_version_header_and_pagination(self):
        client = self._client()
        urls = []
        headers_seen = []

        def _fake_get(url, headers):
            urls.append(url)
            headers_seen.append(dict(headers))
            if "after_id" not in url:
                return {
                    "data": [{"id": "claude-opus-4-6"}, {"id": "claude-sonnet-4-6"}],
                    "has_more": True,
                    "last_id": "claude-sonnet-4-6",
                }
            return {"data": [{"id": "claude-haiku-4-6"}], "has_more": False}

        with patch.object(AIClient, "_get_json", side_effect=_fake_get):
            models = client.fetch_models("anthropic")

        self.assertEqual(
            models,
            ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-6"],
        )
        self.assertEqual(len(urls), 2)
        self.assertIn("after_id=claude-sonnet-4-6", urls[1])
        self.assertEqual(headers_seen[0].get("anthropic-version"), ANTHROPIC_API_VERSION)
        self.assertEqual(headers_seen[0].get("x-api-key"), "ak-test")

    def test_reports_fetch_error_instead_of_silently_returning_nothing(self):
        client = self._client()
        with patch.object(AIClient, "_get_json", side_effect=_http_error(401)):
            models = client.fetch_models("anthropic")

        self.assertEqual(models, [])
        self.assertIn("401", LAST_FETCH_ERROR.get("anthropic", ""))


class TestGeminiStableApiVersion(unittest.TestCase):
    def test_fetch_uses_v1_not_v1beta(self):
        client = AIClient({"api_keys": {"gemini": "gk"}})
        urls = []

        def _fake_get(url, headers):
            urls.append(url)
            return {"models": [
                {"name": "models/gemini-4-argon",
                 "supportedGenerationMethods": ["generateContent"]},
            ]}

        with patch.object(AIClient, "_get_json", side_effect=_fake_get):
            models = client.fetch_models("gemini")

        self.assertEqual(models, ["gemini-4-argon"])
        self.assertTrue(urls[0].startswith(
            "https://generativelanguage.googleapis.com/v1/models"))
        self.assertNotIn("v1beta", urls[0])


class TestModelTestDoesNotParkProvider(unittest.TestCase):
    def test_zero_quota_during_model_test_is_not_persisted(self):
        from addon.logger import log_context

        PROVIDER_ZERO_QUOTA_UNTIL.pop("gemini", None)
        client = AIClient({
            "api_keys": {"gemini": "test-key"},
            "models": {"gemini": "gemini-2.5-flash"},
        })
        body = json.dumps({"error": {"details": [{
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "metadata": {"quota_limit_value": "0"},
        }]}}).encode()
        err = urllib.error.HTTPError("http://test", 429, "Too Many Requests", {}, io.BytesIO(body))
        previous = getattr(log_context, "source", None)
        log_context.source = "model_test"
        try:
            with patch.object(AIClient, "_timed_post", side_effect=err):
                try:
                    client._call_gemini("sys", "prompt")
                except Exception:
                    pass
        finally:
            log_context.source = previous
        self.assertNotIn(
            "gemini", PROVIDER_ZERO_QUOTA_UNTIL,
            "a diagnostic test must not park real generation for 30 minutes",
        )


class TestAutoUpdateThrottle(unittest.TestCase):
    def test_failed_update_does_not_advance_daily_timestamp(self):
        config = {"auto_update_models": True, "last_model_update": 100.0}

        with patch("addon.model_updater.read_meta_config", return_value=config), \
             patch("addon.model_updater.write_pretty_config_preserve_keys"), \
             patch.object(AIClient, "fetch_models", return_value=[]):
            summary = run_auto_update(silent=True)

        self.assertEqual(summary["providers"], 0)
        self.assertEqual(config.get("last_model_update"), 100.0,
                         "a run where every fetch failed must not consume the daily slot")


if __name__ == "__main__":
    unittest.main()
