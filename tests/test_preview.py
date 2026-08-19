import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.application.graph_agent import _extract_preview_images
from backend.main import ROOT_DIR, app

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _write_artifact(rel_path: str, content: bytes = PNG_BYTES) -> Path:
    target = Path(ROOT_DIR) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


class PreviewImageExtractionTests(unittest.TestCase):
    def test_extracts_nested_png_path(self) -> None:
        payload = json.dumps({"artifacts": [r"C:\repo\.pbir-previews\dash\abc.png"]})
        result = _extract_preview_images(payload)
        self.assertEqual(result, ["/api/preview?path=.pbir-previews%2Fdash%2Fabc.png"])

    def test_extracts_workspace_artifact(self) -> None:
        result = _extract_preview_images(
            '{"path": ".dashboard-workspaces/runs/x/render.png"}'
        )
        self.assertEqual(result, ["/api/preview?path=.dashboard-workspaces%2Fruns%2Fx%2Frender.png"])

    def test_deduplicates_repeated_paths(self) -> None:
        result = _extract_preview_images(
            '{"images": [".pbir-previews/a.png", ".pbir-previews/a.png"]}'
        )
        self.assertEqual(len(result), 1)

    def test_ignores_non_image_and_foreign_paths(self) -> None:
        result = _extract_preview_images(
            '{"files": [".pbir-previews/note.txt", "C:\\\\other\\\\x.png", '
            '"C:\\\\repo\\\\backend\\\\main.py"]}'
        )
        self.assertEqual(result, [])

    def test_returns_empty_for_non_json(self) -> None:
        self.assertEqual(_extract_preview_images("not json at all"), [])
        self.assertEqual(_extract_preview_images(""), [])
        self.assertEqual(_extract_preview_images(None), [])


class PreviewEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_serves_png_artifact(self) -> None:
        artifact = _write_artifact(".pbir-previews/test-endpoint/preview.png")
        try:
            response = self.client.get("/api/preview", params={"path": ".pbir-previews/test-endpoint/preview.png"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertEqual(response.content, PNG_BYTES)
        finally:
            artifact.unlink(missing_ok=True)

    def test_serves_workspace_artifact(self) -> None:
        artifact = _write_artifact(".dashboard-workspaces/enc/test.png")
        try:
            response = self.client.get("/api/preview", params={"path": ".dashboard-workspaces/enc/test.png"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
        finally:
            artifact.unlink(missing_ok=True)

    def test_path_traversal_never_leaks_files(self) -> None:
        marker = Path(ROOT_DIR) / "_traversal-marker-test.txt"
        marker.write_text("TOP-SECRET-MARKER", encoding="utf-8")
        try:
            for traversal in (
                ".pbir-previews/../_traversal-marker-test.txt",
                "../_traversal-marker-test.txt",
                ".pbir-previews/..%2F_traversal-marker-test.txt",
            ):
                with self.subTest(path=traversal):
                    response = self.client.get("/api/preview", params={"path": traversal})
                    self.assertNotEqual(response.status_code, 200)
                    self.assertNotIn("TOP-SECRET-MARKER", response.text)
        finally:
            marker.unlink(missing_ok=True)

    def test_rejects_path_outside_artifact_roots(self) -> None:
        response = self.client.get("/api/preview", params={"path": "README.md"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/preview", params={"path": "backend/main.py"})
        self.assertEqual(response.status_code, 400)

    def test_returns_404_for_missing_artifact(self) -> None:
        response = self.client.get(
            "/api/preview", params={"path": ".pbir-previews/does-not-exist.png"}
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()