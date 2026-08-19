from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VisualReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: str
    visual: str | None = None
    severity: Literal["error", "warning", "suggestion"]
    category: Literal[
        "render_failure", "layout", "readability", "data", "formatting",
        "accessibility", "interaction", "other",
    ]
    problem: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)


class VisualReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    summary: str
    issues: list[VisualReviewIssue] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class VisualQADecision(BaseModel):
    approved: bool
    should_revise: bool
    attempt: int
    max_attempts: int
    blocking_issue_count: int
    reason: str


def build_visual_review_prompt(manifest: dict[str, Any]) -> str:
    return """You are reviewing screenshots of a rendered Microsoft Power BI report.
Assess only what is visibly supported by the screenshots. Check for render failures,
clipping, overlap, poor hierarchy, unreadable labels, excessive whitespace, inconsistent
formatting, empty or suspicious visuals, and basic accessibility. Do not invent data or
interaction failures that cannot be observed. Match screenshots to this manifest:

{manifest}

Return only JSON with this exact shape:
{{
  "approved": true,
  "summary": "short overall assessment",
  "issues": [
    {{
      "page": "page display name",
      "visual": "visual title or null",
      "severity": "error|warning|suggestion",
      "category": "render_failure|layout|readability|data|formatting|accessibility|interaction|other",
      "problem": "visible problem",
      "recommendation": "specific DashboardSpec-level correction",
      "confidence": 0.0
    }}
  ]
}}

Set approved=false when any error exists or when warnings materially harm usability.
""".format(manifest=json.dumps(manifest, indent=2))


def _clean_json_response(value: str) -> dict[str, Any]:
    text = value.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("visual reviewer must return a JSON object")
    # Vision models occasionally use a more specific category (for example
    # ``clipping``) than the stable review schema. Normalize known aliases and
    # safely bucket any future labels instead of dropping an otherwise useful
    # visual review on Pydantic validation.
    allowed_categories = {
        "render_failure", "layout", "readability", "data", "formatting",
        "accessibility", "interaction", "other",
    }
    category_aliases = {
        "clipping": "readability",
        "whitespace": "layout",
        "trend": "data",
    }
    issues = payload.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict):
                category = str(issue.get("category", "other")).strip().lower()
                issue["category"] = category_aliases.get(
                    category, category if category in allowed_categories else "other"
                )
    return payload


def _image_payloads(image_paths: list[str | Path]) -> list[tuple[str, bytes]]:
    if not image_paths:
        raise ValueError("at least one rendered image is required")
    if len(image_paths) > 20:
        raise ValueError("visual review is limited to 20 report pages per request")
    images: list[tuple[str, bytes]] = []
    for value in image_paths:
        path = Path(value).resolve()
        suffix = path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"unsupported review image type: {path.name}")
        data = path.read_bytes()
        if len(data) > 20 * 1024 * 1024:
            raise ValueError(f"review image exceeds 20 MB: {path.name}")
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix[1:]}"
        images.append((mime, data))
    return images


def review_rendered_report(
    image_paths: list[str | Path],
    manifest: dict[str, Any],
    provider: str | None = None,
    model: str | None = None,
) -> VisualReview:
    """Send rendered report pages to the configured multimodal model."""
    selected_provider = (
        provider
        or os.getenv("POWERBI_VISION_PROVIDER")
        or os.getenv("LLM_PROVIDER", "gemini")
    ).lower()
    selected_model = model or os.getenv("POWERBI_VISION_MODEL") or os.getenv("LLM_MODEL", "")
    if not selected_model:
        raise ValueError("POWERBI_VISION_MODEL or LLM_MODEL must be configured")
    prompt = build_visual_review_prompt(manifest)
    images = _image_payloads(image_paths)

    if selected_provider == "openai":
        from openai import OpenAI

        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI visual review")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for mime, data in images:
            encoded = base64.b64encode(data).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            })
        response = OpenAI(api_key=key).chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
    elif selected_provider == "anthropic":
        from anthropic import Anthropic

        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic visual review")
        content = [{"type": "text", "text": prompt}]
        for mime, data in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": base64.b64encode(data).decode("ascii"),
                },
            })
        response = Anthropic(api_key=key).messages.create(
            model=selected_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
    elif selected_provider == "gemini":
        from google import genai
        from google.genai import types

        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini visual review")
        contents: list[Any] = [prompt]
        contents.extend(
            types.Part.from_bytes(data=data, mime_type=mime) for mime, data in images
        )
        # Keep the client alive for the whole request. Creating it inline can let
        # its finalizer close the underlying httpx client before the transport
        # finishes sending the multimodal request.
        client = genai.Client(api_key=key)
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            raw = response.text or ""
        finally:
            client.close()
    else:
        raise ValueError(f"unsupported visual review provider: {selected_provider}")

    return VisualReview.model_validate(_clean_json_response(raw))


def decide_visual_qa_iteration(
    review: VisualReview,
    attempt: int,
    max_attempts: int = 3,
) -> VisualQADecision:
    if attempt < 1 or max_attempts < 1 or attempt > max_attempts:
        raise ValueError("attempt must be between 1 and max_attempts")
    blocking = sum(item.severity == "error" for item in review.issues)
    approved = review.approved and blocking == 0
    should_revise = not approved and attempt < max_attempts
    if approved:
        reason = "visual review approved the rendered report"
    elif should_revise:
        reason = "visual issues remain and another bounded revision is allowed"
    else:
        reason = "visual issues remain but the maximum revision count was reached"
    return VisualQADecision(
        approved=approved,
        should_revise=should_revise,
        attempt=attempt,
        max_attempts=max_attempts,
        blocking_issue_count=blocking,
        reason=reason,
    )
