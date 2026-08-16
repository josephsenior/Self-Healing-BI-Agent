"""Provider-neutral LangChain chat-model factory."""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def create_chat_model(
    *,
    provider: str,
    model: str,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    reasoning_effort: str | None = None,
) -> BaseChatModel:
    """Create one LangChain model adapter without leaking provider logic upstream."""
    normalized = provider.strip().lower()

    if normalized == "openai":
        from langchain_openai import ChatOpenAI

        options: dict[str, Any] = {
            "model": model,
            "api_key": openai_api_key or None,
            "max_retries": 2,
        }
        if reasoning_effort and reasoning_effort != "off":
            options["reasoning_effort"] = reasoning_effort
        return ChatOpenAI(**options)

    if normalized == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=anthropic_api_key or None,
            max_tokens=4096,
            max_retries=2,
        )

    if normalized in {"gemini", "google"}:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=gemini_api_key or None,
            max_retries=2,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")