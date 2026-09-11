using Azure.Core;
using FoundryLab;
using System.Text.Json.Nodes;

namespace FoundryLab.Tests;

public class LabTests
{
    [Fact]
    public void SharedProtocolFixtures()
    {
        var cases = Evidence.Load(Path.Combine(AppContext.BaseDirectory, "protocol-cases.json"));
        foreach (var item in cases["responses"]!.AsArray())
        {
            var result = Protocol.ResponseInfo(item!["provider"]!.ToString(), item["status"]!.GetValue<int>(), item["body"]!.AsObject());
            Assert.Equal(item["outcome"]!.ToString(), result["outcome"]!.ToString());
            Assert.DoesNotContain("never export", result.ToJsonString());
        }
        foreach (var item in cases["retries"]!.AsArray())
        {
            var headers = item!["headers"]!.AsObject().ToDictionary(k => k.Key, k => k.Value!.ToString());
            Assert.Equal(item["expected"]!.GetValue<double>(), Protocol.RetryDelay(headers, item["attempt"]!.GetValue<int>(), DateTimeOffset.UnixEpoch, .5));
        }
    }

    [Theory]
    [InlineData("azure_openai", "max_output_tokens")]
    [InlineData("claude", "max_tokens")]
    [InlineData("mai_thinking", "max_completion_tokens")]
    public void OutputContract(string provider, string key)
    {
        var payload = Protocol.Payload(provider, "test", "hello", 32);
        Assert.Equal(32, payload[key]!.GetValue<int>());
        Assert.Equal(1, new[] { "max_tokens", "max_output_tokens", "max_completion_tokens" }.Count(payload.ContainsKey));
    }

    [Theory]
    [InlineData("azure_openai")]
    [InlineData("claude")]
    [InlineData("mai_thinking")]
    [InlineData("mai_image")]
    public async Task Http429Recovery(string provider)
    {
        double now = 0;
        await using var mock = await MockService.StartAsync("rpm", 2, () => now);
        using var transport = new Transport(new JsonObject { ["provider"] = provider, ["deployment"] = "test" }, mock.Origin);
        for (int i = 0; i < 2; i++) Assert.Equal(200, (await transport.SendAsync("hello", 16, default)).Status);
        var response = await transport.SendAsync("hello", 16, default);
        Assert.Equal(429, response.Status);
        now += Protocol.RetryDelay(response.Headers, 1);
        Assert.Equal(200, (await transport.SendAsync("hello", 16, default)).Status);
    }

    [Fact]
    public async Task AdmissionIsAtomicAndBounded()
    {
        var gate = new Gate(0, new(), new(), 3);
        var results = await Task.WhenAll(Enumerable.Range(0, 20).Select(async _ => {
            try { await gate.AcquireAsync(10); return true; } catch (AdmissionException) { return false; }
        }));
        Assert.Equal(3, results.Count(x => x));
        Assert.Throws<ArgumentException>(() => new Gate(1, new() { ["tokens"] = 1 }, new() { ["tokens"] = 2 }, 10));
        var slow = new Gate(1, new(), new(), 10);
        await slow.AcquireAsync(1);
        await Assert.ThrowsAsync<AdmissionException>(() => slow.AcquireAsync(.01));
    }

    private sealed class FakeCredential(Func<DateTimeOffset> clock) : TokenCredential
    {
        public int Calls;
        public bool Fail;
        public override AccessToken GetToken(TokenRequestContext context, CancellationToken cancellation) =>
            Fail ? throw new InvalidOperationException("secret-error") : new AccessToken("secret-" + ++Calls, clock().AddHours(1));
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext context, CancellationToken cancellation) => new(GetToken(context, cancellation));
    }

    [Fact]
    public async Task CredentialRenewalIsCachedAtomicAndSafe()
    {
        var now = DateTimeOffset.UtcNow;
        var fake = new FakeCredential(() => now);
        var tokens = new RenewableToken(fake, "scope", () => now);
        await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => tokens.GetAsync(default)));
        Assert.Equal(1, fake.Calls);
        now = now.AddMinutes(59);
        Assert.Equal("secret-2", await tokens.GetAsync(default));
        fake.Fail = true; now = now.AddHours(1);
        var error = await Assert.ThrowsAsync<LabAuthenticationException>(() => tokens.GetAsync(default));
        Assert.DoesNotContain("secret", error.ToString());
    }

    [Fact]
    public void InvalidRatesAndComparisonsAreRejected()
    {
        Assert.Throws<ArgumentException>(() => new Options { ClientRpm = double.NaN }.Validate());
        Assert.Throws<ArgumentException>(() => new Options { ClientRpm = double.PositiveInfinity }.Validate());
        Assert.Throws<ArgumentException>(() => Evidence.Signature(new JsonObject { ["mode"] = "LOCAL_HTTP_MOCK" }));
        var first = new JsonObject { ["mode"] = "LOCAL_HTTP_MOCK", ["client_window_seconds"] = 2 };
        var second = (JsonObject)first.DeepClone(); second["client_window_seconds"] = 1;
        Assert.False(JsonNode.DeepEquals(Evidence.Signature(first), Evidence.Signature(second)));
    }

    [Theory]
    [InlineData("aoai", "preflight", "rpm")]
    [InlineData("aoai", "baseline", "rpm")]
    [InlineData("aoai", "burst", "rpm")]
    [InlineData("aoai", "retry", "rpm")]
    [InlineData("aoai", "paced", "rpm")]
    [InlineData("aoai", "guarded", "tpm")]
    [InlineData("claude", "guarded", "otpm")]
    [InlineData("mai", "preflight", "rpm")]
    [InlineData("image", "paced", "rpm")]
    [InlineData("aoai", "retry", "capacity")]
    public async Task ScenariosEmitVersionedEvidence(string target, string scenario, string axis)
    {
        var temp = Path.Combine(Path.GetTempPath(), "foundry-tests-" + Guid.NewGuid().ToString("N"));
        try
        {
            var options = new Options { Target = target, Scenario = scenario, MockAxis = axis, MockWindow = .1, Requests = 3,
                ClientRpm = 1200, Out = temp, TokenBudget = axis == "tpm" ? 512 : 0, OutputBudget = axis == "otpm" ? 256 : 0 };
            var path = await Runner.RunAsync(options);
            var manifest = Evidence.Load(Path.Combine(path, "manifest.json"));
            var summary = Evidence.Load(Path.Combine(path, "summary.json"));
            var attempts = File.ReadAllLines(Path.Combine(path, "attempts.jsonl"));
            var jobs = JsonNode.Parse(File.ReadAllText(Path.Combine(path, "jobs.json")))!.AsArray();
            Assert.Equal(1, manifest["schema_version"]!.GetValue<int>());
            Assert.Equal("dotnet", manifest["implementation"]!.ToString());
            Assert.NotNull(manifest["ended_at_utc"]);
            Assert.Equal(attempts.Length, summary["http_attempts"]!.GetValue<int>());
            Assert.Equal(attempts.Length, jobs.Sum(j => j!["attempts"]!.GetValue<int>()));
            Assert.True(attempts.Length <= options.AttemptBudget);
        }
        finally { if (Directory.Exists(temp)) Directory.Delete(temp, true); }
    }
}
