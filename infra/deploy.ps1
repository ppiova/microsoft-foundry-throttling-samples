param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$SubscriptionId,
    [string]$ParametersFile = "$PSScriptRoot/parameters.example.json",
    [ValidateSet('Validate','WhatIf','Deploy')][string]$Mode = 'WhatIf',
    [ValidatePattern('^[a-zA-Z0-9-]{1,64}$')][string]$DeploymentName = 'foundry-throttling-lab',
    [switch]$AcceptClaudeMarketplaceTerms
)
$ErrorActionPreference = 'Stop'
function Invoke-AzJson([string[]]$Arguments) {
    $result = & az @Arguments --only-show-errors -o json
    if ($LASTEXITCODE -ne 0) { throw 'Azure CLI command failed; review the preceding Azure error.' }
    return ($result | ConvertFrom-Json -Depth 100)
}

$parameters = Get-Content -LiteralPath $ParametersFile -Raw | ConvertFrom-Json -Depth 100
$location = $parameters.parameters.location.value
$models = @($parameters.parameters.modelDeployments.value)
if (-not $location -or $null -eq $parameters.parameters.modelDeployments) { throw 'Specify location and modelDeployments explicitly.' }
$targetFormats = @{ aoai='OpenAI'; claude='Anthropic'; mai='Microsoft'; image='Microsoft' }
$targets = @{}; $names = @{}
foreach ($model in $models) {
    if (-not $targetFormats.ContainsKey($model.target) -or $targetFormats[$model.target] -ne $model.format -or
        $model.name -notmatch '^[a-zA-Z0-9-]{1,64}$' -or -not $model.model -or -not $model.version -or
        ($model.capacity -isnot [long] -and $model.capacity -isnot [int]) -or
        $model.capacity -lt 1 -or $model.capacity -gt 1000) { throw 'Invalid model configuration. Use explicit target, format, name, model, version, and capacity 1-1000.' }
    if ($targets.ContainsKey($model.target) -or $names.ContainsKey($model.name)) { throw 'Targets and deployment names must be unique.' }
    $targets[$model.target] = $true; $names[$model.name] = $true
}
if ($targets.ContainsKey('claude')) {
    $attestation = $parameters.parameters.claudeProviderData.value
    if (-not $attestation.organizationName -or $attestation.countryCode -notmatch '^[A-Z]{2}$' -or
        $attestation.industry -notin @('technology','finance','healthcare','education','retail','manufacturing','government','media','other')) {
        throw 'Claude requires real organizationName, countryCode, and industry values.'
    }
    if ($Mode -eq 'Deploy' -and -not $AcceptClaudeMarketplaceTerms) { throw 'Claude deployment accepts Marketplace terms. Supply -AcceptClaudeMarketplaceTerms only when authorized.' }
}

$account = Invoke-AzJson @('account','show','--subscription',$SubscriptionId)
if ($account.state -ne 'Enabled') { throw 'The subscription is not enabled.' }
$catalog = @(Invoke-AzJson @('cognitiveservices','model','list','--location',$location,'--subscription',$SubscriptionId))
$usage = @(Invoke-AzJson @('cognitiveservices','usage','list','--location',$location,'--subscription',$SubscriptionId))
foreach ($model in $models) {
    $candidate = @($catalog | Where-Object { $_.model.name -eq $model.model -and $_.model.version -eq $model.version -and $_.model.format -eq $model.format })
    if (-not $candidate.Count) { throw "Model/version unavailable in catalog: $($model.target)." }
    $sku = @($candidate[0].model.skus | Where-Object name -eq 'GlobalStandard') | Select-Object -First 1
    if (-not $sku) { throw "GlobalStandard is not listed for $($model.target)." }
    $quota = @($usage | Where-Object { $_.name.value -eq $sku.usageName }) | Select-Object -First 1
    if ($quota) {
        Write-Output "$($model.target): quota used=$($quota.currentValue), limit=$($quota.limit), requested capacity=$($model.capacity). Existing lab allocations may already be included in used."
        # Azure validation is authoritative for updates, where requested capacity is
        # not necessarily additional capacity. Do not delete or rebalance other deployments.
        if ($quota.currentValue -ge $quota.limit) { Write-Warning "No unallocated quota reported for $($model.target); deployment validation may reject a new allocation." }
    } else { Write-Warning "No matching quota counter found for $($model.target); Azure validation must resolve access." }
}

$outputDir = Join-Path $PSScriptRoot 'out'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$operation = switch ($Mode) { 'Validate' { 'validate' }; 'WhatIf' { 'what-if' }; 'Deploy' { 'create' } }
$arguments = @('deployment','sub',$operation,'--subscription',$SubscriptionId,'--location',$location,
    '--name',$DeploymentName,'--template-file',(Join-Path $PSScriptRoot 'main.bicep'),'--parameters',('@' + (Resolve-Path -LiteralPath $ParametersFile).Path))
if ($Mode -eq 'WhatIf') { $arguments += '--no-pretty-print' }
$result = Invoke-AzJson $arguments
$result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $outputDir "$($Mode.ToLowerInvariant()).local.json") -Encoding utf8
if ($Mode -eq 'Deploy') {
    if ($result.properties.provisioningState -ne 'Succeeded') { throw 'Deployment did not report Succeeded.' }
    Write-Output 'Deployment succeeded. Generate runtime config with export-config.ps1.'
} else { Write-Output "$Mode completed. Review infra/out/$($Mode.ToLowerInvariant()).local.json." }
