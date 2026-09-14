# Support

This is an independent community project maintained in the maintainer's own time. It is not covered
by a Microsoft support agreement and carries no service level commitment.

## How to get help with this lab

1. Read the [README](README.md) for setup, and [docs/RESULTS.md](docs/RESULTS.md) for how to
   interpret a run.
2. Check [docs/CODE-GUIDE.md](docs/CODE-GUIDE.md) if you are adapting the code to your own project.
3. Search [existing issues](https://github.com/ppiova/microsoft-foundry-throttling-samples/issues)
   before opening a new one.
4. Open an [issue](https://github.com/ppiova/microsoft-foundry-throttling-samples/issues/new/choose)
   using one of the templates.

Include your runtime versions, the scenario and synthetic settings you used, and a minimal
reproduction. Never paste credentials, endpoints, request IDs or raw live run reports into an issue.

## What this project cannot help with

**Throttling in your own Azure subscription.** This lab teaches you how to gather evidence about a
429; it cannot tell you why a specific deployment is rate limited. Use
[docs/INCIDENT-TEMPLATE.md](docs/INCIDENT-TEMPLATE.md) to structure that investigation, and open an
Azure support request for questions about service behavior, quota or capacity.

**Quota increases.** Those go through the Azure portal and your subscription's support channel.

**Microsoft Foundry product questions.** Use
[Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/?WT.mc_id=AI-MVP-5004753) and
the official Azure support channels. Provider specific behavior claimed in this repository is traced
to its source in [docs/SOURCES.md](docs/SOURCES.md).

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
