import tempfile
import unittest
from pathlib import Path

import httpx

from backend.report_authoring.cloud import CloudConfig, PublishResult
from backend.report_authoring.preview import RenderResult
from backend.report_authoring.qualification import (
    MODEL_DISPLAY_NAME,
    REPORT_DISPLAY_NAME,
    FabricQualificationClient,
    FullAgentQualificationRunner,
    QualificationStore,
    SemanticModelResult,
    synthetic_catalog,
    synthetic_dashboard_spec,
    synthetic_model_definition,
)
from backend.report_authoring.semantic import validate_dashboard_semantics
from backend.report_authoring.visual_review import VisualReview


class _StaticTokens:
    def token_for(self, scope: str) -> str:
        return "test-token"


class QualificationFixtureTests(unittest.TestCase):
    def test_synthetic_fixture_is_semantically_self_consistent(self) -> None:
        spec = synthetic_dashboard_spec("model-1")
        issues = validate_dashboard_semantics(spec, synthetic_catalog())
        self.assertFalse(
            [item for item in issues if item.severity == "error"],
            [item.to_dict() for item in issues],
        )
        model = synthetic_model_definition()
        sales = model["model"]["tables"][0]
        self.assertEqual(sales["partitions"][0]["source"]["type"], "calculated")
        self.assertIn("DATATABLE", sales["partitions"][0]["source"]["expression"])
        self.assertGreaterEqual(len(sales["measures"]), 5)

    def test_store_persists_steps_and_resource_ids(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = QualificationStore(Path(root) / "qualification.sqlite3")
            run_id = store.begin_run()
            with store.step(run_id, "example") as detail:
                detail["answer"] = 42
            store.save_resource("workspace", "report", "QA", "report-1")
            store.finish(run_id, "VERIFIED")

            reopened = QualificationStore(Path(root) / "qualification.sqlite3")
            self.assertEqual(
                reopened.resource("workspace", "report", "QA"), "report-1"
            )
            self.assertEqual(reopened.steps(run_id)[0]["detail"]["answer"], 42)


class FabricQualificationClientTests(unittest.TestCase):
    def test_readiness_acquires_both_tokens_and_retries_throttling(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"id": "workspace-1", "displayName": "QA"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cloud = FabricQualificationClient(
            CloudConfig(workspace_id="workspace-1", poll_interval_seconds=0),
            _StaticTokens(),
            client,
            sleep=lambda _: None,
        )
        result = cloud.check_workspace()
        self.assertEqual(result["display_name"], "QA")
        self.assertEqual(len(calls), 2)

    def test_creates_semantic_model_and_completes_lro(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                payload = request.read().decode()
                self.assertIn('"format":"TMSL"', payload)
                return httpx.Response(
                    202,
                    headers={"x-ms-operation-id": "model-operation", "Retry-After": "0"},
                )
            if request.url.path.endswith("/result"):
                return httpx.Response(
                    200,
                    json={"id": "model-1", "displayName": MODEL_DISPLAY_NAME},
                )
            return httpx.Response(200, json={"status": "Succeeded"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cloud = FabricQualificationClient(
            CloudConfig(workspace_id="workspace-1", poll_interval_seconds=0),
            _StaticTokens(),
            client,
            sleep=lambda _: None,
        )
        result = cloud.ensure_model(
            MODEL_DISPLAY_NAME, synthetic_model_definition(), known_id=None
        )
        self.assertEqual(result.action, "created")
        self.assertEqual(result.semantic_model_id, "model-1")

    def test_refreshes_semantic_model_to_completion(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "POST":
                return httpx.Response(202)
            return httpx.Response(200, json={"value": [{"status": "Completed"}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cloud = FabricQualificationClient(
            CloudConfig(workspace_id="workspace-1", poll_interval_seconds=0),
            _StaticTokens(),
            client,
            sleep=lambda _: None,
        )
        result = cloud.refresh_model("model-1")
        self.assertEqual(result["status"], "Completed")
        self.assertEqual([item[0] for item in calls], ["POST", "GET"])


class _FakeCloud:
    def __init__(self):
        self.known_model_ids = []
        self.known_report = None

    def check_workspace(self):
        return {"workspace_id": "workspace-1", "display_name": "QA"}

    def ensure_model(self, display_name, model, known_id=None):
        self.known_model_ids.append(known_id)
        return SemanticModelResult(
            "updated" if known_id else "created",
            "workspace-1",
            known_id or "model-1",
            display_name,
        )

    def refresh_model(self, semantic_model_id):
        return {"status": "Completed"}

    def execute_dax(self, semantic_model_id):
        return {"row": {"[Revenue]": 100.0}, "result_count": 1}

    def find_report(self, display_name):
        return self.known_report


class _FakePublisher:
    def __init__(self):
        self.report_ids = []

    def publish(
        self,
        report_path,
        display_name,
        semantic_model_id=None,
        report_id=None,
    ):
        self.report_ids.append(report_id)
        return PublishResult(
            "updated" if report_id else "created",
            "workspace-1",
            report_id or "report-1",
            display_name,
        )


class _FakeRenderer:
    def render_report(self, report_id, output_path, page_names=None, locale="en-US"):
        image = Path(output_path) / "QualificationOverview.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"fake-png")
        return RenderResult(
            provider="fake",
            artifacts=[str(image)],
            warnings=[],
            metadata={"report_id": report_id},
        )


def _approved_review(images, manifest):
    return VisualReview.model_validate(
        {
            "approved": True,
            "summary": "Qualification report is readable.",
            "issues": [],
        }
    )


class FullQualificationRunnerTests(unittest.TestCase):
    def test_runs_end_to_end_and_reuses_persisted_cloud_ids(self) -> None:
        with tempfile.TemporaryDirectory() as root_value:
            root = Path(root_value)
            cloud = _FakeCloud()
            publisher = _FakePublisher()
            runner = FullAgentQualificationRunner(
                CloudConfig(workspace_id="workspace-1"),
                state_path=root / "qualification.sqlite3",
                output_root=root / "output",
                cloud=cloud,
                publisher=publisher,
                renderer=_FakeRenderer(),
                reviewer=_approved_review,
            )
            first = runner.run()
            second = runner.run()

            self.assertEqual(first.status, "VERIFIED", first.to_dict())
            self.assertEqual(first.semantic_model_id, "model-1")
            self.assertEqual(first.report_id, "report-1")
            self.assertEqual(first.pages_rendered, 1)
            self.assertEqual(first.tests_failed, 0)
            self.assertEqual(first.tests_passed, 8)
            self.assertIsNone(cloud.known_model_ids[0])
            self.assertEqual(cloud.known_model_ids[1], "model-1")
            self.assertIsNone(publisher.report_ids[0])
            self.assertEqual(publisher.report_ids[1], "report-1")


if __name__ == "__main__":
    unittest.main()
