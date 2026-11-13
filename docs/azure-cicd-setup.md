# Connecting GitHub Actions to Azure (one-time setup)

GitHub Actions logs in to Azure with **OIDC**: no password or key is stored in GitHub.
The resource group trusts the `core` environment of this repository through a **user-assigned managed identity**.

| Item | Value |
|---|---|
| Subscription | Azure for Students - JinkunZhao (`8d99dfdf-a6d2-4bd6-b2b6-5f4d059d1b47`) |
| Resource group | `rg-flightinsight-core` |
| GitHub environment | `core` |
| Managed identity | `id-github-core` |
| Allowed regions (student policy) | westus2, canadacentral, norwayeast, francecentral, belgiumcentral |
| Regions used | West US 2 for everything except Azure SQL (Canada Central) |

## Part A — in Azure (subscription owner)

1. **Register resource providers** (Subscription → *Settings* → *Resource providers* → Register):
   `Microsoft.Storage`, `Microsoft.Sql`, `Microsoft.DataFactory`, `Microsoft.KeyVault`, `Microsoft.Web`,
   `Microsoft.DocumentDB`, `Microsoft.Insights`. The deployment identity is scoped to the resource group and
   cannot register providers itself.
2. **Managed identity.** *Managed Identities* → Create → resource group `rg-flightinsight-core`,
   region **West US 2**, name `id-github-core`.
3. **Permissions.** Resource group → *Access control (IAM)* → Add role assignment → tab
   **Privileged administrator roles** → Members: *Managed identity* → `id-github-core`:
   - **Contributor**
   - **Role Based Access Control Administrator**, condition: *assign all roles except privileged administrator
     roles* (`core.bicep` grants ADF and Functions data roles on the lake and Key Vault).
4. **Federated credential.** Identity → *Federated credentials* → Add → **GitHub Actions deploying Azure resources**:
   organization `flightinsight-team3` + its numeric ID, repository `flightinsight-ai` + its numeric ID,
   entity **Environment** = `core`, name `github-core`.
   IDs: open `https://api.github.com/orgs/flightinsight-team3` and
   `https://api.github.com/repos/flightinsight-team3/flightinsight-ai` and take the top-level `"id"`.
   The subject becomes `repo:flightinsight-team3@<orgId>/flightinsight-ai@<repoId>:environment:core`
   (GitHub's immutable subject format for repositories created after July 15, 2026).
5. **IDs.** Identity → *Overview* → *JSON View*: `clientId` and `tenantId`. Students can't open the Entra ID page.

## Part B — in GitHub (repository admin)

Repository → *Settings* → *Environments* → `core`.

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | `clientId` of `id-github-core` |
| `AZURE_TENANT_ID` | `tenantId` (Northeastern tenant) |
| `AZURE_SUBSCRIPTION_ID` | `8d99dfdf-a6d2-4bd6-b2b6-5f4d059d1b47` |
| `AZURE_RESOURCE_GROUP` | `rg-flightinsight-core` |
| `SQL_SERVER_NAME` | `sql-fi-ca-wbl5sr` (after the first deployment) |
| `FUNCTION_APP_NAME` | `func-fi-wbl5sr` (after the first deployment) |

| Secret | Value |
|---|---|
| `SQL_ADMIN_PASSWORD` | Strong password; avoid `;` `'` `"` `{` `}` |
| `SQL_CONNECTION_STRING_PROD` | `Server=tcp:sql-fi-ca-wbl5sr.database.windows.net,1433;Database=flightinsight;User ID=fiadmin;Password=<password>;Encrypt=True;Connection Timeout=120;` |
| `SQL_CONNECTION_STRING_DEV` | Same with `Database=flightinsight-dev` |

## Part C — deploy

1. Actions → **Deploy infrastructure** → `core`, *apply* unchecked → check the what-if output.
2. Run again with *apply* checked.
3. Add the post-deployment variables and secrets above.
4. Actions → **Deploy SQL schema** → `dev`; then `prod` (or merge a change under `sql/`).
5. Actions → **Deploy Functions** → Run workflow.

Key Vault holds every connection secret the code needs: `sql-odbc-flightinsight`, `sql-odbc-flightinsight-dev`,
`cosmos-nosql-key` (laptop scripts only), `cosmos-graph-key` (Gremlin has key auth only).

## Troubleshooting

| Error | Cause / fix |
|---|---|
| `MissingSubscriptionRegistration` | Register the provider named in the error (Part A, step 1) |
| `AADSTS70021: No matching federated identity record found` | Subject mismatch; the error shows the subject GitHub sent — add a credential that matches it |
| `AuthorizationFailed ... roleAssignments/write` | `id-github-core` is missing *Role Based Access Control Administrator* |
| `RequestDisallowedByPolicy` | Region not in the allowed list above |
| SQL: `Provisioning is restricted in this region` | Change `sqlLocation` in `infra/params/core.bicepparam` to another allowed region |
| `InvalidResourceLocation ... already exists in location` | A failed resource is left in the old region; delete it (or rename it in `core.bicep`) and redeploy |
| Cosmos: region has no capacity | Change `cosmosLocation` in `infra/params/core.bicepparam` |
| SQL deploy times out on first connection | The serverless DB was paused and is resuming; re-run the job |
| Cloud Shell `AuthorizationFailed` on another subscription ID | Run `az account set --subscription 8d99dfdf-a6d2-4bd6-b2b6-5f4d059d1b47` |
