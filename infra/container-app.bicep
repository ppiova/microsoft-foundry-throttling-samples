targetScope = 'resourceGroup'
param location string = resourceGroup().location
param prefix string = 'foundrylab'
param appName string = 'foundry-throttling-lab'
param image string
param clientId string
@minLength(1)
@description('Entra user object IDs. Removing an ID denies existing sessions at the application boundary after the new revision activates.')
param allowedUserIds array
@minValue(0)
@maxValue(1)
param minReplicas int = 0

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = { name: '${prefix}-environment' }
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: '${prefix}-identity' }
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: '${prefix}${uniqueString(resourceGroup().id)}' }
var origin = 'https://${appName}.${environment.properties.defaultDomain}'

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8080, transport: 'http', allowInsecure: false }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: [{ name: 'override-use-mi-fic-assertion-client-id', value: identity.properties.clientId }]
    }
    template: {
      containers: [{
        name: 'lab'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'LAB_PUBLIC_ORIGIN', value: origin }
          { name: 'LAB_ALLOWED_USERS', value: join(allowedUserIds, ',') }
        ]
        volumeMounts: [{ volumeName: 'evidence', mountPath: '/data' }]
        probes: [
          { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, initialDelaySeconds: 10, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/healthz', port: 8080 }, initialDelaySeconds: 5, periodSeconds: 10 }
        ]
      }]
      volumes: [{ name: 'evidence', storageType: 'AzureFile', storageName: 'evidence', mountOptions: 'uid=1654,gid=1654,dir_mode=0770,file_mode=0660' }]
      scale: { minReplicas: minReplicas, maxReplicas: 1 }
    }
  }
}
resource auth 'Microsoft.App/containerApps/authConfigs@2025-01-01' = {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'RedirectToLoginPage', redirectToProvider: 'azureactivedirectory' }
    httpSettings: { requireHttps: true }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: clientId
          openIdIssuer: '${az.environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
          clientSecretSettingName: 'override-use-mi-fic-assertion-client-id'
        }
        validation: { defaultAuthorizationPolicy: { allowedPrincipals: { identities: allowedUserIds } } }
      }
    }
    login: { cookieExpiration: { convention: 'FixedTime', timeToExpiration: '01:00:00' } }
  }
}
output url string = origin
