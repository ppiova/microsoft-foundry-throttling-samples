"""CLI lab: real REST calls or an explicitly labeled local HTTP server."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import math
from pathlib import Path
import random
import threading
import time
from urllib.error import URLError
import uuid
import platform
from credentials import AuthenticationError

from adapters import PATHS, Transport
from mock_service import start_mock


def retry_delay(headers, attempt):
    for name, multiplier in (("retry-after-ms", .001), ("retry-after", 1)):
        try:
            value = float(headers[name]) * multiplier
            if math.isfinite(value) and value >= 0:
                return value
        except (KeyError, ValueError, TypeError):
            pass
    try:
        value = parsedate_to_datetime(headers["retry-after"])
        if value.tzinfo:
            return max(0, value.timestamp() - time.time())
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return min(2 ** (attempt - 1), 8) + random.random()


class Gate:
    """LOCAL admission control: pacing, estimated reservations, and a budget.

    The same Gate regulates every attempt, including retries, in this run.
    It does not replicate Azure quotas or coordinate other processes or applications.
    """
    def __init__(self, rpm, limits, costs, budget, window=60):
        if any(costs.get(k, 0) > v for k, v in limits.items()):
            raise ValueError("The estimated request exceeds the local token budget")
        self.rpm, self.limits, self.costs = rpm, limits, costs
        self.budget, self.window = budget, window
        self.next_at = 0.0
        self.history = deque()
        self.lock = threading.Lock()
        self.sent = 0

    def acquire(self, deadline):
        began = time.monotonic()
        while True:
            with self.lock:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError("deadline")
                if self.sent >= self.budget:
                    raise RuntimeError("attempt_budget")
                while self.history and now - self.history[0] >= self.window:
                    self.history.popleft()
                delay = max(0, self.next_at - now)
                if self.history and any((len(self.history) + 1) * self.costs.get(k, 0) > v
                                        for k, v in self.limits.items()):
                    delay = max(delay, self.history[0] + self.window - now)
                if delay <= 0:
                    self.sent += 1
                    self.history.append(now)
                    if self.rpm:
                        self.next_at = now + 60 / self.rpm
                    return now - began
                if now + delay >= deadline:
                    raise TimeoutError("deadline")
            time.sleep(min(delay, .05))


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def summarize(attempts, jobs, elapsed):
    ok_http = sum(200 <= (j["final_status"] or 0) < 300 for j in jobs)
    completed = sum(j["outcome"] == "completed" for j in jobs)
    codes429 = sum(a["status"] == 429 for a in attempts)
    return {
        "logical_requests": len(jobs), "http_attempts": len(attempts),
        "retries": sum(a["attempt"] > 1 for a in attempts),
        "http_successes": ok_http, "completed_responses": completed,
        "http_429": codes429,
        "http_429_percent": round(100 * codes429 / len(attempts), 2) if attempts else 0,
        "elapsed_seconds": round(elapsed, 3),
        "completed_per_second": round(completed / elapsed, 3) if elapsed else 0,
        "p50_e2e_seconds": percentile([j["e2e_seconds"] for j in jobs], .5),
        "p95_e2e_seconds": percentile([j["e2e_seconds"] for j in jobs], .95),
        "p95_http_seconds": percentile([a["http_seconds"] for a in attempts], .95),
    }


def run(args):
    target = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))["targets"][args.target]
    if not isinstance(target, dict) or not isinstance(target.get("provider"), str) or target["provider"] not in PATHS:
        raise ValueError("Unknown provider")
    if not isinstance(target.get("deployment"), str) or not target["deployment"].strip():
        raise ValueError("Set a nonempty deployment name")
    if args.live and target["deployment"] == "REPLACE_ME":
        raise ValueError("Configure the actual deployment name")
    count = 1 if args.scenario == "preflight" else args.requests
    if not (1 <= count <= 200 and 1 <= args.concurrency <= 20 and 1 <= args.max_attempts <= 5
            and 1 <= args.attempt_budget <= 1000 and 1 <= args.deadline <= 600
            and 1 <= args.output_limit <= 32768 and 1 <= args.prompt_repeat <= 200
            and math.isfinite(args.client_rpm) and args.client_rpm > 0 and 1 <= args.input_estimate <= 1000000
            and all(v >= 0 for v in (args.client_token_budget, args.client_input_budget, args.client_output_budget))):
        raise ValueError("Parameters are outside the lab limits")
    prompt = "Explain why measuring request rates helps diagnose an API. " * args.prompt_repeat
    prompt += " Respond in one sentence."
    costs = {"tokens": args.input_estimate + args.output_limit,
             "input": args.input_estimate, "output": args.output_limit}
    limits = {}
    if args.scenario == "guarded":
        limits = {k: v for k, v in (("tokens", args.client_token_budget),
                  ("input", args.client_input_budget), ("output", args.client_output_budget)) if v > 0}
        if not limits and target["provider"] != "mai_image":
            raise ValueError("guarded requires at least one local token budget")
    if target["provider"] == "mai_image" and limits:
        raise ValueError("The image lab uses RPM; text TPM budgets do not apply")
    rpm = args.client_rpm if args.scenario in ("baseline", "paced", "guarded") else 0
    workers = 1 if args.scenario in ("preflight", "baseline") else args.concurrency
    retries = args.max_attempts if args.scenario in ("retry", "paced", "guarded") else 1
    gate = Gate(rpm, limits, costs, args.attempt_budget, 60 if args.live else args.mock_window)
    server = None
    transport = None
    origin = None
    if not args.live:
        server, origin = start_mock(args.mock_axis, args.mock_window)
    try:
        transport = Transport(target, origin)
        output = Path(args.out) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        mode = "LIVE_AZURE" if args.live else "LOCAL_HTTP_MOCK"
        safe_target = {k: target[k] for k in ("provider", "deployment", "endpoint_env", "credential_env",
                       "auth", "model", "version", "lifecycle", "hosting", "region", "deployment_type",
                       "quota_scope", "verified_limits", "credential_type") if k in target}
        manifest = {
            "schema_version": 1, "implementation": "python", "runtime_version": platform.python_version(),
            "run_id": output.name, "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "ended_at_utc": None, "mock_window_seconds": args.mock_window if not args.live else None,
            "mode": mode, "scenario": args.scenario, "target": safe_target,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt),
            "output_limit": args.output_limit, "request_count": count,
            "concurrency": workers, "client_rpm": rpm, "client_estimates": costs,
            "client_token_budgets": limits, "client_window_seconds": gate.window,
            "attempt_budget": args.attempt_budget, "max_attempts_per_job": retries,
            "admission_deadline_seconds": args.deadline,
            "mock_axis": args.mock_axis if not args.live else None,
            "note": "metadata and verified_limits are user-supplied, not discovered from Azure",
        }
        # Configuration contains environment variable names, never credential values.
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        attempts, jobs = [], []
        lock = threading.Lock()
        start = time.monotonic()
        deadline = start + args.deadline

        def job(index):
            outcome, final_status, n = "not_sent", None, 0
            queued = time.monotonic() - start
            waited, backoff = 0.0, 0.0
            for attempt in range(1, retries + 1):
                try:
                    waited += gate.acquire(deadline)
                except (TimeoutError, RuntimeError) as error:
                    outcome = str(error)
                    break
                sent_at = time.monotonic()
                sent_utc = datetime.now(timezone.utc).isoformat()
                status, headers, info = None, {}, {"outcome": "transport_error", "usage": {}}
                try:
                    status, headers, info = transport.send(prompt, args.output_limit,
                                                          max(.001, min(30, deadline - sent_at)))
                except (URLError, TimeoutError, OSError, HTTPException):
                    pass  # Do not resend an operation whose outcome is unknown.
                except AuthenticationError:
                    outcome = "authentication_error"
                    break  # No HTTP request was sent; keep this out of attempt metrics.
                n += 1
                final_status, outcome = status, info["outcome"]
                delay = retry_delay(headers, attempt) if status == 429 and attempt < retries else None
                event = {"job": index, "attempt": attempt, "status": status,
                         "sent_at_utc": sent_utc,
                         "utc": datetime.now(timezone.utc).isoformat(),
                         "sent_after_seconds": round(sent_at - start, 4),
                         "http_seconds": round(time.monotonic() - sent_at, 4),
                         "headers": headers, "proposed_retry_wait_seconds": delay, **info}
                with lock:
                    attempts.append(event)
                    with (output / "attempts.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                    print(f"{mode} job={index:02} attempt={attempt} HTTP={status} "
                          f"outcome={outcome} t={event['sent_after_seconds']:.2f}s", flush=True)
                if status != 429 or attempt == retries:
                    break
                if time.monotonic() + delay >= deadline:
                    outcome = "retry_wait_exceeds_deadline"
                    break
                time.sleep(delay)
                backoff += delay
            result = {"job": index, "attempts": n, "final_status": final_status, "outcome": outcome,
                      "executor_queue_seconds": round(queued, 4),
                      "admission_wait_seconds": round(waited, 4),
                      "retry_wait_seconds": round(backoff, 4),
                      "e2e_seconds": round(time.monotonic() - start, 4)}
            with lock:
                jobs.append(result)

        print(f"{mode} | {args.target} | {args.scenario} | {count} requests", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            list(executor.map(job, range(1, count + 1)))
        summary = summarize(attempts, jobs, time.monotonic() - start)
        manifest["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (output / "attempts.jsonl").touch(exist_ok=True)
        (output / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        lines = [f"# Result: {mode}", "", f"Scenario: {args.scenario}", "",
                 "| Metric | Value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in summary.items()]
        lines += ["", "E2E latency includes queuing, admission, and retries. HTTP 200 does not guarantee completion.",
                  "Usage tokens do not measure the internal throttling counter."]
        (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        print(f"RESULTS={output.resolve()}")
        return output
    finally:
        if transport:
            transport.close()
        if server:
            server.shutdown()
            server.server_close()


def compare(paths, dest):
    runs = [(Path(p), json.loads((Path(p) / "manifest.json").read_text(encoding="utf-8")),
             json.loads((Path(p) / "summary.json").read_text(encoding="utf-8"))) for p in paths]
    signatures = []
    for _, m, _ in runs:
        mock_window = None
        if m["mode"] == "LOCAL_HTTP_MOCK":
            # Local admission and the mock service use the same configured window.
            # Historical evidence without that value cannot establish equivalence.
            mock_window = m.get("client_window_seconds")
            if (isinstance(mock_window, bool) or not isinstance(mock_window, (int, float))
                    or not math.isfinite(mock_window) or mock_window <= 0):
                raise ValueError("Invalid comparison: local mock window is missing or invalid; rerun the scenarios")
        signatures.append((m["mode"], m["target"], m["prompt_sha256"], m["output_limit"],
                           m["request_count"], m["mock_axis"], mock_window, m.get("schema_version")))
    if any(s != signatures[0] for s in signatures[1:]):
        raise ValueError("Invalid comparison: provider, workload, output cap, mode, or mock condition/window differs")
    lines = ["# Run Comparison", "", f"Mode: {runs[0][1]['mode']}", "",
             "| Scenario | Complete | HTTP attempts | 429s | E2E p95 s | Complete/s |",
             "|---|---:|---:|---:|---:|---:|"]
    for _, m, s in runs:
        lines.append(f"| {m['scenario']} | {s['completed_responses']} | {s['http_attempts']} | {s['http_429']} | {s['p95_e2e_seconds']} | {s['completed_per_second']} |")
    lines += ["", "Same logical workload. Controls vary by scenario; review the manifests.",
              "This does not establish causality in Azure: other workloads and capacity can change between runs."]
    Path(dest).write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--config", default="config.example.json")
    run_parser.add_argument("--target", choices=["aoai", "claude", "mai", "image"], default="aoai")
    run_parser.add_argument("--scenario", choices=["preflight", "baseline", "burst", "retry", "paced", "guarded"], default="preflight")
    run_parser.add_argument("--live", action="store_true")
    run_parser.add_argument("--requests", type=int, default=6)
    run_parser.add_argument("--concurrency", type=int, default=6)
    run_parser.add_argument("--max-attempts", type=int, default=3)
    run_parser.add_argument("--attempt-budget", type=int, default=18)
    run_parser.add_argument("--deadline", type=float, default=30)
    run_parser.add_argument("--client-rpm", type=float, default=60)
    run_parser.add_argument("--input-estimate", type=int, default=128)
    run_parser.add_argument("--output-limit", type=int, default=128)
    run_parser.add_argument("--prompt-repeat", type=int, default=1)
    run_parser.add_argument("--client-token-budget", type=int, default=0)
    run_parser.add_argument("--client-input-budget", type=int, default=0)
    run_parser.add_argument("--client-output-budget", type=int, default=0)
    run_parser.add_argument("--mock-axis", choices=["rpm", "tpm", "itpm", "otpm", "capacity"], default="rpm")
    run_parser.add_argument("--mock-window", type=float, default=2)
    run_parser.add_argument("--out", default="runs")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("paths", nargs="+")
    compare_parser.add_argument("--out", default="comparison.md")
    args = parser.parse_args()
    if args.command == "compare":
        compare(args.paths, args.out)
    else:
        if not .1 <= args.mock_window <= 60:
            parser.error("mock-window must be between 0.1 and 60 seconds")
        run(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        # Do not print raw configuration, filesystem, or environment exception values.
        print("Lab configuration or file error. Check arguments, config, environment variables, and output permissions.")
        raise SystemExit(2) from None
