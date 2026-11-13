# adf/

Azure Data Factory writes its pipelines, datasets, linked services and triggers here through its
built-in Git integration. **Don't edit these JSON files by hand**; change them in ADF Studio.

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
4. Switch to `main` in ADF Studio and click **Publish** to make it live.
