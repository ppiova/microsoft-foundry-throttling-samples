using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace FoundryLab;

public static class Runner
{
    private static string Utc() => DateTimeOffset.UtcNow.ToString("O");
    private static double Round(double value) => Math.Round(value, 4);
    public static async Task<string> RunAsync(Options options)
    {
        options.Validate();
        var target = Evidence.Load(options.Config)["targets"]?[options.Target] as JsonObject ?? throw new ArgumentException("Missing target");
        var provider = target["provider"]?.ToString() ?? "";
        if (!Protocol.Paths.ContainsKey(provider)) throw new ArgumentException("Unknown provider");
        if (target["deployment"] is not JsonValue deployment || deployment.GetValueKind() != JsonValueKind.String
            || string.IsNullOrWhiteSpace(deployment.GetValue<string>())) throw new ArgumentException("Set a nonempty deployment name");
        if (options.Live && (target["deployment"]?.ToString() is null or "REPLACE_ME" or "")) throw new ArgumentException("Set the deployment name");
        var limits = options.Limits;
        if (provider == "mai_image" && limits.Count > 0) throw new ArgumentException("Image scenarios do not use text token budgets");
        if (provider != "mai_image" && options.Scenario == "guarded" && limits.Count == 0) throw new ArgumentException("guarded needs a local budget");
        _ = new Gate(options.Rpm, limits, options.Costs, options.AttemptBudget);
        await using var mock = options.Live ? null : await MockService.StartAsync(options.MockAxis, options.MockWindow);
        using var transport = new Transport(target, mock?.Origin);
        var prompt = string.Concat(Enumerable.Repeat("Explain why measuring request rates helps diagnose an API. ", options.PromptRepeat)) + " Respond in one sentence.";
        var id = DateTimeOffset.UtcNow.ToString("yyyyMMdd'T'HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8];
        var output = Path.GetFullPath(Path.Combine(options.Out, id));
        Directory.CreateDirectory(output);
        string mode = options.Live ? "LIVE_AZURE" : "LOCAL_HTTP_MOCK";
        var safeTarget = new JsonObject();
        foreach (var key in new[] { "provider", "deployment", "endpoint_env", "credential_env", "auth", "model", "version", "lifecycle", "hosting", "region",
                     "deployment_type", "quota_scope", "verified_limits", "credential_type" })
            if (target.ContainsKey(key)) safeTarget[key] = target[key]?.DeepClone();
        var manifest = new JsonObject {
            ["schema_version"] = 1, ["implementation"] = "dotnet", ["runtime_version"] = Environment.Version.ToString(),
            ["run_id"] = id, ["started_at_utc"] = Utc(), ["ended_at_utc"] = null,
            ["mode"] = mode, ["scenario"] = options.Scenario, ["target"] = safeTarget,
            ["prompt_sha256"] = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(prompt))).ToLowerInvariant(),
            ["prompt_chars"] = prompt.Length, ["output_limit"] = options.OutputLimit, ["request_count"] = options.Count,
            ["concurrency"] = options.Workers, ["client_rpm"] = options.Rpm,
            ["client_estimates"] = JsonSerializer.SerializeToNode(options.Costs), ["client_token_budgets"] = JsonSerializer.SerializeToNode(limits),
            ["client_window_seconds"] = options.Live ? 60 : options.MockWindow,
            ["mock_window_seconds"] = options.Live ? null : options.MockWindow,
            ["attempt_budget"] = options.AttemptBudget, ["max_attempts_per_job"] = options.Attempts,
            ["admission_deadline_seconds"] = options.Deadline, ["mock_axis"] = options.Live ? null : options.MockAxis,
            ["note"] = "metadata and verified_limits are user-supplied, not discovered from Azure"
        };
        Evidence.Save(Path.Combine(output, "manifest.json"), manifest);
        var attempts = new List<JsonObject>(); var jobs = new List<JsonObject>(); var sync = new object();
        File.WriteAllText(Path.Combine(output, "attempts.jsonl"), "");
        var watch = Stopwatch.StartNew();
        var gate = new Gate(options.Rpm, limits, options.Costs, options.AttemptBudget, options.Live ? 60 : options.MockWindow, () => watch.Elapsed.TotalSeconds);
        using var workers = new SemaphoreSlim(options.Workers);
        Console.WriteLine($"{mode} | {options.Target} | {options.Scenario} | {options.Count} requests");
        await Task.WhenAll(Enumerable.Range(1, options.Count).Select(async index =>
        {
            await workers.WaitAsync();
            try
            {
                var queued = watch.Elapsed.TotalSeconds;
                string outcome = "not_sent"; int? finalStatus = null; int n = 0;
                double waited = 0, backoff = 0;
                for (int attempt = 1; attempt <= options.Attempts; attempt++)
                {
                    try { waited += await gate.AcquireAsync(options.Deadline); }
                    catch (AdmissionException ex) { outcome = ex.Message; break; }
                    var sentAt = watch.Elapsed.TotalSeconds; var sentUtc = Utc();
                    int? status = null;
                    var headers = new Dictionary<string, string>();
                    var info = new JsonObject { ["outcome"] = "transport_error", ["usage"] = new JsonObject() };
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(Math.Max(.001, Math.Min(30, options.Deadline - sentAt))));
                    try { var response = await transport.SendAsync(prompt, options.OutputLimit, timeout.Token); status = response.Status; headers = response.Headers; info = response.Info; }
                    catch (LabAuthenticationException) { outcome = "authentication_error"; break; }
                    catch (Exception error) when (error is HttpRequestException or OperationCanceledException or IOException) { /* Unknown outcome: do not replay. */ }
                    n++; finalStatus = status; outcome = info["outcome"]!.ToString();
                    double? delay = status == 429 && attempt < options.Attempts ? Protocol.RetryDelay(headers, attempt) : null;
                    var record = new JsonObject { ["job"] = index, ["attempt"] = attempt, ["status"] = status,
                        ["utc"] = Utc(), ["sent_at_utc"] = sentUtc, ["sent_after_seconds"] = Round(sentAt),
                        ["http_seconds"] = Round(watch.Elapsed.TotalSeconds - sentAt), ["headers"] = JsonSerializer.SerializeToNode(headers),
                        ["proposed_retry_wait_seconds"] = delay };
                    foreach (var (key, value) in info) record[key] = value?.DeepClone();
                    lock (sync)
                    {
                        attempts.Add(record);
                        File.AppendAllText(Path.Combine(output, "attempts.jsonl"), record.ToJsonString() + "\n");
                        Console.WriteLine($"{mode} job={index:D2} attempt={attempt} HTTP={status} outcome={outcome} t={sentAt:F2}s");
                    }
                    if (delay is null) break;
                    if (watch.Elapsed.TotalSeconds + delay.Value >= options.Deadline) { outcome = "retry_wait_exceeds_deadline"; break; }
                    await Task.Delay(TimeSpan.FromSeconds(delay.Value)); backoff += delay.Value;
                }
                var result = new JsonObject { ["job"] = index, ["attempts"] = n, ["final_status"] = finalStatus, ["outcome"] = outcome,
                    ["executor_queue_seconds"] = Round(queued), ["admission_wait_seconds"] = Round(waited),
                    ["retry_wait_seconds"] = Round(backoff), ["e2e_seconds"] = Round(watch.Elapsed.TotalSeconds) };
                lock (sync) jobs.Add(result);
            }
            finally { workers.Release(); }
        }));
        var summary = Evidence.Summary(attempts, jobs, watch.Elapsed.TotalSeconds);
        manifest["ended_at_utc"] = Utc();
        Evidence.Save(Path.Combine(output, "manifest.json"), manifest);
        Evidence.Save(Path.Combine(output, "jobs.json"), new JsonArray(jobs.Select(j => (JsonNode)j).ToArray()));
        Evidence.Save(Path.Combine(output, "summary.json"), summary);
        var lines = new List<string> { $"# Result: {mode}", "", "Scenario: " + options.Scenario, "", "| Metric | Value |", "|---|---|" };
        lines.AddRange(summary.Select(kv => $"| {kv.Key} | {kv.Value} |"));
        lines.Add("\nE2E latency includes queuing, admission, and retries. HTTP 200 does not guarantee completion. Usage is not the internal throttling counter.");
        File.WriteAllLines(Path.Combine(output, "report.md"), lines);
        Console.WriteLine(summary.ToJsonString(Evidence.JsonOptions)); Console.WriteLine("RESULTS=" + output);
        return output;
    }
}
