"""Optional Azure Identity authentication; local simulation imports no Azure packages."""
import os
import threading
import time

SCOPES = {
    "azure_openai": "https://ai.azure.com/.default",
    "claude": "https://ai.azure.com/.default",
    "mai_thinking": "https://cognitiveservices.azure.com/.default",
    "mai_image": "https://cognitiveservices.azure.com/.default",
}


class AuthenticationError(Exception):
    """Safe diagnostic without credential provider exception text."""


class RenewableToken:
    def __init__(self, credential, scope, clock=time.time):
        self.credential, self.scope, self.clock = credential, scope, clock
        self.token = None
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            try:
                if self.token is None or self.token.expires_on <= self.clock() + 120:
                    self.token = self.credential.get_token(self.scope)
                return self.token.token
            except Exception:
                raise AuthenticationError("Authentication failed; check local sign-in and resource permissions") from None

    def close(self):
        self.credential.close()


def token_provider(target):
    try:
        from azure.identity import AzureCliCredential, DefaultAzureCredential
    except ImportError:
        raise ValueError("Entra authentication requires: pip install -r requirements-live.txt") from None
    mode = target.get("credential_type", "azure_cli")
    if mode not in ("azure_cli", "default"):
        raise ValueError("credential_type must be azure_cli or default")
    tenant = os.environ.get(target.get("tenant_env", "AZURE_TENANT_ID"))
    credential = (AzureCliCredential(tenant_id=tenant, process_timeout=10) if mode == "azure_cli"
                  else DefaultAzureCredential(exclude_interactive_browser_credential=True))
    return RenewableToken(credential, SCOPES[target["provider"]])
