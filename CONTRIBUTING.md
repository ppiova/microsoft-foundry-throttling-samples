# Contributing

Thanks for considering a contribution. This is an independent community project that teaches how to
observe and mitigate HTTP 429, and how to gather evidence before asking for more capacity. Changes
that keep it a teaching tool are easier to accept than changes that turn it into a production
client.

## Before you start

Open an issue first for anything beyond a typo or a small documentation fix. It is faster to agree
on the approach than to rework a finished pull request. Use the
[issue templates](https://github.com/ppiova/microsoft-foundry-throttling-samples/issues/new/choose).

Read [docs/CODE-GUIDE.md](docs/CODE-GUIDE.md) if you are touching either engine. It explains the
adapters, admission control, the token guard and the retry loop, and which behaviors are deliberate
teaching choices rather than reproductions of Microsoft's algorithm.

## Conventions

Use **US English** for documentation, code comments, examples, prompts, CLI help, console messages,
and reports.

Keep provider-specific claims linked to Microsoft documentation, and add the source to
[docs/SOURCES.md](docs/SOURCES.md) when you introduce a new one. Distinguish documented behavior,
local implementation choices, and measured results. Label local HTTP mock data clearly and do not
present it as a Foundry benchmark.

The Python and C# engines are **independent implementations, not ports**. A behavior change in one
usually belongs in the other, and `scripts/validate_parity.py` checks that both still produce
comparable evidence. Say so explicitly in the pull request if a change is deliberately one sided.

Keep pull requests focused on one change.

## Validation

Run these before submitting:

```powershell
python -B -m unittest discover -s python/tests -v
python -B python/lab.py run --config python/config.example.json --scenario preflight
dotnet test dotnet/FoundryLab.Tests --configuration Release
dotnet run --project dotnet/FoundryLab -- run --scenario preflight
node --test demo/test_ui.cjs
python -B scripts/validate_parity.py
```

If you changed the slides, confirm the deck still has fourteen sections and regenerate the public
PDF:

```powershell
python -B -m unittest demo.test_public_slides
python -m pip install reportlab
python -B scripts/export_slides_pdf.py
```

Review the rendered PDF after regenerating it. CI runs the equivalent checks on Windows and Linux
and requires no Azure credentials.

## What not to commit

Credentials, endpoints, tokens, local configuration, request IDs, real incident data, and live run
artifacts. Update relative document links when renaming a file.

## Code of conduct and security

This project follows the [Microsoft Open Source Code of Conduct](CODE_OF_CONDUCT.md). Report
vulnerabilities privately as described in [SECURITY.md](SECURITY.md) rather than in a public issue.

## Licensing of contributions

Contributions are accepted under the repository's [MIT License](LICENSE). By submitting a pull
request you confirm you have the right to license your contribution under those terms.

This repository does not currently require a Contributor License Agreement. If the project is ever
adopted by a Microsoft organization, contributions from that point on would be subject to the
[Microsoft CLA](https://cla.opensource.microsoft.com), and the security policy and copyright notice
would be updated accordingly.
