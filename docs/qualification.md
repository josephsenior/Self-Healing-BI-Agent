# Autonomous single-user qualification

The qualification runner exercises the complete local-to-cloud report workflow without
requiring an existing Power BI Desktop model or external data source.

## What it does

~~~text
authenticate both API audiences
-> create or update a deterministic calculated-table semantic model
-> refresh the semantic model and wait for completion
-> execute a validation DAX query
-> compile and structurally validate a PBIR report
-> create or update a deterministic Fabric report
-> render the report through Power BI Export-to-file
-> review the PNG with the configured multimodal model
-> persist every step and cloud resource ID in SQLite
~~~

The fixed resource names make repeated runs idempotent:

- Agent Qualification Semantic Model
- Agent Qualification Report

The synthetic model is data-source-free. It contains a calculated Sales table with
deterministic rows and explicit measures, so no gateway, Desktop model, BigQuery
project, or manual semantic-model publication is needed.

## Required configuration

~~~dotenv
POWERBI_STAGING_WORKSPACE_ID=<fabric-trial-workspace-guid>

AZURE_TENANT_ID=<entra-tenant-guid>
AZURE_CLIENT_ID=<app-registration-client-guid>
AZURE_CLIENT_SECRET=<client-secret>

LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.6-flash
GEMINI_API_KEY=<gemini-key>
~~~

Instead of the three Entra client-credential values, short-lived audience-specific
tokens can be supplied through FABRIC_API_ACCESS_TOKEN and
POWERBI_API_ACCESS_TOKEN.

Optional settings:

~~~dotenv
POWERBI_CLOUD_TIMEOUT_SECONDS=300
POWERBI_CLOUD_POLL_SECONDS=2
POWERBI_QUALIFICATION_ROOT=.dashboard-workspaces/qualification
POWERBI_QUALIFICATION_STATE_PATH=.dashboard-workspaces/qualification/qualification.sqlite3
POWERBI_VISION_PROVIDER=gemini
POWERBI_VISION_MODEL=gemini-3.6-flash
~~~

The workspace must be assigned to the active Fabric trial capacity, and the Entra
application must have the Contributor workspace role. A Fabric tenant administrator
must enable these settings for the application (directly or through an allowed
security group):

- Service principals can call Fabric public APIs
- Allow service principals to use Power BI APIs
- Dataset Execute Queries REST API
- Export reports as image files

The PNG Export-to-file API requires a workspace backed by Fabric, Premium, or
Embedded capacity; Premium Per User alone is not supported.

## Run it

Start the application normally and ask the agent:

> Run the full autonomous agent qualification.

The MCP tool returns a structured result with status, resource IDs, rendered pages,
QA results, artifacts, warnings, and the durable step ledger.

A successful result has status VERIFIED. NEEDS_REVISION means the deterministic
cloud pipeline passed but visual review found an issue. FAILED identifies the exact
failed step and retains earlier successful resource IDs for an idempotent rerun.

## Local tests

The automated test suite uses mocked Fabric, Power BI, rendering, and vision clients,
so it does not consume cloud capacity or require credentials:

~~~powershell
python -m unittest discover -s tests -v
~~~

A real qualification run is intentionally not part of the unit suite because it
creates or updates two named items in the configured staging workspace.
