// The whole FlightInsight platform, deployed into rg-flightinsight-core:
//   Data Lake (raw/clean files), Azure SQL with two free databases (prod + dev),
//   Key Vault, Data Factory, a Flex Consumption Function App for the Python ETL,
//   and two Cosmos DB accounts (NoSQL with vector search, Gremlin graph).
// Service-to-service permissions (managed identities) are granted at the bottom of this file.

@description('Region for all resources. Defaults to the resource group region.')
param location string = resourceGroup().location

@description('Region for Azure SQL only. Change to eastus2 if the default region blocks SQL provisioning.')
param sqlLocation string = location

@description('Region for both Cosmos DB accounts. Change if the default region reports no capacity.')
param cosmosLocation string = location

@description('Short prefix used in every resource name.')
param prefix string = 'fi'

@description('SQL administrator login.')
param sqlAdminLogin string = 'fiadmin'

@secure()
@description('SQL administrator password. Comes from the GitHub secret SQL_ADMIN_PASSWORD, never committed.')
param sqlAdminPassword string

param tags object = {
  project: 'flightinsight'
  team: 'team3'
  env: 'dev'
  component: 'core'
}

// Stable 6-character suffix so globally unique names don't collide with other teams.
var suffix = take(uniqueString(resourceGroup().id), 6)

var names = {
  lake: 'st${prefix}lake${suffix}'
  funcStorage: 'st${prefix}func${suffix}'
  sqlServer: 'sql-${prefix}-ca-${suffix}'
  keyVault: 'kv-${prefix}-${suffix}'
  dataFactory: 'adf-${prefix}-${suffix}'
  plan: 'plan-${prefix}-${suffix}'
  functionApp: 'func-${prefix}-${suffix}'
  cosmosNoSql: 'cosmos-${prefix}-nosql-${suffix}'
  cosmosGraph: 'cosmos-${prefix}-graph-${suffix}'
}

var sqlDatabases = [
  'flightinsight' // prod: deployed only from main
  'flightinsight-dev' // dev: anyone may experiment
]

var lakeContainers = [
  'raw' // files exactly as downloaded
  'clean' // cleaned, UTC-converted, validated parquet
]

var roleIds = {
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  blobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

// ---------------------------------------------------------------- Data Lake (ADLS Gen2)
resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.lake
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource lakeBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: lake
  name: 'default'
}

resource lakeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for c in lakeContainers: {
    parent: lakeBlob
    name: c
  }
]

// ---------------------------------------------------------------- Azure SQL (free offer)
resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: names.sqlServer
  location: sqlLocation
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

// Lets Azure services (ADF, Functions) reach the server. Laptops still need their own IP rule.
resource sqlAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = [
  for db in sqlDatabases: {
    parent: sqlServer
    name: db
    location: sqlLocation
    tags: tags
    sku: {
      name: 'GP_S_Gen5_2'
      tier: 'GeneralPurpose'
      family: 'Gen5'
      capacity: 2
    }
    properties: {
      useFreeLimit: true // 100,000 vCore-seconds + 32 GB free per database per month
      freeLimitExhaustionBehavior: 'AutoPause' // never bill: pause until next month instead
      autoPauseDelay: 60
      minCapacity: json('0.5')
      maxSizeBytes: 34359738368 // 32 GB
      requestedBackupStorageRedundancy: 'Local'
      zoneRedundant: false
    }
  }
]

// ---------------------------------------------------------------- Key Vault
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.keyVault
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

var sqlHost = sqlServer.properties.fullyQualifiedDomainName

// ODBC connection strings for Python (pyodbc). Connection Timeout covers resume-from-pause.
resource sqlOdbcSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = [
  for db in sqlDatabases: {
    parent: kv
    name: 'sql-odbc-${db}'
    properties: {
      value: 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:${sqlHost},1433;Database=${db};Uid=${sqlAdminLogin};Pwd=${sqlAdminPassword};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=120;'
    }
  }
]

