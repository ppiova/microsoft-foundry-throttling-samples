# Offline command-contract test; no Azure CLI process or Azure resource is used.
$ErrorActionPreference = 'Stop'
$taskTestDir = Join-Path ([IO.Path]::GetTempPath()) ('foundry-collector-' + [Guid]::NewGuid().ToString('N'))
$global:foundryCollectorTestCalls = [Collections.Generic.List[object]]::new()
function az {
    $global:foundryCollectorTestCalls.Add(@($args))
    $global:LASTEXITCODE = 0
    '{"value": []}'
}
try {
    $collector = Join-Path $PSScriptRoot '../inspect_azure.ps1'
    & $collector -SubscriptionId '00000000-0000-0000-0000-000000000000' -ResourceGroup 'test' -AccountName 'test' -Location 'eastus' -OutDir $taskTestDir -StartTimeUtc '2026-09-10T12:00:00Z' -EndTimeUtc '2026-09-10T12:10:00Z' -MetricNames 'Requests','Latency' -Aggregation Average -MetricFilter "Deployment eq 'test'"
    if ($global:foundryCollectorTestCalls.Count -ne 4) { throw 'Expected inventory, usage, definitions, and values calls' }
    $lastCall = $global:foundryCollectorTestCalls[3]
    if (($lastCall -join ' ') -notmatch 'monitor metrics list ' -or $lastCall -notcontains 'Requests' -or $lastCall -notcontains 'Latency' -or $lastCall -notcontains '1m') { throw 'Metric arguments were not preserved' }
    if (-not (Test-Path (Join-Path $taskTestDir 'metric-values.json'))) { throw 'Metric values not saved' }
    $rejected = $false
    try { & $collector -SubscriptionId '00000000-0000-0000-0000-000000000000' -ResourceGroup 'test' -AccountName 'test' -Location 'eastus' -OutDir $taskTestDir -StartTimeUtc '2026-09-10T12:00:00Z' }
    catch { $rejected = $true }
    if (-not $rejected -or $global:foundryCollectorTestCalls.Count -ne 4) { throw 'Incomplete interval was not rejected before CLI invocation' }
    Write-Output 'Collector command-contract tests passed without Azure access.'
}
finally {
    Remove-Variable -Name foundryCollectorTestCalls -Scope Global
    $resolvedTaskDir = [IO.Path]::GetFullPath($taskTestDir)
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTaskDir.StartsWith($resolvedTemp) -and (Split-Path $resolvedTaskDir -Leaf).StartsWith('foundry-collector-') -and (Test-Path -LiteralPath $resolvedTaskDir)) {
        Remove-Item -LiteralPath $resolvedTaskDir -Recurse -Force
    }
}
