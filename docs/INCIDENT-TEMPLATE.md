# Project Incident Investigation Template

Use verified information. “Unknown” is a valid answer.

- Date and UTC interval:
- Application, environment, and owner:
- Provider, model, version, and GA/preview status:
- Deployment name, hosting, region, and deployment type:
- Quota pool scope and other known consumers:
- Approved quota and target allocation, with verification date:
- Logical requests and HTTP attempts:
- Sanitized error codes and messages:
- Request IDs for support:
- Observed headers, including limits and retry delay:
- Arrival pattern and concurrency:
- Input size, output cap, and returned usage:
- SDK, application, and gateway retries:
- Azure Monitor metrics for the same interval:
- Impact: failed requests, incomplete responses, and latency:

## Hypothesis and experiment

- Hypothesis being evaluated:
- Supporting evidence and missing evidence:
- Change to test while keeping other factors comparable:
- Request/time budget and expected outcome:
- Observed result and limitations:
- Decision and justification:

## If proposing another target

- Does it have independent effective quota or share the same pool?
- What workload would move, and what improvement is expected?
- Which data, hosting, and operational requirements constrain the target?
- What experiment will verify the improvement?

This template does not replace a support investigation when service behavior or capacity requires confirmation.
