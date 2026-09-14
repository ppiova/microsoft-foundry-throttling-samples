# Understand the Code and Adapt It to Your Project

Commands on this page run from `python/`. The C# / .NET 10 engine is independent and exposes the same scenarios; see [Choose your language](../README.md#choose-your-language) for its equivalent commands.

The question behind this lab is what evidence you need before requesting more capacity. The lab follows a request through to a report. It does not infer an incident's root cause from an HTTP status alone.

## 1. Configuration: know what you are testing

`config.example.json` separates the target, identity, and metadata. Credentials come from environment variables; their values do not belong in this file. Model ID and deployment name are different fields.

Before a real test, complete `quota_scope`: which deployments share this limit? Record when you checked it. The lab does not automatically query portal quotas or know about later changes. `verified_limits` documents your evidence; it does not configure the local policy automatically.

An empty quota field means “not documented,” not zero or unlimited.

## 2. Adapters: each provider has its own contract

In `adapters.py`, `payload()` builds different request bodies:

| Provider | Route | Output parameter | API key header |
|---|---|---|---|
| Azure OpenAI | `/openai/v1/responses` | `max_output_tokens` | `api-key` |
| Claude | `/anthropic/v1/messages` | `max_tokens` | `x-api-key` |
| MAI-Thinking | `/mai/v1/chat/completions` | `max_completion_tokens` | `api-key` |
| MAI Image | `/mai/v1/images/generations` | Image dimensions; no text output cap | `api-key` |

Claude adds `anthropic-version`. Each adapter supports the bearer mode configured for the relevant contract. Microsoft sources for these details are in [SOURCES.md](SOURCES.md).

The transport uses REST directly so every HTTP attempt is visible without another layer of SDK retries. If you switch to an SDK, assign retry responsibility to one layer and test its behavior.

## 3. Concurrency and pacing are different controls

In `lab.py`, `ThreadPoolExecutor` bounds the number of jobs handled concurrently. A job may be waiting before a send or between retries; worker count is not an active connection metric.

`Gate.acquire()` controls admission. For RPM, it uses an interval of `60 / client_rpm` seconds between attempts. Even with six workers, the next send waits for its turn. A semaphore or worker pool alone does not enforce RPM.

The console prints `t=...` when sending. Compare `burst` and `paced` timestamps: the arrival pattern changes even if Azure does not return a 429.

## 4. Tokens: estimate to regulate, measure to learn

`--input-estimate` is an explicit operator estimate. It is not produced by a tokenizer or verified automatically. The lab reserves this estimate plus the maximum output before every attempt; it does not label the reservation as billed usage.

`guarded` supports separate budgets:

```powershell
python -B lab.py run --target claude --scenario guarded --client-input-budget 256 --client-output-budget 256 --input-estimate 128 --output-limit 128 --mock-axis otpm --client-rpm 600
```

This local example allows two reservations per window. The mock server and token guard use a two-second window by default to make waiting visible in a demo. **These are not Azure TPM values.** With `--live`, the token guard uses a 60-second window.

For Azure OpenAI and MAI-Thinking, `--client-token-budget` supplies a combined local budget. For Claude, use `--client-input-budget` and `--client-output-budget` to demonstrate the dimensions independently. Do not add a text TPM reservation for MAI Image; its requests are paced using RPM in this lab.

`numeric_usage()` preserves the provider's original usage field names. Claude may return `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens`. We do not sum all of them as ITPM. The example does not configure prompt caching; it retains the breakdown when available.

Reservations are not refunded after actual usage is known. This is a conservative local policy, not Microsoft's algorithm. Underestimation can still lead to 429s; overestimation can unnecessarily reduce throughput. For variable prompts, replace the constant estimate with per-request estimates and validate them.

## 5. An attempt: status, headers, usage, and outcome

`Transport.send()` returns HTTP status, selected headers, and a response summary without saving text or images. A real image request still generates an image and may incur charges even though the lab discards the content.

`response_info()` distinguishes HTTP success from generation completion. A response cut short by an output cap is not counted as complete. This check does not evaluate accuracy, usefulness, or quality.

`evidence_hint` identifies a few phrases in error messages. It does not cover every format or provide a definitive classification. A null value means no matching hint was found. Missing headers are omitted rather than converted to zero.

## 6. Retries: wait, reenter admission, and stop

The simplified `job()` flow is:

```python
for attempt in range(1, max_attempts + 1):
    gate.acquire(deadline)      # Retries pass through the same controls.
    status, headers, info = transport.send(prompt, output_limit, timeout)
    record_attempt(status, headers, info)
    if status != 429:
        break
    delay = retry_delay(headers, attempt)
    if delay_exceeds_remaining_time(delay):
        break
    sleep(delay)
```

This snippet illustrates the flow. The executable implementation in `lab.py` also checks attempt exhaustion. `retry_delay()` prioritizes the server's delay and falls back to exponential backoff with jitter when no valid delay is available. If the requested wait exceeds the remaining time, the operation stops; the delay is not shortened to send early.

400, 401, and 403 responses stop without retrying. All other statuses except 429 also stop, including 5xx: handling transient failures beyond throttling is outside this example's scope. Transport failures are not automatically resent because the operation's outcome may be unknown.

## 7. Metrics: avoid misleading conclusions

Suppose six logical requests create eight attempts and two 429s. The 429 rate is `2/8` of HTTP attempts. If all six eventually generate complete responses, they recovered, but incurred waiting time.

E2E p95 includes every logical request, including failures, and starts when the batch is submitted. HTTP p95 measures attempt duration only. Success can improve while latency gets worse; both are reported.

With six requests, p95 is effectively the worst case. This is useful for teaching, not for estimating a production SLO. A performance study needs a representative sample and repeated controlled experiments with an agreed budget.

## 8. Connect the lab to Azure Monitor

Record the run's UTC interval and target. In Azure Monitor, filter the resource and deployment, examine requests/errors and input/output usage, and align the interval with `attempts.jsonl`. First check the metrics available for that resource type and provider.

The Microsoft monitoring reference is in [SOURCES.md](SOURCES.md). No KQL query with assumed table names is included: metric export and diagnostic settings depend on the environment. Chart aggregation can hide bursts visible in per-attempt timestamps.

## 9. What about a second subscription?

This decision needs evidence inference code cannot invent: approved quota, pool scope, available capacity, other workloads, and project requirements. Use `inspect_azure.ps1` to collect allocations and metric definitions, then check them against the portal.

To evaluate another target, copy the configuration, document its quota, and run the same workload there. The strict comparator rejects different targets. Present those separate reports as a target-change experiment and explain which variables changed; do not call it a simultaneous load-balancing test.

The lab does not implement a cross-subscription router. Microsoft documents backend pools in Azure API Management for that extension. Targets sharing quota must not be treated as independent budgets. Identify the limit you expect to increase before designing load balancing.

## 10. Adaptation checklist

- Select a model, version, lifecycle status, and contract supported in your environment.
- Replace the constant estimate with a strategy validated for your inputs.
- Coordinate limits across instances sharing quota; this Python lock covers one run.
- Integrate managed identity or token renewal for your platform.
- Export telemetry and define alerts based on your SLO.
- Test streaming, cancellation, incomplete responses, and additional errors your application uses.
- Calculate costs from applicable pricing and usage; an attempt cap is not a monetary budget.

These are adaptation considerations, not a claim that this lab is a complete production client.
