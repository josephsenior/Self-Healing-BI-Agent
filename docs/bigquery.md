# BigQuery local integration

The BigQuery integration is a bounded, read-only source for analysis, semantic
catalog generation, and local Power BI report authoring.

## Configuration

~~~dotenv
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\your-user\.credentials\bigquery-agent.json
BIGQUERY_PROJECT_ID=your-project-id
BIGQUERY_LOCATION=EU
BIGQUERY_ALLOWED_DATASETS=your-project-id.your_dataset
BIGQUERY_MAX_BYTES_BILLED=1000000000
BIGQUERY_MAX_ROWS=1000

BIGQUERY_POWERBI_IMPLEMENTATION=2.0
BIGQUERY_POWERBI_USE_STORAGE_API=false
~~~

`BIGQUERY_ALLOWED_DATASETS` is mandatory for every table operation. Multiple
fully qualified datasets are comma-separated.

The Google identity needs BigQuery Job User on the billing project and BigQuery
Data Viewer on each allowed dataset. Keeping Storage API disabled avoids adding
BigQuery Read Session permissions for the local qualification path.

## Query security boundary

Only one Standard SQL statement beginning with `SELECT` or `WITH` is accepted.
Known write and administrative keywords are rejected before an API request.

Every accepted SQL statement is first submitted as a BigQuery dry run. BigQuery
parses the SQL and returns its resolved table references. The application checks
every resolved `project.dataset` against `BIGQUERY_ALLOWED_DATASETS`; a mismatch
stops the workflow before the executable query is submitted. The executable job
also enforces `BIGQUERY_MAX_BYTES_BILLED`, and result materialization is capped by
`BIGQUERY_MAX_ROWS`.

## Power BI Desktop bridge

`bigquery_create_powerbi_semantic_model` creates a deterministic local
`.SemanticModel` directory under `.bigquery-models`. It contains:

- `definition.pbism`
- a TMSL `model.bim`
- a native `GoogleBigQuery.Database` Power Query M partition
- a non-secret `bigquery-binding.json` audit manifest

The default partition mode is DirectQuery. `storage_mode="import"` creates an
Import partition instead. The connector uses ADBC implementation 2.0 by default;
this can be changed through `BIGQUERY_POWERBI_IMPLEMENTATION`.

The model never contains the Google JSON key, service-account email, access
tokens, or other credential material. Power BI Desktop stores data-source
credentials separately. The first refresh or DirectQuery execution can therefore
require one Google service-account sign-in in Desktop; subsequent opens reuse
Desktop's credential store.

For a local report:

1. Call `bigquery_create_powerbi_semantic_model` for an allowlisted table.
2. Build the dashboard using the returned semantic catalog.
3. Pass the returned `semantic_model_path` and `catalog` to
   `create_dashboard_workspace`.
4. Call `open_active_dashboard_in_powerbi_desktop` when a local preview is
   requested.

Microsoft connector reference:
https://learn.microsoft.com/power-query/connectors/google-bigquery
