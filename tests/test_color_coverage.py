import json
import tempfile
import unittest
from pathlib import Path

from backend.report_authoring import DashboardSpec, compile_report
from backend.report_authoring.compiler import CALLOUT_COLOR_TYPES, SERIES_COLOR_TYPES
from backend.report_authoring.visual_capabilities import VISUAL_CAPABILITIES

SAMPLE_COLOR = "#112233"


def _field(role_kind: str, index: int) -> dict:
    if role_kind == "measure":
        return {"table": "Sales", "name": f"Measure {index}", "kind": "measure"}
    return {"table": "Sales", "name": f"Column {index}"}


def minimal_spec(visual_type: str, **overrides) -> DashboardSpec:
    """Build a spec that satisfies the capability role constraints of a type."""
    capability = VISUAL_CAPABILITIES[visual_type]
    fields: dict[str, list[dict]] = {}
    index = 0
    for role_name, role in capability.roles.items():
        count = max(role.min_fields, 1)
        fields[role_name] = [_field(role.field_kind, index + offset) for offset in range(count)]
        index += count
    canvas_requirements = {
        "textbox": {"content": "Hello"},
        "basicShape": {"shape_type": "rectangle"},
        "actionButton": {"action": {"type": "webUrl", "target": "https://example.com"}},
        "image": {"image_url": "https://example.com/logo.png"},
    }
    payload = {
        "title": f"Color {visual_type}",
        "dataset": {"path": "../Sales.SemanticModel"},
        "pages": [{
            "name": "Page",
            "visuals": [{
                "type": visual_type,
                "title": "Visual",
                "position": {"column": 0, "row": 0, "width": 4, "height": 3},
                "fields": fields,
                "font_color": SAMPLE_COLOR,
                **canvas_requirements.get(visual_type, {}),
                **overrides,
            }],
        }],
    }
    return DashboardSpec.model_validate(payload)


def compile_single(visual_type: str, **overrides) -> dict:
    """Compile a one-visual report and return the parsed visual.json."""
    spec = minimal_spec(visual_type, **overrides)
    with tempfile.TemporaryDirectory() as root:
        result = compile_report(spec, root)
        visual_file = next(Path(result.report_path).glob("definition/pages/*/visuals/*/visual.json"))
        return json.loads(visual_file.read_text(encoding="utf-8"))


class ColorCoverageTests(unittest.TestCase):
    def test_every_series_visual_emits_data_point_fill(self) -> None:
        for visual_type in sorted(SERIES_COLOR_TYPES):
            with self.subTest(visual_type=visual_type):
                visual = compile_single(visual_type)
                objects = visual["visual"]["objects"]
                fill = objects["dataPoint"][0]["properties"]["fill"]
                literal = fill["solid"]["color"]["expr"]["Literal"]["Value"]
                self.assertEqual(literal, f"'{SAMPLE_COLOR}'")
                labels = objects["dataLabels"][0]["properties"]["color"]
                self.assertEqual(
                    labels["solid"]["color"]["expr"]["Literal"]["Value"],
                    f"'{SAMPLE_COLOR}'",
                )

    def test_every_callout_visual_emits_callout_color(self) -> None:
        for visual_type in sorted(CALLOUT_COLOR_TYPES):
            with self.subTest(visual_type=visual_type):
                visual = compile_single(visual_type)
                color = visual["visual"]["objects"]["calloutValue"][0]["properties"]["color"]
                self.assertEqual(
                    color["solid"]["color"]["expr"]["Literal"]["Value"],
                    f"'{SAMPLE_COLOR}'",
                )

    def test_basic_shape_uses_shape_visual_type_and_fill(self) -> None:
        visual = compile_single("basicShape")
        self.assertEqual(visual["visual"]["visualType"], "shape")
        objects = visual["visual"]["objects"]
        self.assertEqual(
            objects["shape"][0]["properties"]["tileShape"]["expr"]["Literal"]["Value"],
            "'rectangle'",
        )
        fill_entry = objects["fill"][0]
        self.assertEqual(fill_entry["selector"], {"id": "default"})
        self.assertEqual(
            fill_entry["properties"]["fillColor"]["solid"]["color"]["expr"]["Literal"]["Value"],
            f"'{SAMPLE_COLOR}'",
        )
        self.assertEqual(
            objects["outline"][0]["properties"]["show"]["expr"]["Literal"]["Value"],
            "false",
        )

    def test_action_button_emits_fill_selector_pair(self) -> None:
        visual = compile_single("actionButton")
        objects = visual["visual"]["objects"]
        fill_entries = objects["fill"]
        self.assertEqual(len(fill_entries), 2)
        self.assertNotIn("selector", fill_entries[0])
        self.assertEqual(fill_entries[1]["selector"], {"id": "default"})
        self.assertEqual(
            fill_entries[1]["properties"]["fillColor"]["solid"]["color"]["expr"]["Literal"]["Value"],
            f"'{SAMPLE_COLOR}'",
        )

    def test_textbox_emits_text_color(self) -> None:
        visual = compile_single("textbox")
        paragraphs = visual["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
        text_style = paragraphs[0]["textRuns"][0]["textStyle"]
        self.assertEqual(text_style["color"], SAMPLE_COLOR)

    def test_card_maps_to_card_visual_type(self) -> None:
        visual = compile_single("card")
        self.assertEqual(visual["visual"]["visualType"], "cardVisual")

    def test_every_visual_type_compiles(self) -> None:
        for visual_type in sorted(VISUAL_CAPABILITIES):
            with self.subTest(visual_type=visual_type):
                spec = minimal_spec(visual_type)
                with tempfile.TemporaryDirectory() as root:
                    result = compile_report(spec, root)
                    self.assertTrue(result.validation.valid, result.validation.to_dict())
                    self.assertEqual(result.validation.visual_count, 1)

    def test_colorable_families_advertise_font_color(self) -> None:
        colorable = SERIES_COLOR_TYPES | CALLOUT_COLOR_TYPES | {"textbox"}
        for visual_type in sorted(colorable):
            with self.subTest(visual_type=visual_type):
                self.assertIn(
                    "font_color",
                    VISUAL_CAPABILITIES[visual_type].configuration,
                    f"{visual_type} should advertise font_color",
                )

    def test_non_colorable_families_do_not_advertise_font_color(self) -> None:
        for visual_type in ("slicer", "tableEx", "pivotTable", "azureMap", "image"):
            with self.subTest(visual_type=visual_type):
                self.assertNotIn(
                    "font_color",
                    VISUAL_CAPABILITIES[visual_type].configuration,
                    f"{visual_type} should not advertise font_color",
                )


if __name__ == "__main__":
    unittest.main()