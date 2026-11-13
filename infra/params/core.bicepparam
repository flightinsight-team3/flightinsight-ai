using '../core.bicep'

param location = 'westus2'

// Azure SQL is restricted in westus2 for this subscription, so it lives in Canada Central.
param sqlLocation = 'canadacentral'

// Both Cosmos DB accounts. Change to 'canadacentral' if westus2 reports no capacity.
param cosmosLocation = 'westus2'

// The password is read from the environment (GitHub secret SQL_ADMIN_PASSWORD), never stored here.
param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD')
