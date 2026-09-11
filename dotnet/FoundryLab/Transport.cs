using Azure.Core;
using Azure.Identity;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace FoundryLab;

public sealed class LabAuthenticationException : Exception { }

public sealed class RenewableToken(TokenCredential credential, string scope, Func<DateTimeOffset>? clock = null)
{
    private readonly SemaphoreSlim gate = new(1);
    private AccessToken cached;
    public async Task<string> GetAsync(CancellationToken cancellation)
    {
        await gate.WaitAsync(cancellation);
        try
        {
            if (cached.ExpiresOn <= (clock?.Invoke() ?? DateTimeOffset.UtcNow).AddMinutes(2))
                cached = await credential.GetTokenAsync(new TokenRequestContext([scope]), cancellation);
            return cached.Token;
        }
        catch (OperationCanceledException) { throw new LabAuthenticationException(); }
        catch (Exception) { throw new LabAuthenticationException(); }
        finally { gate.Release(); }
    }
}

public sealed class Transport : IDisposable
{
    private readonly HttpClient client;
    private readonly string provider, deployment;
    private readonly Uri endpoint;
    private readonly string? key, keyHeader;
    private readonly RenewableToken? token;
    public Transport(JsonObject target, string? mockOrigin = null)
    {
        provider = target["provider"]!.ToString(); deployment = target["deployment"]!.ToString();
        var origin = mockOrigin ?? Environment.GetEnvironmentVariable(target["endpoint_env"]!.ToString())
            ?? throw new ArgumentException("Missing endpoint environment variable");
        if (!Uri.TryCreate(origin, UriKind.Absolute, out var uri) || uri.UserInfo.Length > 0 || uri.Query.Length > 0
            || uri.Fragment.Length > 0 || uri.AbsolutePath != "/" || (mockOrigin is null && uri.Scheme != "https"))
            throw new ArgumentException("Endpoint must be an HTTPS resource origin without a path");
        endpoint = new Uri(origin.TrimEnd('/') + Protocol.Paths[provider]);
        client = new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = false, PooledConnectionLifetime = TimeSpan.FromMinutes(2) })
            { Timeout = Timeout.InfiniteTimeSpan };
        if (mockOrigin is not null) return;
        var auth = target["auth"]?.ToString() ?? "entra";
        if (auth == "entra")
        {
            var mode = target["credential_type"]?.ToString() ?? "azure_cli";
            TokenCredential credential = mode switch
            {
                "azure_cli" => new AzureCliCredential(new AzureCliCredentialOptions {
                    TenantId = Environment.GetEnvironmentVariable(target["tenant_env"]?.ToString() ?? "AZURE_TENANT_ID"),
                    ProcessTimeout = TimeSpan.FromSeconds(10) }),
                "default" => new DefaultAzureCredential(new DefaultAzureCredentialOptions { ExcludeInteractiveBrowserCredential = true }),
                _ => throw new ArgumentException("credential_type must be azure_cli or default")
            };
            token = new RenewableToken(credential, Protocol.Scopes[provider]);
        }
        else
        {
            key = Environment.GetEnvironmentVariable(target["credential_env"]?.ToString() ?? "");
            if (string.IsNullOrEmpty(key)) throw new ArgumentException("Missing credential environment variable");
            keyHeader = auth switch { "api_key" => provider == "claude" ? "x-api-key" : "api-key",
                "bearer" => "Authorization", _ => throw new ArgumentException("Unknown auth mode") };
            if (auth == "bearer") key = "Bearer " + key;
        }
    }

    public async Task<(int Status, Dictionary<string, string> Headers, JsonObject Info)> SendAsync(string prompt, int limit, CancellationToken cancellation)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, endpoint);
        request.Content = new StringContent(Protocol.Payload(provider, deployment, prompt, limit).ToJsonString(), Encoding.UTF8, "application/json");
        if (provider == "claude") request.Headers.Add("anthropic-version", "2023-06-01");
        if (token is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", await token.GetAsync(cancellation));
        if (keyHeader is not null) request.Headers.Add(keyHeader, key);
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        var headers = response.Headers.Concat(response.Content.Headers).Where(h => Protocol.AllowedHeader(h.Key.ToLowerInvariant()))
            .ToDictionary(h => h.Key.ToLowerInvariant(), h => string.Join(",", h.Value));
        using var stream = await response.Content.ReadAsStreamAsync(cancellation);
        using var buffer = new MemoryStream();
        byte[] chunk = new byte[8192];
        int read;
        while ((read = await stream.ReadAsync(chunk, cancellation)) > 0)
        {
            if (buffer.Length + read > 32 * 1024 * 1024)
                return ((int)response.StatusCode, headers, new JsonObject { ["outcome"] = "body_limit", ["usage"] = new JsonObject() });
            buffer.Write(chunk, 0, read);
        }
        JsonObject body;
        try { body = JsonNode.Parse(buffer.ToArray()) as JsonObject ?? new(); }
        catch (JsonException) { body = new(); }
        return ((int)response.StatusCode, headers, Protocol.ResponseInfo(provider, (int)response.StatusCode, body));
    }
    public void Dispose() => client.Dispose();
}
