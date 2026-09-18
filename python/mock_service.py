"""Educational local HTTP server. Does NOT emulate the internal Foundry algorithm."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_mock(axis="rpm", window=2.0, clock=time.monotonic):
    lock = threading.Lock()
    state = {"start": clock(), "used": 0}
    limits = {"rpm": 2, "tpm": 512, "itpm": 256, "otpm": 256}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            routes = {"/openai/v1/responses": "max_output_tokens", "/anthropic/v1/messages": "max_tokens",
                      "/mai/v1/chat/completions": "max_completion_tokens", "/mai/v1/images/generations": None}
            if self.path not in routes:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError()
                body = json.loads(self.rfile.read(length))
                parameter = routes[self.path]
                if (not isinstance(body, dict) or not isinstance(body.get("model"), str)
                        or (parameter and (type(body.get(parameter)) is not int or body[parameter] <= 0))):
                    raise ValueError()
            except (ValueError, TypeError):
                self.send_error(400)
                return
            text = body.get("input", body.get("prompt", ""))
            if not text:
                messages = body.get("messages", [])
                if not isinstance(messages, list) or any(not isinstance(item, dict) or not isinstance(item.get("content"), str) for item in messages):
                    self.send_error(400)
                    return
                text = " ".join(item["content"] for item in messages)
            if not isinstance(text, str) or not text:
                self.send_error(400)
                return
            tokens = max(1, len(text) // 4)  # Fictional estimate for the local server ONLY.
            output = body.get("max_output_tokens", body.get("max_tokens", body.get("max_completion_tokens", 0)))
            cost = {"rpm": 1, "tpm": tokens + output, "itpm": tokens, "otpm": output}.get(axis, 1)
            with lock:
                now = clock()
                if now - state["start"] >= window:
                    state.update(start=now, used=0)
                rejected = axis == "capacity" or state["used"] + cost > limits.get(axis, 0)
                if not rejected:
                    state["used"] += cost
                remaining = max(0, limits.get(axis, 0) - state["used"])
                wait_ms = max(1, int((window - (now - state["start"])) * 1000) + 5)
            headers = {"x-request-id": "LOCAL-MOCK", "x-lab-mock-axis": axis}
            if axis == "rpm":
                headers["x-ratelimit-remaining-requests"] = str(remaining)
            elif axis == "tpm":
                headers["x-ratelimit-remaining-tokens"] = str(remaining)
            # Do not invent provider headers for ITPM/OTPM.
            if rejected:
                code = 429
                headers["retry-after-ms"] = str(wait_ms)
                message = "System capacity high demand" if axis == "capacity" else f"{axis} rate limit exceeded"
                result = {"error": {"code": "local_mock_" + axis, "message": message}}
            else:
                code = 200
                usage = {"input_tokens": tokens, "output_tokens": min(output, 12)}
                if "/anthropic/" in self.path:
                    result = {"stop_reason": "end_turn", "content": [], "usage": usage}
                elif "/images/" in self.path:
                    result = {"data": [{"b64_json": "LOCAL_PLACEHOLDER_NOT_AN_IMAGE"}]}
                elif "/mai/" in self.path:
                    result = {"choices": [{"finish_reason": "stop"}],
                              "usage": {"prompt_tokens": tokens, "completion_tokens": min(output, 12)}}
                else:
                    result = {"status": "completed", "output": [], "usage": usage}
            encoded = json.dumps(result).encode()
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"
