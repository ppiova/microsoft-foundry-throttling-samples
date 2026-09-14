# Security

This is an independent community project maintained by [Pablo Piovano](https://github.com/ppiova).
It is not a Microsoft product, and it is not covered by the Microsoft Security Response Center.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report them privately through
[GitHub Security Advisories](https://github.com/ppiova/microsoft-foundry-throttling-samples/security/advisories/new).
Expect an acknowledgement within 5 business days.

Include as much of the following as you can, which helps triage the report faster:

- Type of issue (for example: command injection, path traversal, exposed credential, SSRF).
- Full paths of the source files related to the issue.
- The affected branch or commit, or a direct URL.
- Any configuration required to reproduce it.
- Step-by-step reproduction instructions.
- Proof of concept, if you have one.
- Impact, including how an attacker might exploit it.

## Scope

In scope: the Python and C# engines, the local simulator server and its browser UI, the container
definitions, the Bicep templates, and the CI workflows.

Out of scope: vulnerabilities in Microsoft Foundry, Azure OpenAI or any other Azure service. Report
those to the [Microsoft Security Response Center](https://msrc.microsoft.com/create-report).
Findings that depend on a deliberately misconfigured deployment of this lab are also out of scope,
since the local target is documented for workstation use only.

## What this project handles

The default experience makes no network calls beyond loopback and stores no credentials. Live
execution reads endpoints and credentials from environment variables and from a local configuration
file that is excluded from Git. Reports keep operational evidence and exclude response content,
endpoints and request IDs. If you find a path where a secret, an endpoint or response content
reaches a committed file, a log or the browser UI, please report it.

## If this project moves to a Microsoft organization

This file would be replaced by the standard Microsoft `SECURITY.md`, which directs reports to the
Microsoft Security Response Center, and the LICENSE copyright would be updated accordingly.
