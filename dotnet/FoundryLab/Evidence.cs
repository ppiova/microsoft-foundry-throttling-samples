using System.Text.Json;
using System.Text.Json.Nodes;

namespace FoundryLab;

public static class Evidence
{
    public static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    public static double? Percentile(IEnumerable<double> values, double p)
    {
        var sorted = values.Order().ToArray();
        return sorted.Length == 0 ? null : sorted[Math.Max(0, (int)Math.Ceiling(sorted.Length * p) - 1)];
    }
    public static JsonObject Summary(List<JsonObject> attempts, List<JsonObject> jobs, double elapsed)
    {
        int complete = jobs.Count(j => j["outcome"]?.ToString() == "completed");
        int codes = attempts.Count(a => a["status"]?.GetValue<int>() == 429);
        return new JsonObject {
            ["logical_requests"] = jobs.Count, ["http_attempts"] = attempts.Count,
            ["retries"] = attempts.Count(a => a["attempt"]!.GetValue<int>() > 1),
            ["http_successes"] = jobs.Count(j => j["final_status"]?.GetValue<int>() is >= 200 and < 300),
            ["completed_responses"] = complete, ["http_429"] = codes,
            ["http_429_percent"] = attempts.Count == 0 ? 0 : Math.Round(100.0 * codes / attempts.Count, 2),
            ["elapsed_seconds"] = Math.Round(elapsed, 3), ["completed_per_second"] = elapsed == 0 ? 0 : Math.Round(complete / elapsed, 3),
            ["p50_e2e_seconds"] = Percentile(jobs.Select(j => j["e2e_seconds"]!.GetValue<double>()), .5),
            ["p95_e2e_seconds"] = Percentile(jobs.Select(j => j["e2e_seconds"]!.GetValue<double>()), .95),
            ["p95_http_seconds"] = Percentile(attempts.Select(a => a["http_seconds"]!.GetValue<double>()), .95)
        };
    }
    public static void Save(string path, JsonNode node) => File.WriteAllText(path, node.ToJsonString(JsonOptions));
    public static JsonObject Load(string path) => JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? throw new ArgumentException("Invalid evidence object");
    public static JsonArray Signature(JsonObject m)
    {
        JsonNode? window = null;
        if (m["mode"]?.ToString() == "LOCAL_HTTP_MOCK")
        {
            window = m["client_window_seconds"];
            if (window is not JsonValue v || v.GetValueKind() != JsonValueKind.Number
                || !double.TryParse(v.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture, out var n) || !double.IsFinite(n) || n <= 0)
                throw new ArgumentException("Local mock window missing or invalid; rerun scenarios");
        }
        return new JsonArray(m["mode"]?.DeepClone(), m["target"]?.DeepClone(), m["prompt_sha256"]?.DeepClone(),
            m["output_limit"]?.DeepClone(), m["request_count"]?.DeepClone(), m["mock_axis"]?.DeepClone(), window?.DeepClone(), m["schema_version"]?.DeepClone());
    }
    public static void Compare(string[] paths, string output)
    {
        if (paths.Length == 0) throw new ArgumentException("Comparison needs at least one run");
        var runs = paths.Select(p => (M: Load(Path.Combine(p, "manifest.json")), S: Load(Path.Combine(p, "summary.json")))).ToArray();
        var signature = Signature(runs[0].M);
        if (runs.Any(r => !JsonNode.DeepEquals(signature, Signature(r.M)))) throw new ArgumentException("Incompatible workload or mock condition/window");
        var lines = new List<string> { "# Run Comparison", "", "Mode: " + runs[0].M["mode"], "",
            "| Scenario | Complete | HTTP attempts | 429s | E2E p95 s | Complete/s |", "|---|---:|---:|---:|---:|---:|" };
        foreach (var (m, s) in runs) lines.Add($"| {m["scenario"]} | {s["completed_responses"]} | {s["http_attempts"]} | {s["http_429"]} | {s["p95_e2e_seconds"]} | {s["completed_per_second"]} |");
        lines.Add("\nSame logical workload. Controls vary by scenario; review the manifests. This does not establish causality in Azure.");
        File.WriteAllLines(output, lines);
    }
}
