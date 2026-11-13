using '../core.bicep'

param location = 'westus2'

// The password is read from the environment (GitHub secret SQL_ADMIN_PASSWORD), never stored here.
param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD')

// Uncomment if Azure SQL is blocked in the chosen region:
// param sqlLocation = 'canadacentral'