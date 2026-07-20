from __future__ import annotations

import base64
import json
import os
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

from .pbir import _report_root
from .preview import RenderResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
POWERBI_API = "https://api.powerbi.com/v1.0/myorg"


class CloudConfigurationError(ValueError):
    pass


class CloudAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudConfig:
    workspace_id: str
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    fabric_access_token: str = ""
    powerbi_access_token: str = ""
    timeout_seconds: float = 300.0
    poll_interval_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "CloudConfig":
        workspace_id = os.getenv("POWERBI_STAGING_WORKSPACE_ID", "").strip()
        if not workspace_id:
            raise CloudConfigurationError(
                "POWERBI_STAGING_WORKSPACE_ID is required for cloud report QA"
            )
        return cls(
            workspace_id=workspace_id,
            tenant_id=os.getenv("AZURE_TENANT_ID", "").strip(),
            client_id=os.getenv("AZURE_CLIENT_ID", "").strip(),
            client_secret=os.getenv("AZURE_CLIENT_SECRET", "").strip(),
            fabric_access_token=os.getenv("FABRIC_API_ACCESS_TOKEN", "").strip(),
            powerbi_access_token=os.getenv("POWERBI_API_ACCESS_TOKEN", "").strip(),
            timeout_seconds=float(os.getenv("POWERBI_CLOUD_TIMEOUT_SECONDS", "300")),
            poll_interval_seconds=float(os.getenv("POWERBI_CLOUD_POLL_SECONDS", "2")),
        )


class EntraTokenProvider:
    """Provides audience-specific tokens from overrides or client credentials."""

    def __init__(self, config: CloudConfig):
        self.config = config
        self._app: Any | None = None

    def token_for(self, scope: str) -> str:
        override = (
            self.config.fabric_access_token
            if scope == FABRIC_SCOPE
            else self.config.powerbi_access_token
        )
        if override:
            return override
        if not all((self.config.tenant_id, self.config.client_id, self.config.client_secret)):
            raise CloudConfigurationError(
                "configure audience-specific access tokens or AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET"
            )
        if self._app is None:
            try:
                import msal
            except ImportError as exc:
                raise CloudConfigurationError(
                    "msal is required for Microsoft Entra client-credential authentication"
                ) from exc
            self._app = msal.ConfidentialClientApplication(
                self.config.client_id,
                authority=f"https://login.microsoftonline.com/{self.config.tenant_id}",
                client_credential=self.config.client_secret,
            )
        result = self._app.acquire_token_for_client(scopes=[scope])
        token = result.get("access_token")
        if not token:
            detail = result.get("error_description") or result.get("error") or "unknown error"
            raise CloudConfigurationError(f"Microsoft Entra token acquisition failed: {detail}")
        return token


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _ensure_success(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    payload = _response_json(response)
    error = payload.get("error", payload)
    if isinstance(error, dict):
        detail = error.get("message") or error.get("errorCode") or error.get("code")
    else:
        detail = str(error)
    raise CloudAPIError(
        f"{operation} failed with HTTP {response.status_code}: {detail or response.reason_phrase}"
    )


def _safe_retry_after(response: httpx.Response, default: float) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", default)), 30.0))
    except ValueError:
        return default


def build_report_definition_parts(
    report_path: str | Path,
    semantic_model_id: str | None = None,
) -> list[dict[str, str]]:
    """Serialize a PBIR report folder for the Fabric definition API."""
    root = _report_root(report_path)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    parts: list[dict[str, str]] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative != "definition.pbir" and not (
            relative.startswith("definition/") or relative.startswith("StaticResources/")
        ):
            continue
        payload = path.read_bytes()
        if relative == "definition.pbir":
            definition = json.loads(payload.decode("utf-8"))
            reference = definition.get("datasetReference", {})
            if semantic_model_id:
                definition["datasetReference"] = {
                    "byConnection": {
                        "connectionString": f"semanticmodelid={semantic_model_id}"
                    }
                }
            elif "byPath" in reference:
                raise CloudConfigurationError(
                    "semantic_model_id is required because Fabric REST publishing "
                    "does not support a local byPath dataset reference"
                )
            payload = (json.dumps(definition, separators=(",", ":")) + "\n").encode("utf-8")
        parts.append({
            "path": relative,
            "payload": base64.b64encode(payload).decode("ascii"),
            "payloadType": "InlineBase64",
        })
    if not any(item["path"] == "definition.pbir" for item in parts):
        raise CloudConfigurationError("report definition.pbir was not found")
    return parts


@dataclass(frozen=True)
class PublishResult:
    action: str
    workspace_id: str
    report_id: str
    display_name: str
    operation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FabricReportPublisher:
    def __init__(
        self,
        config: CloudConfig,
        token_provider: EntraTokenProvider | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.tokens = token_provider or EntraTokenProvider(config)
        self.client = client or httpx.Client(timeout=config.timeout_seconds)
        self.sleep = sleep

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tokens.token_for(FABRIC_SCOPE)}",
            "Content-Type": "application/json",
        }

    def _complete_lro(self, response: httpx.Response) -> tuple[dict[str, Any], str | None]:
        if response.status_code != 202:
            return _response_json(response), None
        operation_id = response.headers.get("x-ms-operation-id")
        if not operation_id:
            location = response.headers.get("Location", "").rstrip("/")
            operation_id = location.rsplit("/", 1)[-1] if location else ""
        if not operation_id:
            raise CloudAPIError("Fabric returned 202 without an operation identifier")
        state_url = f"{FABRIC_API}/operations/{operation_id}"
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            state_response = self.client.get(state_url, headers=self._headers())
            _ensure_success(state_response, "poll Fabric operation")
            state = _response_json(state_response)
            status = state.get("status")
            if status == "Succeeded":
                result_response = self.client.get(
                    f"{state_url}/result", headers=self._headers()
                )
                _ensure_success(result_response, "get Fabric operation result")
                return _response_json(result_response), operation_id
            if status in {"Failed", "Cancelled"}:
                raise CloudAPIError(f"Fabric operation {operation_id} ended with {status}")
            self.sleep(_safe_retry_after(state_response, self.config.poll_interval_seconds))
        raise TimeoutError(f"Fabric operation {operation_id} exceeded the configured timeout")

    def publish(
        self,
        report_path: str | Path,
        display_name: str,
        semantic_model_id: str | None = None,
        report_id: str | None = None,
    ) -> PublishResult:
        definition = {
            "parts": build_report_definition_parts(report_path, semantic_model_id)
        }
        if report_id:
            url = (
                f"{FABRIC_API}/workspaces/{self.config.workspace_id}/reports/"
                f"{report_id}/updateDefinition"
            )
            response = self.client.post(
                url, headers=self._headers(), json={"definition": definition}
            )
            _ensure_success(response, "update Fabric report")
            _, operation_id = self._complete_lro(response)
            return PublishResult(
                action="updated",
                workspace_id=self.config.workspace_id,
                report_id=report_id,
                display_name=display_name,
                operation_id=operation_id,
            )

        url = f"{FABRIC_API}/workspaces/{self.config.workspace_id}/reports"
        response = self.client.post(
            url,
            headers=self._headers(),
            json={"displayName": display_name, "definition": definition},
        )
        _ensure_success(response, "create Fabric report")
        result, operation_id = self._complete_lro(response)
        created_id = str(result.get("id", ""))
        if not created_id:
            raise CloudAPIError("Fabric create report response did not include a report id")
        return PublishResult(
            action="created",
            workspace_id=self.config.workspace_id,
            report_id=created_id,
            display_name=str(result.get("displayName") or display_name),
            operation_id=operation_id,
        )


