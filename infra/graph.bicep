// Cosmos DB for Apache Gremlin (route network graph). Used as a module by core.bicep.
// serverless = true: pay per request, for when the subscription's free tier is used by another account.
// Note: the Gremlin API supports key authentication only (no managed-identity data access).

param location string = resourceGroup().location
param prefix string = 'fi'

@description('Cosmos account name (globally unique).')
param accountName string = 'cosmos-${prefix}-graph-${take(uniqueString(resourceGroup().id), 6)}'

@description('Serverless capacity mode: no free tier, no provisioned throughput, billed per request.')
param serverless bool = false

@description('Only one free-tier Cosmos account per subscription. Ignored when serverless.')
param enableFreeTier bool = true

@description('Key Vault to store the account key in. Empty = skip.')
param keyVaultName string = ''

@description('Name of the Key Vault secret for the account key.')
param keySecretName string = 'cosmos-graph-key'

param tags object = {
  project: 'flightinsight'
  team: 'team3'
  env: 'dev'
  component: 'graph'
}

var baseProperties = {
  databaseAccountOfferType: 'Standard'
  enableFreeTier: serverless ? false : enableFreeTier
  locations: [
    {
      locationName: location
      failoverPriority: 0
      isZoneRedundant: false
    }
  ]
  consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  capabilities: serverless ? [{ name: 'EnableGremlin' }, { name: 'EnableServerless' }] : [{ name: 'EnableGremlin' }]
}

// Provisioned mode only: cap throughput so the account stays inside the free tier.
var capacityProperties = serverless ? {} : { capacity: { totalThroughputLimit: 1000 } }

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: union(baseProperties, capacityProperties)
}

resource db 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: account
  name: 'flightinsight'
  properties: {
    resource: { id: 'flightinsight' }
    options: serverless ? {} : { throughput: 1000 }
  }
}

// Vertices: airport, airline. Edges: route, operates_at. Edges live in their out-vertex partition.
resource graph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = {
  parent: db
  name: 'route_network'
  properties: {
    resource: {
      id: 'route_network'
      partitionKey: {
        paths: ['/pk']
        kind: 'Hash'
      }
    }
  }
}

// Store the account key in Key Vault (read here, after the account exists).
resource keySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(keyVaultName)) {
  name: '${keyVaultName}/${keySecretName}'
  properties: {
    value: account.listKeys().primaryMasterKey
  }
}

output accountName string = account.name
output gremlinEndpoint string = 'wss://${account.name}.gremlin.cosmos.azure.com:443/'
