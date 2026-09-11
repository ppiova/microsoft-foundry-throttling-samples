Microsoft Foundry Throttling Samples
===================================

Independent community samples by Pablo Piovano. MIT licensed.
Not an official Microsoft product or a production retry library.

Explore request throttling, bounded retries and pacing using independent
Python and C# / .NET 10 implementations with a shared evidence format.
The browser UI supports Azure OpenAI and Microsoft MAI adapters. The CLI
also includes Claude and MAI image adapters; availability for live use
must be verified in your own Azure subscription.

QUICK START: BROWSER UI (NO AZURE ACCOUNT REQUIRED)

Requirements: Python 3.10+; install .NET SDK 10 if choosing C# in the UI.
Run commands from the repository root:

    python demo/server.py

Open http://127.0.0.1:8765 in your browser. Select Python or C# / .NET 10,
Azure OpenAI or Microsoft MAI, and Local HTTP simulator. Run Burst, Retry
with backoff and Paced requests. The first C# run can take longer while
NuGet dependencies are restored. Internet is needed for that restore.

Every UI execution is a bounded loopback simulation: six requests,
three workers, output cap 128 and a two-second synthetic RPM window.
The UI does not invoke Azure model inference. It starts with no saved
executions; create your own using Run local simulation.

Strategy configures the next execution. Saved execution selects an
existing result. Replay animates saved timestamps; KPI cards always show
final totals. Compare matches workload and service settings across runs.
Generated reports are stored locally and ignored by Git.

HTML SLIDES

Open http://127.0.0.1:8765/slides after starting the UI. The ten-slide deck
explains rate limits, retries, pacing and how to interpret evidence. Use
arrow keys, Page Up/Down, Home/End or the slide selector; F toggles full
screen. The deck includes a link to the simulator. It contains no speaker
notes or presenter mode. Microsoft Learn links retain MVP attribution.

QUICK START: PYTHON CLI

Local simulation uses only the Python standard library:

    python python/lab.py run --config python/config.example.json --scenario burst --out python/runs
    python python/lab.py run --config python/config.example.json --scenario retry --out python/runs
    python python/lab.py run --config python/config.example.json --scenario paced --out python/runs
    python python/lab.py run --help

QUICK START: C# / .NET 10 CLI

    dotnet run --project dotnet/FoundryLab --configuration Release -- run --scenario burst --out dotnet/runs
    dotnet run --project dotnet/FoundryLab --configuration Release -- run --scenario retry --out dotnet/runs
    dotnet run --project dotnet/FoundryLab --configuration Release -- run --scenario paced --out dotnet/runs

Each engine implements preflight, baseline, burst, retry, paced and guarded
scenarios. Mock axes include rpm, tpm, itpm, otpm and capacity; the browser
walkthrough uses rpm. Run files contain a manifest, attempts, job outcomes
and summary. Engines can generate Markdown reports locally; none of those
reports or private recordings are distributed in this repository.

HOW TO INTERPRET RESULTS

A logical request may produce several HTTP attempts. Bounded retries can
improve completion while increasing traffic and waiting. Pacing changes
the arrival pattern and does not guarantee zero 429 responses. A concurrency
limit is not a fixed request-rate limit.

Synthetic limits are not an Azure deployment's quota. End-to-end timings
include queueing, retry waits and HTTP time. Small sample workloads are not
model or language benchmarks. An HTTP success and a completed generation
are tracked separately. These samples do not establish that adding another
subscription will resolve a production incident.

OPTIONAL LIVE AZURE CALLS

Live inference requires explicit --live, your own deployment, authorized
identity, verified capacity and a populated local config. It can incur
charges. Default execution remains a loopback simulation.

1. Copy your language's config.example.json to config.local.json.
2. Replace deployment/model/region placeholders for your own target and
   set its endpoint environment variable. Do not commit local configs.
3. Sign in with Azure CLI using az login and select your subscription.
   The default credential_type is azure_cli; use least-privilege access
   appropriate to the provider and direct inference endpoint.
4. For Python live Entra authentication, install the optional dependencies:
       python -m pip install -r python/requirements-live.txt
5. Start with a single preflight after checking run --help:
       python python/lab.py run --config python/config.local.json --target aoai --scenario preflight --live --out python/runs

Use --target mai, claude or image only after configuring that target and
verifying its model availability, endpoint contract and provider-specific
limits. Recorded Azure run in the UI is read-only and initially empty.
No organization deployments, credentials or recorded live results ship here.

INFRASTRUCTURE

infra/main.bicep and infra/modules/foundry.bicep describe Foundry resources.
Review infra/parameters.example.json and supply your own subscription,
region, model versions and capacity. Use PowerShell 7 and Azure CLI:

    ./infra/deploy.ps1 -SubscriptionId YOUR-SUBSCRIPTION-ID -Mode WhatIf

The wrapper defaults to WhatIf. Deployment requires -Mode Deploy. Provider
availability and quota must be checked in your subscription. Claude requires
real organization details and explicit Marketplace terms acceptance through
-AcceptClaudeMarketplaceTerms. No provider terms are accepted by cloning or
running the simulator. Review the Bicep parameters before deployment.

infra/hosting.bicep and infra/container-app.bicep are optional Azure Container
Apps templates. Dockerfile builds both engines. The cloud entry point fails
closed until access is configured. It trusts platform-validated Entra headers
ONLY behind Container Apps Easy Auth; do not expose it behind a proxy that
allows clients to forge those headers. Configure your own single-tenant app,
user assignments, allowedUserIds, clientId and managed-identity federation.
The local server binds only to loopback and needs no cloud authentication.
Do not treat the cloud container as a ready-to-use anonymous web service.

TESTS (FROM REPOSITORY ROOT)

    python -m unittest discover -s python/tests -v
    python -m pip install -r demo/requirements-cloud.txt
    python -m unittest discover -s demo -p "test_*.py" -v
    node --test demo/test_ui.cjs
    dotnet test dotnet/FoundryLab.Tests --configuration Release
    python scripts/validate_parity.py

Node.js 18+ is needed for UI regression tests. CI also validates Bicep,
collector behavior and container startup. No Azure credentials are needed
for the local test suites.

MICROSOFT DOCUMENTATION

Quota management:
https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota?WT.mc_id=AI-MVP-5004753
Retry pattern:
https://learn.microsoft.com/en-us/azure/architecture/patterns/retry?WT.mc_id=AI-MVP-5004753
Foundry access control:
https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry?WT.mc_id=AI-MVP-5004753

CONTRIBUTING

Open an issue with a minimal reproduction, runtime version and synthetic
settings. Never attach keys, tokens, prompts, private endpoints or raw live
reports. Send pull requests with focused changes and relevant test results.
