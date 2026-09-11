using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace FoundryLab;

public sealed class MockService : IAsyncDisposable
{
    private readonly WebApplication app;
    public string Origin => app.Urls.Single();
    private MockService(WebApplication app) => this.app = app;

    public static async Task<MockService> StartAsync(string axis, double window, Func<double>? clock = null)
    {
        var watch = Stopwatch.StartNew();
        clock ??= () => watch.Elapsed.TotalSeconds;
        var builder = WebApplication.CreateSlimBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        var app = builder.Build();
        var stateLock = new object();
        double start = clock();
        int used = 0;
        var limits = new Dictionary<string, int> { ["rpm"] = 2, ["tpm"] = 512, ["itpm"] = 256, ["otpm"] = 256 };
        foreach (var (provider, path) in Protocol.Paths)
        {
            app.MapPost(path, async context =>
            {
                JsonObject? body;
                try { body = await JsonNode.ParseAsync(context.Request.Body) as JsonObject; }
                catch (System.Text.Json.JsonException) { context.Response.StatusCode = 400; return; }
                var text = body?["input"]?.ToString() ?? body?["prompt"]?.ToString();
                if (text is null && body?["messages"] is JsonArray messages)
                    text = string.Join(" ", messages.OfType<JsonObject>().Select(m => m["content"]?.ToString() ?? ""));
                var parameter = provider switch { "azure_openai" => "max_output_tokens", "claude" => "max_tokens", _ => "max_completion_tokens" };
                int output = 0;
                if (body?["model"] is not JsonValue || string.IsNullOrEmpty(text)
                    || (provider != "mai_image" && (body?[parameter] is not JsonValue v || !v.TryGetValue(out output) || output <= 0)))
                { context.Response.StatusCode = 400; return; }
                // ASCII demo prompts; use Unicode scalar count for shared fixtures.
                int tokens = Math.Max(1, text.EnumerateRunes().Count() / 4);
                int cost = axis switch { "rpm" => 1, "tpm" => tokens + output, "itpm" => tokens, "otpm" => output, _ => 1 };
                bool rejected; int remaining, waitMs;
                lock (stateLock)
                {
                    var now = clock();
                    if (now - start >= window) { start = now; used = 0; }
                    rejected = axis == "capacity" || used + cost > limits.GetValueOrDefault(axis);
                    if (!rejected) used += cost;
                    remaining = Math.Max(0, limits.GetValueOrDefault(axis) - used);
                    waitMs = Math.Max(1, (int)((window - (now - start)) * 1000) + 5);
                }
                context.Response.Headers["x-request-id"] = "LOCAL-MOCK";
                if (axis == "rpm") context.Response.Headers["x-ratelimit-remaining-requests"] = remaining.ToString();
                if (axis == "tpm") context.Response.Headers["x-ratelimit-remaining-tokens"] = remaining.ToString();
                JsonObject result;
                if (rejected)
                {
                    context.Response.StatusCode = 429;
                    context.Response.Headers["retry-after-ms"] = waitMs.ToString();
                    result = new JsonObject { ["error"] = new JsonObject { ["code"] = "local_mock_" + axis,
                        ["message"] = axis == "capacity" ? "System capacity high demand" : axis + " rate limit exceeded" } };
                }
                else
                {
                    var usage = new JsonObject { ["input_tokens"] = tokens, ["output_tokens"] = Math.Min(output, 12) };
                    result = provider switch
                    {
                        "claude" => new JsonObject { ["stop_reason"] = "end_turn", ["content"] = new JsonArray(), ["usage"] = usage },
                        "mai_thinking" => new JsonObject { ["choices"] = new JsonArray(new JsonObject { ["finish_reason"] = "stop" }),
                            ["usage"] = new JsonObject { ["prompt_tokens"] = tokens, ["completion_tokens"] = Math.Min(output, 12) } },
                        "mai_image" => new JsonObject { ["data"] = new JsonArray(new JsonObject { ["b64_json"] = "LOCAL_PLACEHOLDER_NOT_AN_IMAGE" }) },
                        _ => new JsonObject { ["status"] = "completed", ["output"] = new JsonArray(), ["usage"] = usage }
                    };
                }
                context.Response.ContentType = "application/json";
                await context.Response.WriteAsync(result.ToJsonString());
            });
        }
        await app.StartAsync();
        return new MockService(app);
    }
    public async ValueTask DisposeAsync() { await app.StopAsync(); await app.DisposeAsync(); }
}
