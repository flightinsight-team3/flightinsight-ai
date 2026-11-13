// Cosmos DB for NoSQL (documents + vector search). Used as a module by core.bicep.
// Free tier: 1000 RU/s and 25 GB free. totalThroughputLimit caps the account so it can never exceed that.

param location string = resourceGroup().location
param prefix string = 'fi'

@description('Cosmos account name (globally unique).')
param accountName string = 'cosmos-${prefix}-nosql-${take(uniqueString(resourceGroup().id), 6)}'

@description('Only one free-tier Cosmos account is allowed per subscription.')
param enableFreeTier bool = true

@description('Managed identity principal IDs that get read/write access to documents (Cosmos data-plane RBAC).')
param dataContributorPrincipalIds array = []

param tags object = {
  project: 'flightinsight'
  team: 'team3'
  env: 'dev'
  component: 'nosql'
}

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: accountName
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

// Cosmos DB Built-in Data Contributor: read/write documents without account keys.
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource dataContributors 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [
  for principalId in dataContributorPrincipalIds: {
    parent: account
    name: guid(account.id, principalId, dataContributorRoleId)
    properties: {
      roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
      principalId: principalId
      scope: account.id
    }
  }
]

output accountName string = account.name
output endpoint string = account.properties.documentEndpoint
