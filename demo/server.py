"""Loopback-only presentation console. Executes bounded local mocks, never Azure."""
import argparse
import hashlib
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).parent
LOCK = threading.Lock()



def runs_directory(language):
    data_root = os.environ.get('LAB_DATA_ROOT')
    return Path(data_root) / language / 'runs' if data_root else ROOT / language / 'runs'


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0


def project_run(folder):
    """Allowlist presentation fields; never serve source manifests or headers."""
    manifest = read_json(folder / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("Invalid manifest")
    if manifest.get("schema_version") != 1 or manifest.get("mode") not in ("LIVE_AZURE", "LOCAL_HTTP_MOCK"):
        raise ValueError("Unsupported evidence")
    summary = read_json(folder / "summary.json")
    target = manifest["target"]
    if not isinstance(summary, dict) or not isinstance(target, dict):
        raise ValueError("Invalid evidence objects")
    if manifest.get("implementation") not in ("python", "dotnet") or target.get("provider") not in ("azure_openai", "mai_thinking", "claude", "mai_image"):
        raise ValueError("Unsupported runtime or provider")
    if not isinstance(manifest.get("request_count"), int) or not 1 <= manifest["request_count"] <= 200:
        raise ValueError("Invalid request count")
    signature = [manifest.get(k) for k in ("mode", "target", "prompt_sha256", "output_limit", "request_count", "mock_axis", "client_window_seconds", "schema_version")]
    attempts = []
    for line in (folder / "attempts.jsonl").read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict):
            raise ValueError("Invalid attempt")
        attempts.append({key: number(entry.get(key)) for key in ("job", "attempt", "status", "sent_after_seconds", "http_seconds")})
        attempts[-1]["outcome"] = entry.get("outcome", "unknown")
        attempts[-1]["retry_wait"] = number(entry.get("proposed_retry_wait_seconds"))
    return {
        "id": hashlib.sha256(str(folder).encode()).hexdigest()[:16],
        "signature": hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest(),
        "runtime": manifest["implementation"], "mode": manifest["mode"],
        "scenario": manifest["scenario"], "provider": target["provider"],
        "model": target.get("model", target["provider"]),
        "started": manifest["started_at_utc"], "count": number(manifest["request_count"]),
        "outputLimit": number(manifest["output_limit"]), "concurrency": number(manifest["concurrency"]),
        "rpm": number(manifest.get("client_rpm")),
        "summary": {key: number(summary.get(key)) for key in ("logical_requests", "http_attempts", "completed_responses", "http_429", "retries", "elapsed_seconds", "p95_e2e_seconds")},
        "attempts": attempts,
    }


def runs():
    result = []
    skipped = 0
    for language in ("python", "dotnet"):
        for manifest in runs_directory(language).glob("*/manifest.json"):
            try:
                result.append(project_run(manifest.parent))
            except (OSError, ValueError, KeyError, TypeError):
                skipped += 1
    seed = ASSETS / 'recordings.json'
    if seed.exists():
        result.extend(read_json(seed))
    return {"runs": sorted(result, key=lambda run: run["started"], reverse=True)[:200], "skipped": skipped,
            "dotnet": bool(shutil.which("dotnet"))}


def command(data):
    if set(data) != {"runtime", "target", "scenario"}:
        raise ValueError("Only runtime, target and scenario are accepted")
    runtime, target, scenario = (data[k] for k in ("runtime", "target", "scenario"))
    if runtime not in ("python", "dotnet") or target not in ("aoai", "mai") or scenario not in ("burst", "retry", "paced"):
        raise ValueError("Unsupported simulation")
    prefix = [sys.executable, "-B", str(ROOT / "python/lab.py")] if runtime == "python" else ["dotnet", "run", "--project", str(ROOT / "dotnet/FoundryLab"), "--configuration", "Release", "--"]
    if runtime == 'dotnet' and os.environ.get('LAB_DOTNET_DLL'):
        prefix = ['dotnet', os.environ['LAB_DOTNET_DLL']]
    return prefix + ["run", "--config", str(ROOT / runtime / "config.example.json"), "--target", target,
                     "--scenario", scenario, "--requests", "6", "--concurrency", "3", "--output-limit", "128",
                     "--max-attempts", "3", "--attempt-budget", "18", "--deadline", "20", "--client-rpm", "60",
                     "--mock-axis", "rpm", "--mock-window", "2", "--out", str(runs_directory(runtime))]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body, content_type="application/json"):
        payload = json.dumps(body).encode() if content_type == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A closed browser must not turn a completed run into a server error.

    def trusted(self):
        host = self.headers.get("Host", "")
        return host == f"127.0.0.1:{self.server.server_port}" and self.headers.get("Origin", f"http://{host}") == f"http://{host}"

    def do_GET(self):
        if not self.trusted():
            return self.respond(403, {"error": "Loopback origin required"})
        if self.path == "/api/runs":
            return self.respond(200, runs())
        assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
        assets["/portal.css"] = ("portal.css", "text/css")
        if self.path not in assets:
            return self.respond(404, {"error": "Not found"})
        name, mime = assets[self.path]
        payload = (ASSETS / name).read_bytes()
        self.respond(200, payload, mime)

    def do_POST(self):
        if not self.trusted() or self.headers.get("Content-Type") != "application/json":
            return self.respond(403, {"error": "Same-origin JSON required"})
        if self.path != "/api/run":
            return self.respond(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid request size")
            args = command(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError, KeyError):
            return self.respond(400, {"error": "Invalid simulation settings"})
        if not LOCK.acquire(blocking=False):
            return self.respond(409, {"error": "A simulation is already running"})
        try:
            completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180, shell=False)
            if completed.returncode:
                return self.respond(500, {"error": "Simulation failed. Check the runtime installation and CLI locally."})
            self.respond(200, runs())
        except (OSError, subprocess.TimeoutExpired):
            self.respond(500, {"error": "Runtime unavailable or simulation timed out"})
        finally:
            LOCK.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Demo console: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
