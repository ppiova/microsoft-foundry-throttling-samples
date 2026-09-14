# Security

This is an independent community project maintained by [Pablo Piovano](https://github.com/ppiova).
It is not a Microsoft product, and it is not covered by the Microsoft Security Response Center.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report them privately through
[GitHub's private vulnerability reporting](https://github.com/ppiova/microsoft-foundry-throttling-samples/security/advisories/new)
on this repository. You should receive an acknowledgement within three business days.

Include as much of the following as you can, so the issue can be reproduced quickly:

- Type of issue (for example: credential exposure, command injection, path traversal, insecure default)
- Full paths of the source files involved
- The affected commit or tag
- Any special configuration needed to reproduce it
- Step-by-step reproduction instructions
- Proof-of-concept or exploit code, if available
- The impact, including how an attacker might exploit it

> **Note for the maintainer.** If this repository moves to a Microsoft-owned
> organization, replace this section with the standard Microsoft Security Response
> Center policy: reports then go to [MSRC](https://msrc.microsoft.com/create-report)
> or secure@microsoft.com, and the [Microsoft Bug Bounty](https://aka.ms/opensource/security/bounty)
> terms apply.

## Scope

In scope: the Python and C# engines, the local simulator server and its browser UI, the container
definitions, the Bicep templates, and the CI workflows.

Out of scope: vulnerabilities in Microsoft Foundry, Azure OpenAI or any other Azure service. Report
those to the [Microsoft Security Response Center](https://msrc.microsoft.com/create-report).
Findings that depend on deliberately publishing the local target to the internet are also out of
scope, since it is documented for workstation use only.

## What this lab does with credentials

This is demonstration code. Read this before pointing it at a resource you care about.

- **The default path uses no credentials at all.** Local simulation talks to a loopback HTTP mock.
  No Azure account, API key or network egress is involved, which is why the quick start needs none.
- **Keyless by default when live.** Targets are configured with `auth: entra` and a
  `credential_type` of `azure_cli`, so `python/credentials.py` acquires Entra tokens through
  `AzureCliCredential` or `DefaultAzureCredential`. `RenewableToken` refreshes a token 120 seconds
  before it expires rather than capturing one bearer string for the process lifetime.
  `DefaultAzureCredential` is constructed with the interactive browser credential excluded.
- **Keys are opt-in and never stored by this code.** When a target is configured for key
  authentication, the key is read from the environment variable named in `credential_env`. Nothing
  here writes a key to disk, a report or a log. `config.local.json` is gitignored and must never be
  committed.
- **Reports exclude response content by design.** `response_info()` does not export text, images,
  prompts or complete error messages. An error code is recorded only if it matches
  `[A-Za-z0-9_.-]{1,80}`, and free-text hints are a few matched phrases rather than a classification.
  The prompt is stored as a SHA-256 hash and a character count, not in clear text.
- **Response headers are allowlisted, not captured wholesale.** `observed_headers()` keeps only
  rate limit headers, `retry-after`, `retry-after-ms`, and the request ID headers. **Request IDs are
  therefore present in your local reports.** They are useful when opening an Azure support case and
  should not be pasted into a public issue.
- **A live image run still generates an image.** The lab discards the returned content and keeps
  only operational evidence, but the call reaches the generation service and may incur charges.
- **The container runs unprivileged and bound to loopback.** Non-root, read-only root filesystem,
  dropped Linux capabilities, a writable evidence volume, and a Compose binding to `127.0.0.1`. The
  local target is for workstation use; do not publish it as an anonymous internet service.
- **The cloud target fails closed.** It trusts identity headers only behind Azure Container Apps
  Easy Auth and refuses to serve until Entra authentication is configured.
- **Public network access is enabled in the template, deliberately.** `infra/modules/foundry.bicep`
  deploys with `disableLocalAuth: true`, so the account issues no usable key, and access is governed
  by Entra and RBAC instead. Production deployments should use private endpoints.

## Responsible AI

This lab measures **request outcomes**, not model output. That boundary is deliberate and worth
stating plainly:

- **No quality, accuracy or safety evaluation is performed.** A response is counted as complete or
  incomplete based on the provider's own status and stop reason. The lab never inspects whether an
  answer is correct, useful or appropriate.
- **Generated content is discarded**, including images. Only operational evidence is retained.
- **No content filtering is configured.** Live runs use whatever defaults your deployment has.
  Review them for your own use case.
- **The default data is synthetic.** Local responses are predefined fixtures, not model output, and
  the local MAI image response is a fictional marker rather than a generated image.
- **A synthetic 429 is a teaching example, not a measurement of Azure capacity.** Presenting these
  numbers as evidence about a real deployment's quota would be a misuse of the lab. See
  [docs/RESULTS.md](docs/RESULTS.md) for how to read them, and
  [docs/SOURCES.md](docs/SOURCES.md) for the Microsoft documentation behind each provider claim.

Assess the risks of any system you build from this code, and comply with the laws and safety
standards that apply to your use case.

## Automated checks

Every push and pull request runs:

| Check | Covers |
|---|---|
| CodeQL | Static analysis of Python, JavaScript, C# and the GitHub Actions workflows, weekly as well as per change |
| Unit and integration tests | Python 3.11 and 3.12 on Windows and Linux, plus .NET 10 on both |
| Cross-runtime parity | Both engines run the same scenarios and must produce comparable evidence |
| Container boundaries | The cloud target denies unconfigured access, and the local Compose workflow preserves evidence |
| Bicep | Template build, and PSRule for Azure against the Well-Architected rules |
| Dependabot | Weekly version updates for GitHub Actions, pip, NuGet and Docker |
| Secret scanning with push protection | The full history, and any push containing a recognized secret |

Workflow permissions are least privilege and every action is pinned by commit SHA.

Secret scanning and push protection are repository settings rather than workflows, and both are
enabled. **Dependabot security updates are not yet enabled**, which is what opens a pull request
when an advisory affects a dependency in use, separate from the weekly version updates.

`ps-rule.yaml` excludes the public access and private endpoint rules, with the reasoning recorded in
that file: a lab a reader deploys to follow along cannot sit behind a private endpoint. The exposure
those rules address is mitigated instead by `disableLocalAuth: true`, which leaves no key to steal.

## Supported versions

Only the default branch is maintained. Fixes are not backported to tags.
