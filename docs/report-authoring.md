# Autonomous PBIR report authoring

The report-authoring subsystem uses a strict DashboardSpec intermediate
representation instead of asking an LLM to write PBIR JSON directly.

## Current safety boundary

Local compilation remains isolated under `.pbir-staging`. Cloud publication is
available only through the workspace configured by
`POWERBI_STAGING_WORKSPACE_ID`. Creating or updating a Fabric report is an
external write and must follow successful local, semantic, quality, structural,
and official-schema validation. Generated PBIR is never edited in place during
visual QA; feedback is applied to `DashboardSpec` and recompiled.

## Supported visuals

The first compiler supports card, barChart, clusteredColumnChart, lineChart,
donutChart, tableEx, and slicer. Specifications use a 12-column grid which is
converted into deterministic PBIR pixel positions.

## MCP workflow

1. Call validate_dashboard_spec with the proposed specification.
2. Fix field-role or layout errors.
3. Call stage_pbir_report.
4. Call validate_pbir_report or inspect_pbir_report on the staged report.
5. Call `check_powerbi_cloud_qa_readiness`.
6. Call `publish_pbir_to_fabric` with a remote semantic model ID.
7. Call `render_powerbi_report` to export the real report pages as PNG files.
8. Call `review_powerbi_render` to obtain structured visual findings.
9. Call `decide_powerbi_visual_qa_iteration` and revise the specification when
   allowed. The default maximum is three attempts.

A local model reference normally looks like ../Sales.SemanticModel. A report
targeting a model in Fabric can provide semantic_model_id instead.

## Validation scope

The subsystem validates the intermediate model, required PBIR files, page and
visual references, positions, generated JSON, layout collisions, live semantic
fields, Microsoft schemas, and rendered screenshots. A live cloud run still
depends on tenant credentials, a remote semantic model, and a staging workspace
backed by a capacity that supports Power BI PNG export.


## Milestone 2 validation

Dashboard specifications can be checked against a SemanticModelCatalog assembled
from live Power BI MCP metadata. Validation reports unknown or hidden fields,
invalid field roles, nonnumeric values, and high-cardinality dimensions.

validate_pbir_official_schemas resolves only versioned Microsoft Fabric schema
URLs and caches them in .pbir-schema-cache. Network retrieval requires the
explicit allow_schema_download flag. evaluate_dashboard_quality checks density,
sizing, title length, KPI presence, and excessive series. preview_pbir_report
produces a deterministic render manifest.

## Cloud rendering and visual review

`FabricReportPublisher` serializes the enhanced PBIR project as the official
Fabric definition-parts payload. Local `byPath` dataset references are rebound
in memory to `semanticmodelid=<id>` because Fabric publishing requires a remote
semantic model reference. Create and update operations support Fabric's
long-running-operation protocol.

`PowerBIExportRenderer` starts an asynchronous `ExportTo` job in the staging
workspace, polls it, downloads the result, and safely extracts page PNGs from
the returned ZIP. Artifacts are written below `.pbir-previews` and are ignored
by Git.

`review_powerbi_render` supports Gemini, OpenAI, and Anthropic multimodal models.
It returns strict issue objects with page, visual, severity, category, visible
problem, recommended `DashboardSpec` correction, and confidence. The retry gate
prevents an autonomous agent from entering an unbounded generate/render loop.

## Microsoft configuration checklist

1. Obtain Power BI Pro for the publishing identity.
2. Create a staging workspace on Fabric, Premium, or Embedded capacity.
3. Enable the tenant setting for exporting reports as image files.
4. Create a Microsoft Entra application for unattended execution, grant the
   required Fabric/Power BI permissions, and allow it in the relevant tenant
   service-principal settings.
5. Add the identity to the staging workspace with Contributor access.
6. Configure the variables documented in `.env.example`.

For interactive testing, audience-specific bearer tokens can replace client
credentials temporarily. Never commit those tokens or the `.env` file.
