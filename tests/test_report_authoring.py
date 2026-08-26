import json
import base64
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from backend.report_authoring import DashboardSpec, compile_report
from backend.report_authoring.layout import validate_page_layout
from backend.report_authoring.pbir import inspect_pbir_project, validate_pbir_project
from backend.report_authoring.visual_capabilities import VISUAL_CAPABILITIES


def sample_spec() -> DashboardSpec:
    return DashboardSpec.model_validate({
        "title": "Executive Sales",
        "dataset": {"path": "../Sales.SemanticModel"},
        "pages": [{
            "name": "Overview",
            "visuals": [
                {
                    "type": "card",
                    "title": "Revenue",
                    "position": {"column": 0, "row": 0, "width": 3, "height": 2},
                    "values": [{"table": "Sales", "name": "Revenue", "kind": "measure"}],
                },
                {
                    "type": "lineChart",
                    "title": "Revenue Trend",
                    "position": {"column": 0, "row": 2, "width": 8, "height": 4},
                    "category": {"table": "Date", "name": "Month"},
                    "values": [{"table": "Sales", "name": "Revenue", "kind": "measure"}],
                },
            ],
        }],
    })


class ReportAuthoringTests(unittest.TestCase):
    def test_compiles_complete_staged_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(sample_spec(), root)
            self.assertTrue(result.validation.valid, result.validation.to_dict())
            self.assertEqual(result.validation.page_count, 1)
            self.assertEqual(result.validation.visual_count, 2)
            report_root = Path(result.report_path)
            self.assertTrue((report_root / "definition.pbir").is_file())
            self.assertTrue((report_root.parent / "Executive-Sales.pbip").is_file())
            inspected = inspect_pbir_project(report_root)
            self.assertEqual(inspected["pages"][0]["visual_count"], 2)

    def test_rejects_invalid_card_roles(self) -> None:
        payload = sample_spec().model_dump(by_alias=True)
        payload["pages"][0]["visuals"][0]["values"] = []
        with self.assertRaises(ValidationError):
            DashboardSpec.model_validate(payload)

    def test_detects_layout_overlap(self) -> None:
        spec = sample_spec().model_copy(deep=True)
        spec.pages[0].visuals[1].position.row = 0
        self.assertTrue(validate_page_layout(spec.pages[0]))

    def test_generated_visual_uses_field_expression(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(sample_spec(), root)
            visual_file = next(Path(result.report_path).glob(
                "definition/pages/*/visuals/*/visual.json"
            ))
            visual = json.loads(visual_file.read_text(encoding="utf-8"))
            self.assertIn("queryState", visual["visual"]["query"])

    def test_native_visual_colors_are_emitted(self) -> None:
        spec = sample_spec().model_copy(deep=True)
        spec.pages[0].visuals[0].font_color = "#2563EB"
        spec.pages[0].visuals[1].font_color = "#059669"
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(spec, root)
            visuals = sorted(Path(result.report_path).glob(
                "definition/pages/*/visuals/*/visual.json"
            ))
            cards = [json.loads(path.read_text(encoding="utf-8")) for path in visuals]
            card = next(item for item in cards if item["visual"]["visualType"] == "cardVisual")
            line = next(item for item in cards if item["visual"]["visualType"] == "lineChart")
            card_color = card["visual"]["objects"]["calloutValue"][0]["properties"]["color"]
            line_color = line["visual"]["objects"]["dataPoint"][0]["properties"]["fill"]
            self.assertEqual(card_color["solid"]["color"]["expr"]["Literal"]["Value"], "'#2563EB'")
            self.assertEqual(line_color["solid"]["color"]["expr"]["Literal"]["Value"], "'#059669'")

    def test_numeric_column_value_is_emitted_as_sum_aggregation(self) -> None:
        spec = DashboardSpec.model_validate({
            "title": "Aggregated Card",
            "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [{
                "name": "Overview",
                "visuals": [{
                    "type": "card",
                    "title": "Total Revenue",
                    "position": {"column": 0, "row": 0, "width": 4, "height": 2},
                    "fields": {"value": [{
                        "table": "Sales", "name": "Revenue", "kind": "column"
                    }]},
                }],
            }],
        })
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(spec, root)
            visual_file = next(Path(result.report_path).glob(
                "definition/pages/*/visuals/*/visual.json"
            ))
            visual = json.loads(visual_file.read_text(encoding="utf-8"))["visual"]
            projection = visual["query"]["queryState"]["Data"]["projections"][0]

            self.assertEqual(visual["visualType"], "cardVisual")
            self.assertEqual(projection["field"]["Aggregation"]["Function"], 0)
            self.assertEqual(projection["queryRef"], "Sum(Sales.Revenue)")
            self.assertEqual(projection["nativeQueryRef"], "Sum of Revenue")


