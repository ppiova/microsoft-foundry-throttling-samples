param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$AccountName,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]+$')][string]$Location,
    [string]$OutDir = './azure-evidence',
    [string]$StartTimeUtc,
    [string]$EndTimeUtc,
    [string[]]$MetricNames = @(),
    [string]$Aggregation = 'Total',
    [string]$Interval = '1m',
    [string]$MetricFilter
)
$ErrorActionPreference = 'Stop'
if ($StartTimeUtc -or $EndTimeUtc -or $MetricNames.Count) {
    if (-not $StartTimeUtc -or -not $EndTimeUtc -or -not $MetricNames.Count) {
        throw 'Time-series collection requires StartTimeUtc, EndTimeUtc, and MetricNames together.'
    }
    if ($StartTimeUtc -notmatch '(Z|\+00:00)$' -or $EndTimeUtc -notmatch '(Z|\+00:00)$') {
        throw 'Use explicit UTC offsets in both timestamps.'
    }
    $startUtc = [DateTimeOffset]::Parse($StartTimeUtc)
    $endUtc = [DateTimeOffset]::Parse($EndTimeUtc)
    if ($startUtc.Offset -ne [TimeSpan]::Zero -or $endUtc.Offset -ne [TimeSpan]::Zero -or $startUtc -ge $endUtc) {
        throw 'Use an increasing UTC interval with explicit Z or +00:00 offsets.'
    }
}
$evidenceDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null

function Save-AzJson {
    param([string[]]$AzArguments, [string]$FileName)
    $result = & az @AzArguments
    if ($LASTEXITCODE -ne 0) { throw "Azure query failed: $FileName" }
    $result | Set-Content -LiteralPath (Join-Path $evidenceDir $FileName) -Encoding utf8
}

# Read-only. Does not retrieve keys or change the active subscription, quota, or deployments.
Save-AzJson -FileName 'deployments.json' -AzArguments @(
    'cognitiveservices','account','deployment','list','--subscription',$SubscriptionId,
    '--resource-group',$ResourceGroup,'--name',$AccountName,
    '--query','[].{name:name,sku:sku,model:properties.model,state:properties.provisioningState}',
    '--output','json'
)
$usageUri = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.CognitiveServices/locations/$Location/usages?api-version=2024-10-01"
Save-AzJson -FileName 'quota-allocations.json' -AzArguments @('rest','--method','get','--url',$usageUri,'--output','json')
$resourceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName"
Save-AzJson -FileName 'metric-definitions.json' -AzArguments @(
    'monitor','metrics','list-definitions','--resource',$resourceId,'--subscription',$SubscriptionId,'--output','json'
)
if ($MetricNames.Count) {
    $metricArguments = @('monitor','metrics','list','--resource',$resourceId,'--subscription',$SubscriptionId,
        '--start-time',$startUtc.ToString('o'),'--end-time',$endUtc.ToString('o'),
        '--interval',$Interval,'--aggregation',$Aggregation,'--output','json','--metrics') + $MetricNames
    if ($MetricFilter) { $metricArguments += @('--filter',$MetricFilter) }
    Save-AzJson -FileName 'metric-values.json' -AzArguments $metricArguments
}
@{
    collectedAtUtc = [DateTime]::UtcNow.ToString('o')
    startTimeUtc = $StartTimeUtc
    endTimeUtc = $EndTimeUtc
    metrics = $MetricNames
    note = 'Usages reports management-plane allocations/quota, not inference tokens consumed per minute. Verify scope for each model.'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceDir 'collection.json') -Encoding utf8
Write-Output "Read-only evidence: $evidenceDir"
