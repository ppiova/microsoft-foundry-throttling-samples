using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace FoundryLab;

public static class Protocol
{
    public static readonly Dictionary<string, string> Paths = new()
    {
        ["azure_openai"] = "/openai/v1/responses", ["claude"] = "/anthropic/v1/messages",
        ["mai_thinking"] = "/mai/v1/chat/completions", ["mai_image"] = "/mai/v1/images/generations"
    };
    public static readonly Dictionary<string, string> Scopes = new()
    {
        ["azure_openai"] = "https://ai.azure.com/.default", ["claude"] = "https://ai.azure.com/.default",
        ["mai_thinking"] = "https://cognitiveservices.azure.com/.default", ["mai_image"] = "https://cognitiveservices.azure.com/.default"
    };
    public static JsonObject Payload(string provider, string deployment, string prompt, int limit)
    {
        var body = new JsonObject { ["model"] = deployment };
        if (provider == "azure_openai")
        {
            body["input"] = prompt; body["max_output_tokens"] = limit; body["store"] = false;
        }
        else if (provider == "mai_image")
        {
            body["prompt"] = prompt; body["width"] = 1024; body["height"] = 1024;
        }
        else if (provider is "claude" or "mai_thinking")
        {
            body["messages"] = new JsonArray(new JsonObject { ["role"] = "user", ["content"] = prompt });
            body[provider == "claude" ? "max_tokens" : "max_completion_tokens"] = limit;
            if (provider == "mai_thinking") body["stream"] = false;
        }
        else throw new ArgumentException("Unknown provider");
        return body;
    }

    public static JsonObject NumericUsage(JsonObject? usage)
    {
        var result = new JsonObject();
        if (usage is null) return result;
        foreach (var (key, value) in usage)
        {
            if (value is JsonObject child) result[key] = NumericUsage(child);
            else if (value is JsonValue number && double.TryParse(number.ToJsonString(), NumberStyles.Float,
                         CultureInfo.InvariantCulture, out var parsed) && double.IsFinite(parsed)) result[key] = value.DeepClone();
        }
        return result;
    }

    public static JsonObject ResponseInfo(string provider, int status, JsonObject body)
    {
        var info = new JsonObject { ["usage"] = NumericUsage(body["usage"] as JsonObject),
            ["outcome"] = "http_error", ["error_code"] = null, ["evidence_hint"] = null };
        if (status is < 200 or >= 300)
        {
            var error = body["error"] as JsonObject ?? body;
            var code = error["code"]?.ToString() ?? error["type"]?.ToString();
            if (code is not null && Regex.IsMatch(code, @"\A[A-Za-z0-9_.-]{1,80}\z")) info["error_code"] = code;
            var message = error["message"]?.ToString().ToLowerInvariant() ?? "";
            foreach (var (term, hint) in new[] { ("capacity", "capacity_message"), ("high demand", "capacity_message"),
                         ("output token", "output_token_message"), ("input token", "input_token_message"),
                         ("token rate", "token_rate_message"), ("request rate", "request_rate_message") })
                if (message.Contains(term)) { info["evidence_hint"] = hint; break; }
            return info;
        }
        info["outcome"] = provider switch
        {
            "azure_openai" => body["status"]?.ToString() == "completed" ? "completed" : "incomplete_or_unknown",
            "claude" => body["stop_reason"]?.ToString() is "end_turn" or "stop_sequence" ? "completed" : "incomplete_or_other",
            "mai_thinking" => body["choices"] is JsonArray { Count: > 0 } choices && choices[0] is JsonObject choice
                && choice["finish_reason"]?.ToString() == "stop" ? "completed" : "incomplete_or_other",
            _ => body["data"] is JsonArray { Count: > 0 } ? "completed" : "empty_or_unknown"
        };
        return info;
    }

    public static bool AllowedHeader(string name) => name.StartsWith("x-ratelimit-") || name.StartsWith("anthropic-ratelimit-")
        || name is "retry-after" or "retry-after-ms" or "request-id" or "x-request-id" or "apim-request-id";

    public static double RetryDelay(IReadOnlyDictionary<string, string> headers, int attempt, DateTimeOffset? now = null, double? jitter = null)
    {
        foreach (var (name, multiplier) in new[] { ("retry-after-ms", .001), ("retry-after", 1.0) })
            if (headers.TryGetValue(name, out var raw) && double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
                && double.IsFinite(value * multiplier) && value >= 0) return value * multiplier;
        if (headers.TryGetValue("retry-after", out var date) && DateTimeOffset.TryParse(date, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal, out var when)) return Math.Max(0, (when - (now ?? DateTimeOffset.UtcNow)).TotalSeconds);
        return Math.Min(Math.Pow(2, attempt - 1), 8) + (jitter ?? Random.Shared.NextDouble());
    }
}
