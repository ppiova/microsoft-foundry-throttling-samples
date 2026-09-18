targetScope = 'subscription'

@description('Region selected after checking the live model catalog and quota.')
param location string = 'eastus2'

@minLength(2)
@maxLength(20)
param environmentName string = 'throttling-demo'

param resourceGroupName string = 'rg-foundry-${environmentName}'
param principalId string = ''
param assignInferenceRole bool = false

@description('Existing public network access is not required. This new demo account uses Entra authentication on a public endpoint. Optional IP rules restrict client access.')
param allowedIpAddresses array = []

@description('Explicit catalog model versions and SKU capacity units; capacity is not a monetary spending cap. Empty array creates only the account and project.')
param modelDeployments array = [
  {
    target: 'aoai'
    name: 'lab-openai'
    format: 'OpenAI'
    model: 'gpt-5-mini'
    version: '2025-08-07'
    capacity: 10
  }
]

@description('Real organizationName, countryCode and industry, needed only for Anthropic models. Deploying Claude accepts Marketplace terms; the deployment wrapper requires an explicit opt-in.')
param claudeProviderData object = {}

param tags object = {
  project: 'foundry-throttling-lab'
  environment: 'demo'
  managedBy: 'bicep'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module foundry './modules/foundry.bicep' = {
  name: 'foundry-lab'
  scope: resourceGroup
  params: {
    location: location
    accountName: 'fndry-${environmentName}-${uniqueString(subscription().subscriptionId, resourceGroupName)}'
    projectName: 'throttling-lab'
    principalId: principalId
    assignInferenceRole: assignInferenceRole
    allowedIpAddresses: allowedIpAddresses
    modelDeployments: modelDeployments
    claudeProviderData: claudeProviderData
    tags: tags
  }
}

output resourceGroupName string = resourceGroup.name
output resourceId string = foundry.outputs.resourceId
output accountName string = foundry.outputs.accountName
output projectEndpoint string = foundry.outputs.projectEndpoint
output endpoint string = foundry.outputs.endpoint
output deployments array = modelDeployments
output location string = location
output tenantId string = tenant().tenantId
