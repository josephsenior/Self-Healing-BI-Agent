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

The compiler supports 34 built-in visual types across bar/column, line/area,
combo, part-to-whole, waterfall, ribbon, scatter, table/matrix, card,
indicator, slicer, map, AI, and canvas-element families. This includes Azure
Maps, shape maps, decomposition trees, key influencers, text boxes, shapes,
buttons, and images. Call `list_powerbi_visual_capabilities` to get the
authoritative type list, accepted field roles, and required configuration for
each type.

New specifications assign fields through a visual-specific `fields` map. For
example, a scatter chart uses `x` and `y`, while a combo chart uses `axis`,
`column_values`, and `line_values`. The older `category`, `values`, and
`series` properties remain supported for existing specifications. All visuals
use the same 12-column grid, converted into deterministic PBIR pixel positions.

Unlisted AppSource, organizational, or private custom visuals are supported only
through an inline `custom_visual` adapter. The adapter must declare the exact
data roles and set both `trusted: true` and `installed: true`. The compiler
never downloads or installs executable `.pbiviz` packages; it only authors
configuration for a visual already available in the target environment.

## MCP workflow

1. Call `list_powerbi_visual_capabilities` and select a valid type and roles.
2. Call validate_dashboard_spec with the proposed specification.
3. Fix field-role or layout errors.
4. Call stage_pbir_report.
5. Call validate_pbir_report or inspect_pbir_report on the staged report.
6. Call `check_powerbi_cloud_qa_readiness`.
7. Call `publish_pbir_to_fabric` with a remote semantic model ID.
8. Call `render_powerbi_report` to export the real report pages as PNG files.
9. Call `review_powerbi_render` to obtain structured visual findings.
10. Call `decide_powerbi_visual_qa_iteration` and revise the specification when
   allowed. The default maximum is three attempts.

A local model reference normally looks like ../Sales.SemanticModel. A report
targeting a model in Fabric can provide semantic_model_id instead.

## Real visual testing in Power BI Desktop

Power BI Desktop can open a report's `definition.pbir` directly. For a real
local render, first save the source model through Desktop as a Power BI Project
so that a `<Name>.SemanticModel` folder containing `definition.pbism` exists.
Enable the **Store reports using enhanced metadata format (PBIR)** preview
feature in Desktop.

After staging and validation:

1. Call `prepare_pbir_for_powerbi_desktop` with the staged report path and the
   local `.SemanticModel` folder. The tool rewrites only the staged report's
   `datasetReference.byPath` using a correct relative path and revalidates it.
2. Call `open_pbir_in_powerbi_desktop` to launch the generated
   `definition.pbir` through Windows.
3. Power BI Desktop loads the real semantic model and renders the actual report
   visuals. External changes require Desktop to reopen the report.

This path is free and uses the real Power BI rendering engine. It gives the user
a real visual test, but the agent still cannot inspect the rendered pixels
automatically unless Desktop screenshot automation is added.

## Stateful dashboard editing

The agent keeps generated dashboards in `.dashboard-workspaces` so follow-up
requests can refer to "the current dashboard" without repeating the complete
specification or explaining how PBIR should be edited. The directory is local
runtime state and is ignored by Git.

For a new dashboard, `create_dashboard_workspace` stores the canonical
`DashboardSpec`, compiles it, records validation results, and makes it active.
If a local `.SemanticModel` path is provided, that association is retained for
future revisions and Desktop launches.

For follow-up requests, the agent should:

1. Load the current specification with `get_active_dashboard`.
2. Inspect its current quality with `audit_active_dashboard`.
3. Decide the appropriate changes from the user's outcome, semantic metadata,
   and audit findings.
4. Submit the complete revised specification through
   `revise_active_dashboard`, including the version it started from.
5. Open the rebuilt report through
   `open_active_dashboard_in_powerbi_desktop` when a model path is available.

Every accepted revision creates an immutable version and a separate compiled
build. Optimistic version checks prevent an older edit from overwriting a newer
one. `list_dashboard_versions` exposes the history, and `rollback_dashboard`
restores an earlier specification by creating a new version rather than
deleting history.

Examples of sufficient follow-up instructions are: "improve the current
dashboard", "add a regional analysis page", or "undo the last change". The
agent owns the load, audit, revision, validation, versioning, rebuild, and
Desktop handoff mechanics.

## Runtime QA admission and refinement

Dashboard creation, revision, and rollback pass through a runtime admission
controller; this behavior does not depend on the language model remembering a
prompt. Every reachable configured gate records evidence before promotion:
layout, quality, live semantics when configured, compilation, Desktop binding,
PBIR structure, official Microsoft schemas, and preview generation.

Findings are classified as `blocking`, `improvement`, or `informational`.
Blocking findings return `accepted: false` and `NEEDS_REVISION` with exact
structured feedback while preserving the current active version. Improvement
findings permit `VERIFIED_WITH_WARNINGS`. After three attempts, or repeated
identical findings, the controller returns `NEEDS_REVIEW` instead of looping
indefinitely. Candidate manifests and QA fingerprints remain under the
workspace for auditability.

The default policy runs official-schema checks from `.pbir-schema-cache`, does
not download schemas, and treats a semantic catalog as configured only when one
is supplied. Set `POWERBI_QA_REQUIRE_SEMANTIC_CATALOG=true` for fail-closed live
semantic validation. `POWERBI_QA_BLOCKING_QUALITY_CODES` can promote selected
quality recommendations to blocking defects.

Cloud publication, PNG rendering, and multimodal review remain a separate gate
because they require Fabric configuration and authorization for external
writes. A local verification result must not be described as cloud-rendered or
visually approved.

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
