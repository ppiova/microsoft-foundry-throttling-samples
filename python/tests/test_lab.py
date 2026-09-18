import importlib
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import Transport, payload, response_info, observed_headers
from lab import Gate, retry_delay, summarize, compare
from mock_service import start_mock


class Contracts(unittest.TestCase):
    def test_output_parameters_are_provider_specific(self):
        for provider, parameter in (("azure_openai", "max_output_tokens"),
                                    ("claude", "max_tokens"), ("mai_thinking", "max_completion_tokens")):
            value = payload(provider, "my-deployment", "test", 128)
            self.assertEqual(value[parameter], 128)
            self.assertEqual(value["model"], "my-deployment")
            self.assertEqual(len(set(value) & {"max_output_tokens", "max_tokens", "max_completion_tokens"}), 1)

    def test_image_contract(self):
        body = payload("mai_image", "d", "p", 256)
        self.assertEqual((body["width"], body["height"]), (1024, 1024))
        self.assertNotIn("max_tokens", body)

    def test_incomplete_is_not_successful_completion(self):
        self.assertNotEqual(response_info("azure_openai", 200, {"status": "incomplete"})["outcome"], "completed")
        self.assertNotEqual(response_info("claude", 200, {"stop_reason": "max_tokens"})["outcome"], "completed")
        self.assertNotEqual(response_info("mai_thinking", 200, {"choices": [{"finish_reason": "length"}]})["outcome"], "completed")

    def test_usage_preserves_cache_dimensions(self):
        body = {"usage": {"input_tokens": 12, "output_tokens": 3, "cache_read_input_tokens": 100,
                          "cache_creation_input_tokens": 20}, "stop_reason": "end_turn"}
        self.assertEqual(response_info("claude", 200, body)["usage"], body["usage"])

    def test_no_content_or_secrets_in_diagnostics(self):
        headers = observed_headers({"Authorization": "secret", "x-api-key": "secret", "Retry-After": "1"})
        info = response_info("azure_openai", 429, {"error": {"message": "my secret prompt", "code": "RateLimit"}})
        self.assertNotIn("secret", json.dumps([headers, info]))
        self.assertIsNone(info["evidence_hint"])


class Control(unittest.TestCase):
    def test_atomic_attempt_budget(self):
        gate = Gate(0, {}, {}, 3)
        successes = []
        def acquire():
            try:
                gate.acquire(time.monotonic() + 1)
                successes.append(True)
            except RuntimeError:
                pass
        threads = [threading.Thread(target=acquire) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(successes), 3)

    def test_rpm_pacing(self):
        gate = Gate(3000, {}, {}, 2)
        gate.acquire(time.monotonic() + 1)
        start = time.monotonic()
        gate.acquire(start + 1)
        self.assertGreaterEqual(time.monotonic() - start, .015)

    def test_input_and_output_budgets(self):
        gate = Gate(0, {"input": 200, "output": 100}, {"input": 50, "output": 100}, 3, window=.03)
        gate.acquire(time.monotonic() + 1)
        start = time.monotonic()
        gate.acquire(start + 1)
        self.assertGreaterEqual(time.monotonic() - start, .025)

    def test_impossible_request_fails_before_network(self):
        with self.assertRaises(ValueError):
            Gate(1, {"tokens": 1}, {"tokens": 2}, 10)

    def test_deadline_stops_admission(self):
        gate = Gate(1, {}, {}, 2)
        gate.acquire(time.monotonic() + 1)
        with self.assertRaises(TimeoutError):
            gate.acquire(time.monotonic() + .01)

    def test_retry_formats(self):
        self.assertEqual(retry_delay({"retry-after-ms": "1500", "retry-after": "5"}, 1), 1.5)
        self.assertEqual(retry_delay({"retry-after": "2"}, 1), 2)
        for value in ["nan", "inf", "-1", "bad"]:
            self.assertTrue(1 <= retry_delay({"retry-after-ms": value}, 1) <= 2)
        with patch("lab.time.time", return_value=0):
            self.assertEqual(retry_delay({"retry-after": "Thu, 01 Jan 1970 00:00:03 GMT"}, 1), 3)


