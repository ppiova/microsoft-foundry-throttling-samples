param location string
param accountName string
param projectName string
param principalId string
param assignInferenceRole bool
param allowedIpAddresses array
param modelDeployments array
param claudeProviderData object
param tags object

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: empty(allowedIpAddresses) ? 'Allow' : 'Deny'
      ipRules: [for ip in allowedIpAddresses: { value: ip }]
      virtualNetworkRules: []
    }
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {}
}

// Built-in roles are scoped only to the new account. Cognitive Services User
// is broader than just MaaS invocation; see README before opting into that role.
var hasPartnerModels = length(filter(modelDeployments, model => model.format != 'OpenAI')) > 0
var inferenceRoleId = hasPartnerModels ? 'a97b65f3-24c7-4388-baec-2e87135dc908' : '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
resource inferenceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignInferenceRole && !empty(principalId)) {
  name: guid(account.id, principalId, inferenceRoleId)
  scope: account
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', inferenceRoleId)
  }
}

// The preview API is needed for Anthropic modelProviderData. Sequential account
// deployment operations avoid concurrent update conflicts on the same account.
@batchSize(1)
resource models 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = [for model in modelDeployments: {
  parent: account
  name: model.name
  sku: { name: 'GlobalStandard', capacity: model.capacity }
  properties: union({
    model: {
      format: model.format
      name: model.model
      version: model.version
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }, model.format == 'Anthropic' ? { modelProviderData: claudeProviderData } : {})
  dependsOn: [project, inferenceRole]
}]

output resourceId string = account.id
output accountName string = account.name
output endpoint string = 'https://${account.name}.services.ai.azure.com'
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
