// Cosmos DB for Apache Gremlin (route network graph), deployed into rg-flightinsight-graph.
// Free tier: 1000 RU/s and 25 GB free; totalThroughputLimit keeps the account inside it.

param location string = resourceGroup().location
param prefix string = 'fi'

@description('Only one free-tier Cosmos account is allowed per subscription.')
param enableFreeTier bool = true

param tags object = {
  project: 'flightinsight'
  team: 'team3'
  env: 'dev'
  component: 'graph'
}

var suffix = take(uniqueString(resourceGroup().id), 6)

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'cosmos-${prefix}-graph-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: enableFreeTier
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    capabilities: [
      { name: 'EnableGremlin' }
    ]
    capacity: { totalThroughputLimit: 1000 }
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: account
  name: 'flightinsight'
  properties: {
    resource: { id: 'flightinsight' }
    options: { throughput: 1000 }
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

output accountName string = account.name
output gremlinEndpoint string = 'wss://${account.name}.gremlin.cosmos.azure.com:443/'