class PowerBIExportRenderer:
    def __init__(
        self,
        config: CloudConfig,
        token_provider: EntraTokenProvider | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.tokens = token_provider or EntraTokenProvider(config)
        self.client = client or httpx.Client(timeout=config.timeout_seconds)
        self.sleep = sleep

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tokens.token_for(POWERBI_SCOPE)}",
            "Content-Type": "application/json",
        }

    def render_report(
        self,
        report_id: str,
        output_path: str | Path,
        page_names: list[str] | None = None,
        locale: str = "en-US",
    ) -> RenderResult:
        output = Path(output_path).resolve()
        output.mkdir(parents=True, exist_ok=True)
        base_url = (
            f"{POWERBI_API}/groups/{self.config.workspace_id}/reports/{report_id}"
        )
        configuration: dict[str, Any] = {
            "settings": {"locale": locale, "includeHiddenPages": False}
        }
        if page_names:
            configuration["pages"] = [{"pageName": name} for name in page_names]
        response = self.client.post(
            f"{base_url}/ExportTo",
            headers=self._headers(),
            json={"format": "PNG", "powerBIReportConfiguration": configuration},
        )
        _ensure_success(response, "start Power BI PNG export")
        export_id = str(_response_json(response).get("id", ""))
        if not export_id:
            raise CloudAPIError("Power BI export response did not include an export id")

        status_url = f"{base_url}/exports/{export_id}"
        deadline = time.monotonic() + self.config.timeout_seconds
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            status_response = self.client.get(status_url, headers=self._headers())
            _ensure_success(status_response, "poll Power BI PNG export")
            status = _response_json(status_response)
            state = status.get("status")
            if state == "Succeeded":
                break
            if state == "Failed":
                raise CloudAPIError(f"Power BI export {export_id} failed")
            self.sleep(_safe_retry_after(status_response, self.config.poll_interval_seconds))
        else:
            raise TimeoutError(f"Power BI export {export_id} exceeded the configured timeout")

        file_response = self.client.get(
            f"{status_url}/file",
            headers={"Authorization": self._headers()["Authorization"]},
        )
        _ensure_success(file_response, "download Power BI PNG export")
        artifacts: list[str] = []
        if file_response.content.startswith(b"PK"):
            archive = output / f"{report_id}-{export_id}.zip"
            archive.write_bytes(file_response.content)
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (output / member.filename).resolve()
                    try:
                        target.relative_to(output)
                    except ValueError as exc:
                        raise CloudAPIError("Power BI export contained an unsafe ZIP path") from exc
                    if member.is_dir():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bundle.read(member))
                    if target.suffix.lower() == ".png":
                        artifacts.append(str(target))
        else:
            image = output / f"{report_id}-{export_id}.png"
            image.write_bytes(file_response.content)
            artifacts.append(str(image))
        if not artifacts:
            raise CloudAPIError("Power BI export completed but contained no PNG artifacts")
        return RenderResult(
            provider="powerbi-export-to-file",
            artifacts=artifacts,
            warnings=[],
            metadata={
                "workspace_id": self.config.workspace_id,
                "report_id": report_id,
                "export_id": export_id,
                "percent_complete": status.get("percentComplete", 100),
            },
        )
