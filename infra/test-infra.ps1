# Offline export and input-validation checks. No Azure service is invoked.
$ErrorActionPreference = 'Stop'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('foundry-infra-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $outputs = @{
        endpoint=@{value='https://sample-foundry.services.ai.azure.com'}
        tenantId=@{value='00000000-0000-0000-0000-000000000000'}
        location=@{value='eastus2'}
        deployments=@{value=@(@{target='aoai';name='lab-openai';model='gpt-5-mini';version='2025-08-07'})}
    }
    $deploymentPath = Join-Path $testRoot 'deployment.json'
    @{properties=@{provisioningState='Succeeded';outputs=$outputs}} | ConvertTo-Json -Depth 20 | Set-Content $deploymentPath
    & "$PSScriptRoot/export-config.ps1" -DeploymentFile $deploymentPath -OutputRoot $testRoot
    $python = Get-Content (Join-Path $testRoot 'python/config.local.json') -Raw | ConvertFrom-Json
    $dotnet = Get-Content (Join-Path $testRoot 'dotnet/config.local.json') -Raw | ConvertFrom-Json
    if ($python.targets.aoai.auth -ne 'entra' -or $dotnet.targets.aoai.deployment -ne 'lab-openai') { throw 'Export mismatch.' }
    $rejected = $false
    try { & "$PSScriptRoot/export-config.ps1" -DeploymentFile $deploymentPath -OutputRoot $testRoot } catch { $rejected = $true }
    if (-not $rejected) { throw 'Existing config was not protected.' }
    $parameters = Get-Content "$PSScriptRoot/parameters.example.json" -Raw | ConvertFrom-Json
    $parameters.parameters.modelDeployments.value[0].capacity = 0
    $parametersPath = Join-Path $testRoot 'invalid.json'
    $parameters | ConvertTo-Json -Depth 20 | Set-Content $parametersPath
    function az { throw 'Offline validation must reject before Azure CLI.' }
    $rejected = $false
    try { & "$PSScriptRoot/deploy.ps1" -SubscriptionId '00000000-0000-0000-0000-000000000000' -ParametersFile $parametersPath -Mode Validate }
    catch { if ($_.Exception.Message -like 'Invalid model configuration*') { $rejected = $true } else { throw } }
    if (-not $rejected) { throw 'Invalid capacity was not rejected.' }
    Write-Output 'Infrastructure offline tests passed.'
}
finally {
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath())) -and (Split-Path $resolved -Leaf).StartsWith('foundry-infra-')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
