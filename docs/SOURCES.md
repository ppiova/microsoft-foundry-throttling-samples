# Microsoft Source Map

Checked September 8, 2026. Local policies are educational implementation choices, not universal limits or reproductions of Microsoft's algorithm.

| Official source | Supports | Implementation or use |
|---|---|---|
| [Azure OpenAI quota management](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota?WT.mc_id=AI-MVP-5004753) | Headers, retries, quota, and rate limiting | Recovery and observation in `lab.py` |
| [Azure OpenAI Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses?WT.mc_id=AI-MVP-5004753) | Endpoint, authentication, and requests | Azure OpenAI adapter |
| [Responses REST reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/responses?preserve-view=true&view=rest-microsoft-foundry-v1-preview&WT.mc_id=AI-MVP-5004753) | Output cap, store, status, and usage | `payload()` and `response_info()` |
| [Call Claude in Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude?WT.mc_id=AI-MVP-5004753) | Messages, version, authentication, and max_tokens | Claude adapter |
| [Claude quotas and availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models?WT.mc_id=AI-MVP-5004753#quotas-and-rate-limits) | RPM, ITPM, OTPM, and shared scope | Configuration and guide |
| [MAI-Thinking-1](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-thinking?WT.mc_id=AI-MVP-5004753) | Chat completions, max_completion_tokens, and preview | MAI text adapter |
| [MAI Image](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-image?WT.mc_id=AI-MVP-5004753) | Generation, dimensions, authentication, RPM, and preview | MAI image adapter |
| [Monitor Foundry models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models?WT.mc_id=AI-MVP-5004753) | Resource and deployment monitoring | Evidence correlation |
| [Azure OpenAI performance and latency](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/latency?WT.mc_id=AI-MVP-5004753) | Traffic and latency measurement | Attempt versus E2E interpretation |
| [AI gateway in API Management](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities?WT.mc_id=AI-MVP-5004753) | Endpoint traffic management and distribution | Future architecture extension; not implemented |
| [List deployments with Azure CLI](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/account/deployment?WT.mc_id=AI-MVP-5004753#az-cognitiveservices-account-deployment-list) | Deployment inventory | `inspect_azure.ps1` |
| [Azure CLI metric definitions](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?WT.mc_id=AI-MVP-5004753#az-monitor-metrics-list-definitions) | Metric discovery | `inspect_azure.ps1` |

The collector's Usages API is documented in “Programmatically check quota and capacity” in the quota management source. It provides management-plane evidence, not an inference counter in real time.

## Distinctions preserved in the lab

- Output parameters and API key headers are provider-specific.
- Headers are recorded when present, not assumed to exist in every response.
- Claude usage is not all added together as ITPM.
- Local budgets are not labeled Azure quota.
- GA status, quota, and regional availability are separate considerations.

Before live execution, verify access, the contract, and lifecycle status for each model. Documentation does not establish that a model is deployed in the reader's subscription. Real inference uses configurable endpoints and deployment names rather than a fixed default model.
