// Cosmos DB for NoSQL (documents + vector search), deployed into rg-flightinsight-nosql.
// Free tier: 1000 RU/s and 25 GB free. totalThroughputLimit caps the account so it can never exceed that.

param location string = resourceGroup().location
param prefix string = 'fi'

@description('Only one free-tier Cosmos account is allowed per subscription.')
param enableFreeTier bool = true

param tags object = {
  project: 'flightinsight'
  team: 'team3'
  env: 'dev'
  component: 'nosql'
}

var suffix = take(uniqueString(resourceGroup().id), 6)

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'cosmos-${prefix}-nosql-${suffix}'
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
      { name: 'EnableNoSQLVectorSearch' }
    ]
    capacity: { totalThroughputLimit: 1000 }
  }
}

// Shared throughput: both containers share the free 1000 RU/s.
resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: account
  name: 'flightinsight'
  properties: {
    resource: { id: 'flightinsight' }
    options: { throughput: 1000 }
  }
}

// One document per route and month. Partition key cannot be changed after creation.
resource routeSummaries 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: db
  name: 'route_summaries'
  properties: {
    resource: {
      id: 'route_summaries'
      partitionKey: {
        paths: ['/origin']
        kind: 'Hash'
      }
    }
  }
}

// One document per ASRS safety report with a 768-d nomic-embed-text vector.
resource asrsReports 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: db
  name: 'asrs_reports'
  properties: {
    resource: {
      id: 'asrs_reports'
      partitionKey: {
        paths: ['/month_key']
        kind: 'Hash'
      }
      vectorEmbeddingPolicy: {
        vectorEmbeddings: [
          {
            path: '/narrative_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 768
          }
        ]
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/narrative_vector/*' }
          { path: '/"_etag"/?' }
        ]
        vectorIndexes: [
          {
            path: '/narrative_vector'
            type: 'quantizedFlat'
          }
        ]
      }
    }
  }
}

output accountName string = account.name
output endpoint string = account.properties.documentEndpoint
