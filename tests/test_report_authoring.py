import json
import tempfile
import unittest
from pathlib import Path

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

if __name__ == "__main__":
    unittest.main()
