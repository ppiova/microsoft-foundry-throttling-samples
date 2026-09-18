"""Separate REST contracts. Microsoft references are listed in SOURCES.md."""
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from credentials import token_provider

PATHS = {
    "azure_openai": "/openai/v1/responses",
    "claude": "/anthropic/v1/messages",
    "mai_thinking": "/mai/v1/chat/completions",
    "mai_image": "/mai/v1/images/generations",
}


def payload(provider, deployment, prompt, output_limit):
    if provider == "azure_openai":
        return dict(model=deployment, input=prompt, max_output_tokens=output_limit, store=False)
    if provider == "claude":
        return dict(model=deployment, messages=[dict(role="user", content=prompt)],
                    max_tokens=output_limit)
    if provider == "mai_thinking":
        return dict(model=deployment, messages=[dict(role="user", content=prompt)],
                    max_completion_tokens=output_limit, stream=False)
    if provider == "mai_image":
        return dict(model=deployment, prompt=prompt, width=1024, height=1024)
    raise ValueError("Unknown provider")


def numeric_usage(body):
    """Preserve original field names; usage is not the rate-limit counter."""
    def clean(obj):
        if not isinstance(obj, dict):
            return {}
        return {k: clean(v) if isinstance(v, dict) else v for k, v in obj.items()
                if isinstance(v, (int, float, dict)) and not isinstance(v, bool)}
    return clean(body.get("usage", {}))


def response_info(provider, status, body):
    """Do not export text, images, prompts, or complete error messages."""
    info = {"usage": numeric_usage(body), "outcome": "http_error", "error_code": None,
            "evidence_hint": None}
    if not 200 <= status < 300:
        error = body.get("error", body)
        error = error if isinstance(error, dict) else {}
        code = error.get("code") or error.get("type")
        if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
            info["error_code"] = code
        # Text hints are not an authoritative classification.
        message = str(error.get("message", "")).lower()
        patterns = (("capacity", "capacity_message"), ("high demand", "capacity_message"),
                    ("output token", "output_token_message"),
                    ("input token", "input_token_message"),
                    ("token rate", "token_rate_message"),
                    ("request rate", "request_rate_message"))
        info["evidence_hint"] = next((label for text, label in patterns if text in message), None)
        return info
    if provider == "azure_openai":
        info["outcome"] = "completed" if body.get("status") == "completed" else "incomplete_or_unknown"
    elif provider == "claude":
        info["outcome"] = "completed" if body.get("stop_reason") in ("end_turn", "stop_sequence") else "incomplete_or_other"
    elif provider == "mai_thinking":
        choices = body.get("choices") or []
        info["outcome"] = "completed" if isinstance(choices, list) and choices and isinstance(choices[0], dict) and choices[0].get("finish_reason") == "stop" else "incomplete_or_other"
    else:
        info["outcome"] = "completed" if body.get("data") else "empty_or_unknown"
    return info


def observed_headers(headers):
    return {k.lower(): v for k, v in headers.items()
            if k.lower().startswith(("x-ratelimit-", "anthropic-ratelimit-"))
            or k.lower() in ("retry-after", "retry-after-ms", "request-id", "x-request-id", "apim-request-id")}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Transport:
    def __init__(self, target, mock_origin=None):
        self.provider = target["provider"]
        self.deployment = target["deployment"]
        origin = mock_origin or os.environ.get(target.get("endpoint_env", ""))
        if not origin:
            raise ValueError("Set the configured endpoint environment variable")
        parsed = urlsplit(origin)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.path not in ("", "/")
                or (not mock_origin and parsed.scheme != "https")):
            raise ValueError("The endpoint must be the HTTPS resource origin, without paths or secrets")
        self.url = origin.rstrip("/") + PATHS[self.provider]
        self.headers = {"Content-Type": "application/json"}
        self.token_provider = None
        if self.provider == "claude":
            self.headers["anthropic-version"] = "2023-06-01"
        if not mock_origin:
            auth = target.get("auth", "entra")
            if auth == "entra":
                self.token_provider = token_provider(target)
                return
            if auth not in ("bearer", "api_key"):
                raise ValueError("auth must be entra, bearer, or api_key")
            credential = os.environ.get(target.get("credential_env", ""))
            if not credential:
                raise ValueError("Set the configured credential environment variable")
            if auth == "bearer":
                self.headers["Authorization"] = "Bearer " + credential
            elif target["auth"] == "api_key":
                self.headers["x-api-key" if self.provider == "claude" else "api-key"] = credential
            else:
                raise ValueError("auth must be bearer or api_key")

    def close(self):
        if self.token_provider:
            self.token_provider.close()

    def send(self, prompt, output_limit, timeout):
        data = json.dumps(payload(self.provider, self.deployment, prompt, output_limit)).encode()
        headers = dict(self.headers)
        if self.token_provider:
            headers["Authorization"] = "Bearer " + self.token_provider()
        request = Request(self.url, data=data, headers=headers)
        # Use an opener per attempt; do not share mutable HTTP state across threads.
        try:
            response = build_opener(NoRedirect()).open(request, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            status = response.code
            headers = observed_headers(response.headers)
            raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            return status, headers, {"outcome": "body_limit", "usage": {}}
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                body = {}
        except (ValueError, UnicodeDecodeError):
            body = {}
        return status, headers, response_info(self.provider, status, body)
