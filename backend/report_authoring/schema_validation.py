from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jsonschema import RefResolver
from jsonschema.exceptions import RefResolutionError, SchemaError
from jsonschema.validators import validator_for

SCHEMA_PREFIX = "https://developer.microsoft.com/json-schemas/fabric/"


@dataclass(frozen=True)
class SchemaIssue:
    severity: str
    code: str
    message: str
    path: str = ""
    json_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfficialSchemaStore:
    def __init__(self, cache_root: str | Path, allow_network: bool = False):
        self.cache_root = Path(cache_root).resolve()
        self.allow_network = allow_network

    def _normalized_url(self, uri: str) -> str:
        url = urllib.parse.urldefrag(uri).url
        # Microsoft publishes schema-embedded.json with a dotted internal $id.
        url = url.replace("/schema.embedded.json", "/schema-embedded.json")
        if not url.startswith(SCHEMA_PREFIX):
            raise ValueError(f"schema URL is outside the Microsoft Fabric allowlist: {url}")
        return url

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_root / f"{digest}.json"

    def load(self, uri: str) -> dict[str, Any]:
        url = self._normalized_url(uri)
        cache_path = self._cache_path(url)
        if cache_path.is_file():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        if not self.allow_network:
            raise FileNotFoundError(f"schema is not cached: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "PowerBI-PBIR-Validator/1.0"})
        try:
            response_context = urllib.request.urlopen(request, timeout=20)
        except OSError as exc:
            raise OSError(f"failed to download {url}: {exc}") from exc
        with response_context as response:
            document = json.loads(response.read().decode("utf-8"))
        self.cache_root.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temporary.replace(cache_path)
        return document


def validate_json_document(
    document: dict[str, Any],
    *,
    path: str = "",
    cache_root: str | Path,
    allow_network: bool = False,
) -> list[SchemaIssue]:
    schema_uri = document.get("$schema")
    if not isinstance(schema_uri, str):
        return [SchemaIssue("error", "missing_schema", "$schema is missing", path)]

    store = OfficialSchemaStore(cache_root, allow_network)
    try:
        schema = store.load(schema_uri)
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        resolver = RefResolver(
            base_uri=schema_uri,
            referrer=schema,
            handlers={"https": store.load},
        )
        validator = validator_class(schema, resolver=resolver)
        return [
            SchemaIssue(
                "error",
                "schema_violation",
                error.message,
                path,
                "/".join(str(item) for item in error.absolute_path),
            )
            for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
        ]
    except (OSError, ValueError, json.JSONDecodeError, RefResolutionError, SchemaError) as exc:
        return [SchemaIssue("error", "schema_unavailable", str(exc), path)]
