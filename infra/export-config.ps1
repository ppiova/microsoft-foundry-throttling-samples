param(
    [string]$DeploymentFile = "$PSScriptRoot/out/deploy.local.json",
    [switch]$Force,
    [string]$OutputRoot = (Split-Path $PSScriptRoot -Parent)
)
$ErrorActionPreference = 'Stop'
$deployment = Get-Content -LiteralPath $DeploymentFile -Raw | ConvertFrom-Json -Depth 100
if ($deployment.properties.provisioningState -ne 'Succeeded') { throw 'Export requires a successful deployment result.' }
$outputs = $deployment.properties.outputs
$endpoint = $outputs.endpoint.value
if ($endpoint -notmatch '^https://[a-z0-9-]+\.services\.ai\.azure\.com$') { throw 'Unexpected resource endpoint.' }
$tenantId = $outputs.tenantId.value
if ($tenantId -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Unexpected tenant ID in outputs.' }
$targets = [ordered]@{}
$providers = @{ aoai='azure_openai'; claude='claude'; mai='mai_thinking'; image='mai_image' }
$envNames = @{ aoai='AOAI_ENDPOINT'; claude='CLAUDE_ENDPOINT'; mai='MAI_ENDPOINT'; image='MAI_ENDPOINT' }
foreach ($model in $outputs.deployments.value) {
    if (-not $providers.ContainsKey($model.target)) { throw 'Unexpected target in deployment outputs.' }
    $targets[$model.target] = [ordered]@{
        provider=$providers[$model.target]; deployment=$model.name; endpoint_env=$envNames[$model.target]
        auth='entra'; credential_type='azure_cli'; model=$model.model; version=$model.version
        lifecycle='VERIFY'; hosting='VERIFY'; region=$outputs.location.value; deployment_type='GlobalStandard'
        quota_scope='VERIFY actual pool scope'; verified_limits=@{}
    }
}
$repoRoot = [IO.Path]::GetFullPath($OutputRoot)
$paths = @((Join-Path $repoRoot 'python/config.local.json'), (Join-Path $repoRoot 'dotnet/config.local.json'))
$envPath = Join-Path $repoRoot 'infra/out/environment.local.ps1'
foreach ($path in ($paths + $envPath)) { if ((Test-Path -LiteralPath $path) -and -not $Force) { throw 'Local configuration already exists. Use -Force only to replace it intentionally.' } }
$json = @{ targets=$targets } | ConvertTo-Json -Depth 20
foreach ($path in ($paths + $envPath)) { New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force | Out-Null }
foreach ($path in $paths) { Set-Content -LiteralPath $path -Value $json -Encoding utf8 }
$lines = @('# Non-secret endpoint configuration generated from deployment outputs.')
$lines += "Set-Item -Path Env:AZURE_TENANT_ID -Value '$tenantId'"
foreach ($envName in @($envNames.Values | Select-Object -Unique)) { $lines += "Set-Item -Path Env:$envName -Value '$endpoint'" }
Set-Content -LiteralPath $envPath -Value $lines -Encoding utf8
Write-Output 'Created ignored local configs for both runtimes. Dot-source infra/out/environment.local.ps1 in the shell that runs the lab.'