class ExpandedVisualAuthoringTests(unittest.TestCase):
    @staticmethod
    def visual_payload(visual_type: str) -> dict:
        capability = VISUAL_CAPABILITIES[visual_type]
        fields = {}
        for role_name, role in capability.roles.items():
            if role.min_fields:
                field = (
                    {"table": "Date", "name": "Month"}
                    if role.field_kind == "column"
                    else {"table": "Sales", "name": "Revenue", "kind": "measure"}
                )
                fields[role_name] = [field for _ in range(role.min_fields)]
        if not fields and capability.min_total_fields:
            role_name, role = next(iter(capability.roles.items()))
            fields[role_name] = [{"table": "Date", "name": "Month"}]
        payload = {
            "type": visual_type,
            "title": f"Test {visual_type}",
            "position": {"column": 0, "row": 0, "width": 6, "height": 4},
            "fields": fields,
        }
        if visual_type == "textbox":
            payload["content"] = "Executive overview"
        elif visual_type == "basicShape":
            payload["shape_type"] = "rectangle"
        elif visual_type == "actionButton":
            payload["content"] = "Open documentation"
            payload["action"] = {"type": "webUrl", "target": "https://learn.microsoft.com"}
        elif visual_type == "image":
            payload["image_url"] = "https://example.com/logo.png"
        return payload

    def test_every_registered_visual_compiles(self) -> None:
        for visual_type in VISUAL_CAPABILITIES:
            with self.subTest(visual_type=visual_type):
                spec = DashboardSpec.model_validate({
                    "title": f"Visual {visual_type}",
                    "dataset": {"path": "../Sales.SemanticModel"},
                    "pages": [{
                        "name": "Overview",
                        "visuals": [self.visual_payload(visual_type)],
                    }],
                })
                with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
                    result = compile_report(spec, root)
                    self.assertTrue(result.validation.valid, result.validation.to_dict())

    def test_registered_visuals_pass_official_pbir_schemas(self) -> None:
        pages = []
        for index, visual_type in enumerate(VISUAL_CAPABILITIES):
            page_index, slot = divmod(index, 4)
            if page_index == len(pages):
                pages.append({"name": f"Page {page_index + 1}", "visuals": []})
            visual = self.visual_payload(visual_type)
            visual["position"] = {
                "column": 0 if slot % 2 == 0 else 6,
                "row": 0 if slot < 2 else 5,
                "width": 6,
                "height": 4,
            }
            pages[page_index]["visuals"].append(visual)
        spec = DashboardSpec.model_validate({
            "title": "Visual Matrix",
            "dataset": {"path": "../Sales.SemanticModel"},
            "pages": pages,
        })
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(spec, root)
            report = validate_pbir_project(
                result.report_path,
                official_schemas=True,
                allow_schema_download=False,
            )
            if not report.valid and any(
                issue.code == "schema_unavailable" for issue in report.issues
            ):
                report = validate_pbir_project(
                    result.report_path,
                    official_schemas=True,
                    allow_schema_download=True,
                )
            self.assertTrue(report.valid, report.to_dict())

    def test_scatter_uses_visual_specific_query_roles(self) -> None:
        visual = self.visual_payload("scatterChart")
        spec = DashboardSpec.model_validate({
            "title": "Scatter", "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [{"name": "Overview", "visuals": [visual]}],
        })
        self.assertEqual(set(spec.pages[0].visuals[0].resolved_fields()), {"X", "Y"})

    def test_ai_visuals_use_official_sample_roles(self) -> None:
        decomposition = DashboardSpec.model_validate({
            "title": "AI", "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [{"name": "Overview", "visuals": [
                self.visual_payload("decompositionTreeVisual")
            ]}],
        }).pages[0].visuals[0]
        influencers = DashboardSpec.model_validate({
            "title": "AI", "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [{"name": "Overview", "visuals": [
                self.visual_payload("keyDriversVisual")
            ]}],
        }).pages[0].visuals[0]
        self.assertEqual(set(decomposition.resolved_fields()), {"Analyze", "ExplainBy"})
        self.assertEqual(set(influencers.resolved_fields()), {"Target", "ExplainBy"})

    def test_page_navigation_button_resolves_page_identifier(self) -> None:
        button = self.visual_payload("actionButton")
        button["action"] = {"type": "pageNavigation", "target": "Details"}
        spec = DashboardSpec.model_validate({
            "title": "Navigation", "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [
                {"name": "Overview", "visuals": [button]},
                {"name": "Details", "visuals": [self.visual_payload("card")]},
            ],
        })
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(spec, root)
            visual_files = Path(result.report_path).glob(
                "definition/pages/*/visuals/*/visual.json"
            )
            button_json = next(
                item for item in (json.loads(path.read_text()) for path in visual_files)
                if item["visual"]["visualType"] == "actionButton"
            )
            link = button_json["visual"]["visualContainerObjects"]["visualLink"][0]
            target = link["properties"]["navigationSection"]["expr"]["Literal"]["Value"]
            self.assertNotEqual(target.strip("'"), "Details")

    def test_trusted_custom_visual_adapter_compiles(self) -> None:
        visual = {
            "type": "denebCustomVisual1.0.0",
            "title": "Custom", "position": {"column": 0, "row": 0, "width": 6, "height": 4},
            "fields": {"values": [{"table": "Sales", "name": "Revenue", "kind": "measure"}]},
            "custom_visual": {
                "source": "appsource", "trusted": True, "installed": True,
                "roles": {"values": {"query_role": "dataset", "min_fields": 1}},
            },
        }
        spec = DashboardSpec.model_validate({
            "title": "Custom", "dataset": {"path": "../Sales.SemanticModel"},
            "pages": [{"name": "Overview", "visuals": [visual]}],
        })
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(spec, root)
            self.assertTrue(result.validation.valid, result.validation.to_dict())

    def test_rejects_unregistered_custom_visual(self) -> None:
        visual = self.visual_payload("card")
        visual["type"] = "unknownVisual"
        with self.assertRaises(ValidationError):
            DashboardSpec.model_validate({
                "title": "Invalid", "dataset": {"path": "../Sales.SemanticModel"},
                "pages": [{"name": "Overview", "visuals": [visual]}],
            })

    def test_rejects_unknown_field_role(self) -> None:
        visual = self.visual_payload("lineChart")
        visual["fields"]["latitude"] = [{"table": "Geo", "name": "Latitude"}]
        with self.assertRaises(ValidationError):
            DashboardSpec.model_validate({
                "title": "Invalid", "dataset": {"path": "../Sales.SemanticModel"},
                "pages": [{"name": "Overview", "visuals": [visual]}],
            })




