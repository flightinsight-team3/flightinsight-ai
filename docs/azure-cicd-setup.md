# Connecting GitHub Actions to Azure (one-time setup)

GitHub Actions logs in to Azure with **OIDC**: no password or key is stored in GitHub. Each subscription
trusts one GitHub *environment* of this repository through a **user-assigned managed identity**.

| GitHub environment | Subscription owner | Resource group | Managed identity |
|---|---|---|---|
| `core` | (core owner) | `rg-flightinsight-core` | `id-github-core` |
| `nosql` | (nosql owner) | `rg-flightinsight-nosql` | `id-github-nosql` |
| `graph` | (graph owner) | `rg-flightinsight-graph` | `id-github-graph` |

All three subscriptions must use the same region (East US).

## Part A — in Azure (each subscription owner, for their own row)

1. **Resource group.** Create it if it doesn't exist (tags: `project=flightinsight`, `team=team3`, `env=dev`, `component=<core|nosql|graph>`).
2. **Managed identity.** Portal → *Managed Identities* → Create → your subscription, your resource group,
   name `id-github-<environment>`, same region.
3. **Permissions.** Resource group → *Access control (IAM)* → Add role assignment:
   - **Contributor** → Members: *Managed identity* → `id-github-<environment>`.
   - **core only:** also **Role Based Access Control Administrator** → same identity
     (`core.bicep` grants ADF and Functions access to the Data Lake and Key Vault).
4. **Federated credential.** Open the managed identity → *Federated credentials* → Add credential:
   - Scenario: **GitHub Actions deploying Azure resources**
   - Organization: the GitHub organization name · Repository: `flightinsight-ai`
   - Entity: **Environment** · Environment: `core` / `nosql` / `graph` (must match exactly)
   - Name: `github-<environment>`
5. **Write down** from the identity's *Overview*: **Client ID**; and your **Tenant ID** and **Subscription ID**.

## Part B — in GitHub (repository admin)

Repository → *Settings* → *Environments* → New environment, for each of `core`, `nosql`, `graph`.
In each environment add **variables** (not secrets — these IDs are not sensitive):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | Client ID of that environment's managed identity |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID of that owner |
| `AZURE_RESOURCE_GROUP` | `rg-flightinsight-core` / `-nosql` / `-graph` |

In `core` also add the **secret** `SQL_ADMIN_PASSWORD` (a strong password; nobody needs to remember it,
it is also stored in Key Vault).

## Part C — first deployment

1. Actions → **Deploy infrastructure** → `core`, *apply* unchecked → check the what-if output.
2. Run again with *apply* checked. The job prints the outputs: `sqlServerName`, `functionAppName`, ….
3. In the `core` environment add:
   - variables `SQL_SERVER_NAME`, `FUNCTION_APP_NAME` (from the outputs)
   - secrets `SQL_CONNECTION_STRING_PROD` and `SQL_CONNECTION_STRING_DEV`:
     `Server=tcp:<sqlServerFqdn>,1433;Database=flightinsight;User ID=fiadmin;Password=<password>;Encrypt=True;Connection Timeout=120;`
     (use `Database=flightinsight-dev` for the dev one)
4. Repeat steps 1–2 for `nosql` and `graph` (their owners can run them).
5. Actions → **Deploy SQL schema** → `dev`, then merge anything under `sql/` (or run with `prod`).
6. Actions → **Deploy Functions** → Run workflow.
7. Store the Cosmos endpoints and keys in the core Key Vault (`cosmos-nosql-key`, `cosmos-graph-key`, …)
   so ADF and Functions can use them. The core owner grants themselves **Key Vault Secrets Officer** on the vault to do this.

## Troubleshooting

| Error | Cause / fix |
|---|---|
| `AADSTS70021: No matching federated identity record found` | Environment name, org or repo in the federated credential doesn't match exactly |
| `AuthorizationFailed ... roleAssignments/write` | core identity is missing *Role Based Access Control Administrator* |
| SQL: `Provisioning is restricted in this region` | Uncomment `sqlLocation = 'eastus2'` in `infra/params/core.bicepparam` |
| Cosmos: free tier already used | Another Cosmos account in that subscription has the free tier; delete it or set `enableFreeTier = false` |
| SQL deploy times out on first connection | The serverless DB was paused and is resuming; re-run the job |
| Environments missing in repo settings | Environments need a public repo (or a paid plan for private repos) |
