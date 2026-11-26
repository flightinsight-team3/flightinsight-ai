# adf/

Azure Data Factory writes its pipelines, datasets, linked services and triggers here through its
built-in Git integration. **Don't edit these JSON files by hand**; change them in ADF Studio.

`PL_Master_Monthly` chains the per-step pipelines for one month: `PL_BTS_Month` and `PL_NOAA_Month`
run in parallel, then `PL_Load_Star_Month`, then the `cosmos/sync` Function (mapping its
`database_name` parameter to `{"database": "dev"|"prod"}`). It still takes `month_key` and
`database_name` parameters — nothing runs automatically on a schedule, you still trigger it once per
month (from ADF Studio's Debug/Trigger now, or from the Monitor tab for a past run).

## One-time setup (core subscription owner)

ADF Studio → Manage → Git configuration → Configure:

| Setting | Value |
|---|---|
| Repository type | GitHub |
| Repository owner | your GitHub organization |
| Repository name | `flightinsight-ai` |
| Collaboration branch | `main` |
| Publish branch | `adf_publish` |
| Root folder | `/adf` |
| Import existing resources | Yes |

GitHub will ask you to authorize the Azure Data Factory app for the organization.

## Working on a pipeline

1. In ADF Studio, create a working branch from the branch dropdown.
2. Edit and **Save** (commits to your branch), then **Debug** to test.
3. Create a pull request into `main`; merge.
4. Make it live: Actions → **Deploy ADF pipelines** → run with *apply* unchecked to preview, then
   checked to deploy. This runs the same validate+export ARM template that ADF Studio's own
   **Publish** button would generate, so there's no manual Publish click and no `adf_publish`
   branch to manage — anyone with repo access can ship a merged pipeline change, not just whoever
   has ADF Studio open.