from backend.report_authoring.preview import build_preview_manifest
from backend.report_authoring.quality import evaluate_report_quality
from backend.report_authoring.schema_validation import OfficialSchemaStore
from backend.report_authoring.semantic import SemanticModelCatalog, validate_dashboard_semantics
from backend.report_authoring.cloud import (
    CloudConfig,
    FabricReportPublisher,
    PowerBICloudClient,
    PowerBIExportRenderer,
    build_report_definition_parts,
)
from backend.report_authoring.visual_review import (
    VisualReview,
    decide_visual_qa_iteration,
)
from backend.report_authoring.desktop import (
    ensure_staging_semantic_model,
    open_report_in_powerbi_desktop,
    prepare_report_for_desktop,
)
from backend.report_authoring.workspace import DashboardWorkspaceManager
from backend.report_authoring.qa import DashboardQARejected, QAPolicy


class MilestoneTwoTests(unittest.TestCase):
    def test_semantic_catalog_accepts_known_fields(self) -> None:
        catalog = SemanticModelCatalog.model_validate({"tables": [
            {"name": "Sales", "measures": [{"name": "Revenue", "data_type": "currency"}]},
            {"name": "Date", "columns": [{"name": "Month", "distinct_count": 12}]},
        ]})
        self.assertFalse(validate_dashboard_semantics(sample_spec(), catalog))

    def test_semantic_catalog_rejects_unknown_fields(self) -> None:
        catalog = SemanticModelCatalog.model_validate({"tables": [
            {"name": "Sales"}, {"name": "Date"},
        ]})
        issues = validate_dashboard_semantics(sample_spec(), catalog)
        self.assertTrue(any(item.code == "unknown_field" for item in issues))

    def test_quality_flags_small_visual(self) -> None:
        spec = sample_spec().model_copy(deep=True)
        spec.pages[0].visuals[0].position.width = 1
        self.assertTrue(any(
            item.code == "small_visual" for item in evaluate_report_quality(spec)
        ))

    def test_preview_manifest_lists_visuals(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(sample_spec(), root)
            manifest = build_preview_manifest(result.report_path)
            self.assertEqual(len(manifest["pages"][0]["visuals"]), 2)

    def test_schema_store_rejects_untrusted_host(self) -> None:
        store = OfficialSchemaStore(Path(__file__).parent / ".schema-test")
        with self.assertRaises(ValueError):
            store.load("https://example.com/schema.json")


class _StaticTokens:
    def token_for(self, scope: str) -> str:
        return "test-token"


class CloudVisualQATests(unittest.TestCase):
    def test_cloud_client_lists_models_builds_catalog_and_executes_dax(self) -> None:
        model = {
            "model": {"tables": [{
                "name": "Sales",
                "columns": [{"name": "Region", "dataType": "string"}],
                "measures": [{"name": "Revenue", "dataType": "decimal"}],
            }]}
        }
        encoded_model = base64.b64encode(json.dumps(model).encode()).decode()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path.endswith("/semanticModels"):
                return httpx.Response(200, json={"value": [{
                    "id": "model-1", "displayName": "Sales Model"
                }]})
            if request.url.path.endswith("/getDefinition"):
                return httpx.Response(200, json={"definition": {"parts": [{
                    "path": "model.bim", "payload": encoded_model
                }]}})
            if request.url.path.endswith("/executeQueries"):
                return httpx.Response(200, json={"results": [{"tables": [{
                    "rows": [{"[Revenue]": 42}]
                }]}]})
            return httpx.Response(404)

        client = PowerBICloudClient(
            CloudConfig(workspace_id="workspace-1"),
            _StaticTokens(),
            httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.assertEqual(client.list_semantic_models()[0]["id"], "model-1")
        catalog = client.semantic_catalog("model-1")
        self.assertEqual(catalog.tables[0].columns[0].name, "Region")
        self.assertEqual(catalog.tables[0].measures[0].name, "Revenue")
        result = client.execute_dax("model-1", "EVALUATE ROW(\"Revenue\", 42)")
        self.assertEqual(result["results"][0]["tables"][0]["rows"][0]["[Revenue]"], 42)

    def test_cloud_client_rejects_non_query_dax(self) -> None:
        client = PowerBICloudClient(CloudConfig(workspace_id="workspace-1"), _StaticTokens())
        with self.assertRaisesRegex(ValueError, "must begin"):
            client.execute_dax("model-1", "DROP TABLE Sales")

    def test_pro_mode_supports_publication_but_rejects_png_export(self) -> None:
        config = CloudConfig(workspace_id="workspace-1", license_mode="pro")
        self.assertFalse(config.supports_export_to_file)
        renderer = PowerBIExportRenderer(config, _StaticTokens())
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            with self.assertRaisesRegex(ValueError, "ExportToFile API requires"):
                renderer.render_report("report-1", root)

    def test_capacity_mode_supports_png_export(self) -> None:
        config = CloudConfig(workspace_id="workspace-1", license_mode="capacity")
        self.assertTrue(config.supports_export_to_file)

    def test_definition_parts_rebind_local_semantic_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(sample_spec(), root)
            parts = build_report_definition_parts(result.report_path, "model-123")
            definition_part = next(item for item in parts if item["path"] == "definition.pbir")
            definition = json.loads(base64.b64decode(definition_part["payload"]))
            self.assertEqual(
                definition["datasetReference"]["byConnection"]["connectionString"],
                "semanticmodelid=model-123",
            )

    def test_definition_parts_require_remote_model_for_by_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = compile_report(sample_spec(), root)
            with self.assertRaises(ValueError):
                build_report_definition_parts(result.report_path)

    def test_fabric_publisher_completes_long_running_create(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    202,
                    headers={"x-ms-operation-id": "operation-1", "Retry-After": "0"},
                )
            if request.url.path.endswith("/operations/operation-1/result"):
                return httpx.Response(200, json={"id": "report-1", "displayName": "QA Report"})
            return httpx.Response(200, json={"status": "Succeeded", "percentComplete": 100})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        config = CloudConfig(workspace_id="workspace-1", poll_interval_seconds=0)
        publisher = FabricReportPublisher(config, _StaticTokens(), client, sleep=lambda _: None)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            compiled = compile_report(sample_spec(), root)
            result = publisher.publish(
                compiled.report_path, "QA Report", semantic_model_id="model-1"
            )
        self.assertEqual(result.report_id, "report-1")
        self.assertEqual(result.operation_id, "operation-1")

    def test_powerbi_renderer_extracts_page_pngs(self) -> None:
        bundle_bytes = io.BytesIO()
        with zipfile.ZipFile(bundle_bytes, "w") as bundle:
            bundle.writestr("Overview.png", b"fake-png-one")
            bundle.writestr("Details.png", b"fake-png-two")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(202, json={"id": "export-1"})
            if request.url.path.endswith("/file"):
                return httpx.Response(200, content=bundle_bytes.getvalue())
            return httpx.Response(200, json={"status": "Succeeded", "percentComplete": 100})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        config = CloudConfig(workspace_id="workspace-1", poll_interval_seconds=0)
        renderer = PowerBIExportRenderer(config, _StaticTokens(), client, sleep=lambda _: None)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            result = renderer.render_report("report-1", root)
            self.assertEqual(len(result.artifacts), 2)
            self.assertTrue(all(Path(item).is_file() for item in result.artifacts))
        self.assertEqual(result.metadata["export_id"], "export-1")

    def test_visual_qa_iteration_is_bounded(self) -> None:
        review = VisualReview.model_validate({
            "approved": False,
            "summary": "A chart is clipped",
            "issues": [{
                "page": "Overview",
                "visual": "Revenue Trend",
                "severity": "error",
                "category": "layout",
                "problem": "The right edge is clipped",
                "recommendation": "Reduce width by one grid column",
                "confidence": 0.95,
            }],
        })
        first = decide_visual_qa_iteration(review, attempt=1, max_attempts=3)
        final = decide_visual_qa_iteration(review, attempt=3, max_attempts=3)
        self.assertTrue(first.should_revise)
        self.assertFalse(final.should_revise)


class DesktopVisualHandoffTests(unittest.TestCase):
    def test_staging_model_uses_supported_schema_and_contains_data(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            model = ensure_staging_semantic_model(root, sample_spec())
            definition = json.loads(
                (model / "definition.pbism").read_text(encoding="utf-8")
            )
            payload = json.loads((model / "model.bim").read_text(encoding="utf-8"))

            self.assertEqual(
                definition["$schema"],
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "semanticModel/definitionProperties/1.0.0/schema.json",
            )
            self.assertEqual(definition["version"], "4.2")
            # Verify compatibility level is a valid positive integer (detected from installed Desktop)
            self.assertIsInstance(payload["compatibilityLevel"], int)
            self.assertGreater(payload["compatibilityLevel"], 0)
            tables = {table["name"]: table for table in payload["model"]["tables"]}
            self.assertEqual(
                {column["name"] for column in tables["Sales"]["columns"]},
                {"__Revenue_Value"},
            )
            self.assertEqual(
                {measure["name"] for measure in tables["Sales"]["measures"]},
                {"Revenue"},
            )
            self.assertEqual(
                {column["name"] for column in tables["Date"]["columns"]},
                {"Month"},
            )
            self.assertIn("#table", "\n".join(
                tables["Sales"]["partitions"][0]["source"]["expression"]
            ))

    def test_prepares_staged_report_for_real_desktop_rendering(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            model = root / "Sales.SemanticModel"
            model.mkdir()
            (model / "definition.pbism").write_text("{}", encoding="utf-8")
            compiled = compile_report(sample_spec(), root / "staging")
            result = prepare_report_for_desktop(compiled.report_path, model)
            definition = json.loads(Path(result.pbir_path).read_text(encoding="utf-8"))
            reference = definition["datasetReference"]["byPath"]["path"]
            self.assertEqual(reference, result.relative_model_path)
            self.assertEqual(
                (Path(compiled.report_path) / reference).resolve(), model.resolve()
            )
            self.assertTrue(result.validation["valid"])

    @unittest.skipUnless(sys.platform == "win32", "os.startfile is Windows-only")
    def test_desktop_open_uses_definition_pbir_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            model = ensure_staging_semantic_model(root, sample_spec())
            compiled = compile_report(sample_spec(), root)
            prepare_report_for_desktop(compiled.report_path, model)
            with patch("backend.report_authoring.desktop.os.startfile") as startfile:
                opened = open_report_in_powerbi_desktop(compiled.report_path)
            startfile.assert_called_once_with(opened)
            self.assertTrue(opened.endswith("Executive-Sales.pbip"))

    def test_desktop_open_rejects_cloud_only_dataset_reference(self) -> None:
        payload = sample_spec().model_dump()
        payload["dataset"] = {"semantic_model_id": "cloud-model-id"}
        cloud_spec = DashboardSpec.model_validate(payload)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            compiled = compile_report(cloud_spec, root)
            with patch("backend.report_authoring.desktop.os.startfile", create=True) as startfile:
                with self.assertRaisesRegex(ValueError, "cloud-bound report"):
                    open_report_in_powerbi_desktop(compiled.report_path)
            startfile.assert_not_called()


class StatefulDashboardWorkspaceTests(unittest.TestCase):
    def _model(self, root: Path) -> Path:
        import json as _json
        from backend.report_authoring.desktop_version import detect_compatibility_level
        model = root / "Sales.SemanticModel"
        model.mkdir(parents=True, exist_ok=True)
        (model / "definition.pbism").write_text(_json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2",
        }, indent=2) + "\n", encoding="utf-8")
        (model / "model.bim").write_text(_json.dumps({
            "compatibilityLevel": detect_compatibility_level(),
            "model": {
                "tables": [
                    {
                        "name": "Sales",
                        "columns": [
                            {"name": "__Revenue_Value", "dataType": "double", "sourceColumn": "Revenue"},
                            {"name": "Month", "dataType": "string", "sourceColumn": "Month"},
                        ],
                        "measures": [
                            {"name": "Revenue", "expression": "SUM('Sales'[__Revenue_Value])", "formatString": "#,0"},
                        ],
                        "partitions": [
                            {"name": "p", "mode": "import", "source": {"type": "m", "expression": ["let", "    x = 1", "in", "    x"]}},
                        ],
                    },
                    {
                        "name": "Date",
                        "columns": [{"name": "Month", "dataType": "string", "sourceColumn": "Month"}],
                        "partitions": [
                            {"name": "p", "mode": "import", "source": {"type": "m", "expression": ["let", "    x = 1", "in", "    x"]}},
                        ],
                    },
                ],
            },
        }, indent=2) + "\n", encoding="utf-8")
        return model

    @staticmethod
    def _catalog(*, include_fields: bool = True) -> SemanticModelCatalog:
        return SemanticModelCatalog.model_validate({"tables": [
            {
                "name": "Sales",
                "measures": (
                    [{"name": "Revenue", "data_type": "currency"}]
                    if include_fields else []
                ),
            },
            {
                "name": "Date",
                "columns": (
                    [{"name": "Month", "data_type": "string", "distinct_count": 12}]
                    if include_fields else []
                ),
            },
        ]})

    def test_successful_revision_stores_runtime_qa_evidence(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            result = manager.create(
                sample_spec(), str(self._model(root)), catalog=self._catalog()
            )
            self.assertTrue(result.qa["promotable"])
            self.assertIn(result.qa["status"], {"VERIFIED", "VERIFIED_WITH_WARNINGS"})
            gate_names = {item["name"] for item in result.qa["gates"]}
            self.assertTrue({
                "layout", "quality", "semantic", "compile",
                "pbir_structure", "official_schema", "preview_manifest",
            }.issubset(gate_names))

    def test_semantic_failure_returns_feedback_and_preserves_active_version(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(
                root / "workspaces",
                QAPolicy(require_semantic_catalog=True),
            )
            manager.create(
                sample_spec(), str(self._model(root)), catalog=self._catalog()
            )
            with self.assertRaises(DashboardQARejected) as raised:
                manager.revise(
                    sample_spec(),
                    "Invalid semantic candidate",
                    expected_version=1,
                    catalog=self._catalog(include_fields=False),
                )
            report = raised.exception.report
            self.assertEqual(report.status, "NEEDS_REVISION")
            self.assertFalse(report.promotable)
            self.assertTrue(any(
                item.gate == "semantic" and item.classification.value == "blocking"
                for item in report.findings
            ))
            self.assertTrue(Path(raised.exception.candidate_manifest_path).is_file())
            self.assertEqual(manager.get()["dashboard"]["active_version"], 1)

    def test_quality_warning_is_feedback_not_a_promotion_blocker(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            spec = sample_spec().model_copy(deep=True)
            spec.pages[0].visuals[0].position.width = 1
            spec.pages[0].visuals[0].position.height = 1
            manager = DashboardWorkspaceManager(root / "workspaces")
            result = manager.create(spec, str(self._model(root)))
            self.assertTrue(result.qa["promotable"])
            self.assertEqual(result.qa["status"], "VERIFIED_WITH_WARNINGS")
            self.assertTrue(any(
                item["code"] == "small_visual"
                and item["classification"] == "improvement"
                for item in result.qa["findings"]
            ))

    def test_identical_failures_stop_at_needs_review(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(
                root / "workspaces",
                QAPolicy(max_attempts=3, require_semantic_catalog=True),
            )
            manager.create(
                sample_spec(), str(self._model(root)), catalog=self._catalog()
            )
            statuses = []
            for _ in range(3):
                with self.assertRaises(DashboardQARejected) as raised:
                    manager.revise(
                        sample_spec(),
                        "Repeated invalid candidate",
                        expected_version=1,
                        catalog=self._catalog(include_fields=False),
                    )
                statuses.append(raised.exception.report.status)
            self.assertEqual(statuses, [
                "NEEDS_REVISION", "NEEDS_REVISION", "NEEDS_REVIEW"
            ])
            self.assertEqual(manager.get()["dashboard"]["active_version"], 1)

    def test_active_dashboard_survives_manager_restart(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            created = manager.create(sample_spec(), str(self._model(root)))
            restarted = DashboardWorkspaceManager(root / "workspaces")
            state = restarted.get()
            self.assertEqual(state["dashboard"]["dashboard_id"], created.dashboard_id)
            self.assertEqual(state["dashboard"]["active_version"], 1)
            self.assertEqual(state["current"]["spec"]["title"], "Executive Sales")

    def test_revision_is_immutable_and_conflict_checked(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            manager.create(sample_spec(), str(self._model(root)))
            revised = sample_spec().model_copy(deep=True)
            revised.pages[0].visuals[0].title = "Net Revenue"
            result = manager.revise(revised, "Clarify KPI title", expected_version=1)
            self.assertEqual(result.version, 2)
            first = json.loads(Path(manager.get()["current"]["spec_path"]).read_text())
            self.assertEqual(first["version"], 2)
            original = json.loads(
                (manager.root / result.dashboard_id / "versions" / "0001.json").read_text()
            )
            self.assertEqual(original["spec"]["pages"][0]["visuals"][0]["title"], "Revenue")
            with self.assertRaises(RuntimeError):
                manager.revise(revised, "Stale edit", expected_version=1)

    def test_audit_versions_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            created = manager.create(sample_spec(), str(self._model(root)))
            revised = sample_spec().model_copy(deep=True)
            revised.pages[0].display_name = "Leadership"
            manager.revise(revised, "Leadership wording", expected_version=1)
            audit = manager.audit()
            self.assertTrue(audit["valid"])
            self.assertEqual(audit["version"], 2)
            self.assertEqual(len(manager.list_versions()), 2)
            rollback = manager.rollback(1)
            self.assertEqual(rollback.version, 3)
            current = manager.get()["current"]
            self.assertEqual(current["spec"], json.loads(Path(created.spec_path).read_text())["spec"])

    @unittest.skipUnless(sys.platform == "win32", "os.startfile is Windows-only")
    def test_open_active_uses_saved_semantic_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            manager.create(sample_spec(), str(self._model(root)))
            with patch("backend.report_authoring.desktop.os.startfile"):
                opened = manager.open_active_in_desktop()
            self.assertTrue(opened["opened"])
            self.assertEqual(opened["version"], 1)

    def test_open_active_auto_generates_staging_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            created = manager.create(sample_spec(), semantic_model_path=None)
            refresh_result = {
                "processed": True,
                "verification_table": "Sales",
                "row_count": 6,
            }
            with patch(
                "backend.report_authoring.workspace."
                "open_and_refresh_report_in_powerbi_desktop",
                return_value=("definition.pbir", refresh_result),
            ) as open_and_refresh:
                opened = manager.open_active_in_desktop()
            self.assertTrue(opened["opened"])
            self.assertTrue("Staging.SemanticModel" in opened["semantic_model_path"])
            self.assertEqual(opened["model_refresh"]["row_count"], 6)
            open_and_refresh.assert_called_once()

if __name__ == "__main__":
    unittest.main()
