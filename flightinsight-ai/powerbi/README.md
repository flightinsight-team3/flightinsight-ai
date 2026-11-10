# powerbi/

Save reports as **Power BI Project (.pbip)** (File → Save as → .pbip), not `.pbix`.
`.pbip` is a folder of text files, so changes show up in PRs and merge cleanly.

- Connect only to `vw_*` views in the `flightinsight` database.
- Use **Import** mode, not DirectQuery, so the serverless database can auto-pause.
