"""Serializable LangGraph state owned by one conversation thread."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Durable state; external clients and sessions never belong here."""

    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str
    thread_id: str
    last_error: str | None
    artifacts: list[dict[str, Any]]