class HttpIntegration(unittest.TestCase):
    def test_four_real_http_transports_to_local_mock(self):
        for provider in ("azure_openai", "claude", "mai_thinking", "mai_image"):
            with self.subTest(provider=provider):
                server, origin = start_mock("rpm", .1)
                try:
                    transport = Transport({"provider": provider, "deployment": "test"}, origin)
                    status, headers, info = transport.send("hello", 16, 2)
                    self.assertEqual(status, 200)
                    self.assertEqual(info["outcome"], "completed")
                finally:
                    server.shutdown()
                    server.server_close()

    def test_http429_and_recovery(self):
        now = [0.0]
        server, origin = start_mock("rpm", .15, clock=lambda: now[0])
        try:
            transport = Transport({"provider": "azure_openai", "deployment": "test"}, origin)
            transport.send("hello", 16, 2)
            transport.send("hello", 16, 2)
            status, headers, info = transport.send("hello", 16, 2)
            self.assertEqual(status, 429)
            self.assertEqual(info["error_code"], "local_mock_rpm")
            # Control server time rather than depending on HTTP or CI speed.
            delay = retry_delay(headers, 1)
            self.assertGreaterEqual(delay, .15)
            now[0] += delay
            self.assertEqual(transport.send("hello", 16, 2)[0], 200)
        finally:
            server.shutdown()
            server.server_close()

    def test_key_headers(self):
        with patch.dict("os.environ", {"TEST_ENDPOINT": "https://example.com", "TEST_KEY": "placeholder"}):
            for provider in ("claude", "azure_openai", "mai_thinking", "mai_image"):
                transport = Transport(dict(provider=provider, deployment="d", endpoint_env="TEST_ENDPOINT",
                    credential_env="TEST_KEY", auth="api_key"))
                self.assertIn("x-api-key" if provider == "claude" else "api-key", transport.headers)


class Metrics(unittest.TestCase):
    def test_comparison_requires_the_same_known_mock_window(self):
        for second_window in (1, None, 0, float("nan"), True):
            with self.subTest(window=second_window), tempfile.TemporaryDirectory() as tmp:
                paths = []
                for index, window in enumerate((2, second_window)):
                    path = Path(tmp) / str(index)
                    path.mkdir()
                    manifest = dict(mode="LOCAL_HTTP_MOCK", target={}, prompt_sha256="a",
                                    output_limit=128, request_count=6, mock_axis="rpm")
                    if window is not None:
                        manifest["client_window_seconds"] = window
                    (path / "manifest.json").write_text(json.dumps(manifest))
                    (path / "summary.json").write_text("{}")
                    paths.append(str(path))
                with self.assertRaisesRegex(ValueError, "window"):
                    compare(paths, str(Path(tmp) / "report.md"))

    def test_comparison_accepts_same_window_with_different_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, scenario in enumerate(("burst", "paced")):
                path = Path(tmp) / str(index)
                path.mkdir()
                manifest = dict(mode="LOCAL_HTTP_MOCK", target={}, prompt_sha256="a",
                                output_limit=128, request_count=6, mock_axis="rpm",
                                client_window_seconds=2, scenario=scenario,
                                client_rpm=0 if index == 0 else 60)
                summary = dict(completed_responses=2, http_attempts=6, http_429=4,
                               p95_e2e_seconds=1, completed_per_second=2)
                (path / "manifest.json").write_text(json.dumps(manifest))
                (path / "summary.json").write_text(json.dumps(summary))
                paths.append(str(path))
            report = Path(tmp) / "report.md"
            compare(paths, str(report))
            self.assertIn("paced", report.read_text())

    def test_attempt_vs_job_and_incomplete(self):
        result = summarize([dict(status=429, attempt=1, http_seconds=.1),
                            dict(status=200, attempt=2, http_seconds=.2)],
                           [dict(final_status=200, outcome="incomplete_or_unknown", e2e_seconds=1)], 1)
        self.assertEqual(result["http_successes"], 1)
        self.assertEqual(result["completed_responses"], 0)
        self.assertEqual(result["http_429_percent"], 50)

    def test_reject_mixed_mock_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for mode in ("LOCAL_HTTP_MOCK", "LIVE_AZURE"):
                path = Path(tmp) / mode
                path.mkdir()
                (path / "manifest.json").write_text(json.dumps(dict(mode=mode, target={}, prompt_sha256="a",
                    output_limit=1, request_count=1, mock_axis=None, client_window_seconds=2)))
                (path / "summary.json").write_text("{}")
                paths.append(str(path))
            with self.assertRaises(ValueError):
                compare(paths, str(Path(tmp) / "report.md"))


if __name__ == "__main__":
    unittest.main()