// ---------------------------------------------------------------- Data Factory
// Git integration (repo → adf/ folder) is configured once in ADF Studio, not here,
// so redeploying this template never overwrites it.
resource adf 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: names.dataFactory
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// ---------------------------------------------------------------- Cosmos DB
// Only one free-tier Cosmos account is allowed per subscription:
//   NoSQL (read and written most) uses the free tier; Gremlin is serverless (pay per request).
module cosmosNoSql 'nosql.bicep' = {
  name: 'cosmos-nosql'
  params: {
    location: cosmosLocation
    prefix: prefix
    accountName: names.cosmosNoSql
    enableFreeTier: true
    tags: tags
    keyVaultName: kv.name
    keySecretName: 'cosmos-nosql-key'
    // ADF and Functions read/write documents with their managed identities, no keys needed.
    dataContributorPrincipalIds: [
      adf.identity.principalId
      functionApp.identity.principalId
    ]
  }
}

module cosmosGraph 'graph.bicep' = {
  name: 'cosmos-graph'
  params: {
    location: cosmosLocation
    prefix: prefix
    accountName: names.cosmosGraph
    serverless: true
    tags: tags
    keyVaultName: kv.name
    keySecretName: 'cosmos-graph-key'
  }
}

// ---------------------------------------------------------------- Function App (Flex Consumption)
// Separate standard storage account: the Functions runtime does not use a hierarchical-namespace account.
resource funcStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.funcStorage
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource funcBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: funcStorage
  name: 'default'
}

resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: funcBlob
  name: 'deployments'
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: names.plan
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: names.functionApp
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${funcStorage.properties.primaryEndpoints.blob}${deployContainer.name}'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40 // lowest value Flex Consumption allows
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: funcStorage.name }
        { name: 'DATA_LAKE_URL', value: lake.properties.primaryEndpoints.dfs }
        { name: 'KEY_VAULT_URL', value: kv.properties.vaultUri }
        // Key Vault references: the app reads the secret with its own identity at startup.
        { name: 'SQL_CONNECTION_STRING', value: '@Microsoft.KeyVault(SecretUri=${sqlOdbcSecret[0].properties.secretUri})' }
        { name: 'SQL_CONNECTION_STRING_DEV', value: '@Microsoft.KeyVault(SecretUri=${sqlOdbcSecret[1].properties.secretUri})' }
        // Endpoints are built from names (not module outputs) to avoid a dependency cycle:
        // the NoSQL module needs the Function App's identity first.
        { name: 'COSMOS_NOSQL_ENDPOINT', value: 'https://${names.cosmosNoSql}.documents.azure.com:443/' }
        { name: 'COSMOS_NOSQL_DATABASE', value: 'flightinsight' }
        { name: 'COSMOS_GREMLIN_ENDPOINT', value: 'wss://${names.cosmosGraph}.gremlin.cosmos.azure.com:443/' }
        { name: 'COSMOS_GREMLIN_DATABASE', value: 'flightinsight' }
        { name: 'COSMOS_GREMLIN_GRAPH', value: 'route_network' }
        { name: 'COSMOS_GREMLIN_KEY', value: '@Microsoft.KeyVault(SecretUri=${kv.properties.vaultUri}secrets/cosmos-graph-key/)' }
      ]
    }
  }
  dependsOn: [cosmosGraph]
}

// ---------------------------------------------------------------- Service permissions
resource adfLake 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(lake.id, adf.id, roleIds.blobDataContributor)
  scope: lake
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.blobDataContributor)
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource adfKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, adf.id, roleIds.keyVaultSecretsUser)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.keyVaultSecretsUser)
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource funcLake 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(lake.id, functionApp.id, roleIds.blobDataContributor)
  scope: lake
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.blobDataContributor)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource funcOwnStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(funcStorage.id, functionApp.id, roleIds.blobDataOwner)
  scope: funcStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.blobDataOwner)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource funcKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, functionApp.id, roleIds.keyVaultSecretsUser)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.keyVaultSecretsUser)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------- Outputs (no secrets)
output dataLakeName string = lake.name
output sqlServerName string = sqlServer.name
output sqlServerFqdn string = sqlHost
output keyVaultName string = kv.name
output dataFactoryName string = adf.name
output functionAppName string = functionApp.name
output cosmosNoSqlName string = names.cosmosNoSql
output cosmosGraphName string = names.cosmosGraph
