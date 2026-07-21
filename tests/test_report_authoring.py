import json
import base64
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from backend.report_authoring import DashboardSpec, compile_report
from backend.report_authoring.layout import validate_page_layout
from backend.report_authoring.pbir import inspect_pbir_project


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




from backend.report_authoring.preview import build_preview_manifest
from backend.report_authoring.quality import evaluate_report_quality
from backend.report_authoring.schema_validation import OfficialSchemaStore
from backend.report_authoring.semantic import SemanticModelCatalog, validate_dashboard_semantics
from backend.report_authoring.cloud import (
    CloudConfig,
    FabricReportPublisher,
    PowerBIExportRenderer,
    build_report_definition_parts,
)
from backend.report_authoring.visual_review import (
    VisualReview,
    decide_visual_qa_iteration,
)
from backend.report_authoring.desktop import (
    open_report_in_powerbi_desktop,
    prepare_report_for_desktop,
)
from backend.report_authoring.workspace import DashboardWorkspaceManager


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

    def test_desktop_open_uses_definition_pbir_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            compiled = compile_report(sample_spec(), root)
            with patch("backend.report_authoring.desktop.os.startfile") as startfile:
                opened = open_report_in_powerbi_desktop(compiled.report_path)
            startfile.assert_called_once_with(opened)
            self.assertTrue(opened.endswith("definition.pbir"))


class StatefulDashboardWorkspaceTests(unittest.TestCase):
    def _model(self, root: Path) -> Path:
        model = root / "Sales.SemanticModel"
        model.mkdir()
        (model / "definition.pbism").write_text("{}", encoding="utf-8")
        return model

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

    def test_open_active_uses_saved_semantic_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root_value:
            root = Path(root_value)
            manager = DashboardWorkspaceManager(root / "workspaces")
            manager.create(sample_spec(), str(self._model(root)))
            with patch("backend.report_authoring.desktop.os.startfile"):
                opened = manager.open_active_in_desktop()
            self.assertTrue(opened["opened"])
            self.assertEqual(opened["version"], 1)

if __name__ == "__main__":
    unittest.main()
