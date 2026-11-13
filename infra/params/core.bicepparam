using '../core.bicep'

// The password is read from the environment (GitHub secret SQL_ADMIN_PASSWORD), never stored here.
param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD')

// Uncomment if Azure SQL is blocked in the resource group's region:
// param sqlLocation = 'eastus2'
