# Autonomous PBIR report authoring

The report-authoring subsystem uses a strict DashboardSpec intermediate
representation instead of asking an LLM to write PBIR JSON directly.

## Current safety boundary

The MCP integration can inspect, validate, and stage reports under
.pbir-staging. It cannot overwrite a live Power BI project or deploy to a
Fabric workspace. Apply and deployment tools require a later milestone with
elicitation approval, backups, and optimistic file hashes.

## Supported visuals

The first compiler supports card, barChart, clusteredColumnChart, lineChart,
donutChart, tableEx, and slicer. Specifications use a 12-column grid which is
converted into deterministic PBIR pixel positions.

## MCP workflow

1. Call validate_dashboard_spec with the proposed specification.
2. Fix field-role or layout errors.
3. Call stage_pbir_report.
4. Call validate_pbir_report or inspect_pbir_report on the staged report.
5. Open the staged definition.pbir in Power BI Desktop for visual QA.

A local model reference normally looks like ../Sales.SemanticModel. A report
targeting a model in Fabric can provide semantic_model_id instead.

## Validation scope

This milestone validates the intermediate model, required PBIR files, page and
visual references, positions, generated JSON, and layout collisions. Full
Microsoft JSON Schema resolution, live semantic-field resolution, rendering,
apply, and Fabric deployment are subsequent milestones.


## Milestone 2 validation

Dashboard specifications can be checked against a SemanticModelCatalog assembled
from live Power BI MCP metadata. Validation reports unknown or hidden fields,
invalid field roles, nonnumeric values, and high-cardinality dimensions.

validate_pbir_official_schemas resolves only versioned Microsoft Fabric schema
URLs and caches them in .pbir-schema-cache. Network retrieval requires the
explicit allow_schema_download flag. evaluate_dashboard_quality checks density,
sizing, title length, KPI presence, and excessive series. preview_pbir_report
produces a deterministic render manifest; ReportRenderer is the adapter boundary
for a future Desktop or Fabric screenshot implementation.
