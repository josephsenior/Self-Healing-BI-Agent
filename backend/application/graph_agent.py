"""Bounded LangGraph orchestration over the existing MCP tool services."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from urllib.parse import quote
from typing import Any, AsyncGenerator

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from backend.application.state import AgentState

logger = logging.getLogger("graph_agent")
_SENTINEL = object()


def _provider_safe_context(messages: list[Any], max_messages: int) -> list[Any]:
    """Return complete conversation turns without orphaned tool protocol messages.

    Checkpoint history can contain an incomplete tool cycle when an older run was
    cancelled or stopped by the former iteration budget. Gemini rejects any
    function call that is not followed by all matching function responses. A
    blind tail slice can also separate a ToolMessage from its AIMessage. Remove
    incomplete cycles first, then truncate only at a HumanMessage boundary.
    """
    sanitized: list[Any] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, AIMessage) and message.tool_calls:
            responses: list[ToolMessage] = []
            cursor = index + 1
            while cursor < len(messages) and isinstance(messages[cursor], ToolMessage):
                responses.append(messages[cursor])
                cursor += 1
            expected = {
                str(call.get("id"))
                for call in message.tool_calls
                if call.get("id") is not None
            }
            received = {str(item.tool_call_id) for item in responses}
            if expected and expected.issubset(received):
                sanitized.append(message)
                sanitized.extend(responses)
            else:
                logger.warning(
                    "Dropping incomplete historical tool cycle: expected=%s received=%s",
                    sorted(expected),
                    sorted(received),
                )
            index = cursor
            continue
        if isinstance(message, ToolMessage):
            logger.warning("Dropping orphaned historical ToolMessage %s", message.tool_call_id)
            index += 1
            continue
        sanitized.append(message)
        index += 1

    if len(sanitized) <= max_messages:
        return sanitized

    cutoff = len(sanitized) - max_messages
    for boundary in range(cutoff, len(sanitized)):
        if isinstance(sanitized[boundary], HumanMessage):
            return sanitized[boundary:]

    # The active user turn alone exceeds the configured context window. Keep it
    # intact because cutting a function-call cycle produces an invalid request.
    for boundary in range(cutoff - 1, -1, -1):
        if isinstance(sanitized[boundary], HumanMessage):
            return sanitized[boundary:]
    return sanitized


def _tool_schema(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    pieces: list[str] = []
    for block in content:
        if isinstance(block, str):
            pieces.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
            pieces.append(str(block.get("text", "")))
    return "".join(pieces)


def _mcp_result_text(result: Any, max_chars: int) -> str:
    pieces: list[str] = []
    for item in getattr(result, "content", []) or []:
        if getattr(item, "type", None) == "text":
            pieces.append(str(item.text))
        else:
            pieces.append(f"[{getattr(item, 'type', 'unknown')} content]")
    text = "".join(pieces)
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n[tool result truncated; {omitted} characters omitted]"


def _extract_preview_images(result_text: str) -> list[str]:
    """Turn rendered PNG/JPEG paths inside a tool result into preview URLs.

    Only paths below the git-ignored artifact roots are eligible so the browser
    can never be pointed at arbitrary repository files.
    """
    try:
        payload = json.loads(result_text)
    except (ValueError, TypeError):
        return []

    markers = (".pbir-previews", ".dashboard-workspaces")
    images: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            lowered = node.lower()
            if not lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
                return
            normalized = node.replace("\\", "/")
            for marker in markers:
                if marker + "/" in normalized:
                    relative = normalized.split(marker + "/", 1)[-1]
                    rel_path = marker + "/" + relative
                    images.append(f"/api/preview?path={quote(rel_path, safe='')}")
                    return
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(payload)
    return list(dict.fromkeys(images))


async def discover_powerbi_context(session: Any, tool_names: set[str]) -> str:
    """Preserve the previous automatic local Power BI connection behavior."""
    if "connection_operations" not in tool_names:
        return ""
    try:
        response = await session.call_tool(
            "connection_operations", {"request": {"operation": "ListConnections"}}
        )
        data = json.loads(response.content[0].text)
        connections = data.get("data") if isinstance(data, dict) else data
        active = connections[0] if isinstance(connections, list) and connections else None

        if active is None:
            response = await session.call_tool(
                "connection_operations",
                {"request": {"operation": "ListLocalInstances"}},
            )
            data = json.loads(response.content[0].text)
            instances = data.get("data") if isinstance(data, dict) else data
            if isinstance(instances, list) and instances:
                connection_string = instances[0].get("connectionString")
                if connection_string:
                    await session.call_tool(
                        "connection_operations",
                        {
                            "request": {
                                "operation": "Connect",
                                "connectionString": connection_string,
                            }
                        },
                    )
                    response = await session.call_tool(
                        "connection_operations",
                        {"request": {"operation": "ListConnections"}},
                    )
                    data = json.loads(response.content[0].text)
                    connections = data.get("data") if isinstance(data, dict) else data
                    active = (
                        connections[0]
                        if isinstance(connections, list) and connections
                        else None
                    )

        if active:
            name = active.get("connectionName") or "Power BI model"
            return (
                "\n\n[Active Connection Status: CONNECTED]\n"
                f"- Connected instance: {name}\n"
                "- Use the existing connection directly."
            )
        return (
            "\n\n[Active Connection Status: DISCONNECTED]\n"
            "- No running local Power BI Desktop instance was detected."
        )
    except Exception as exc:
        logger.warning("Power BI environment discovery failed: %s", exc)
        return f"\n\n[Active Connection Status: UNKNOWN]\n- Discovery error: {exc}"


def build_agent_graph(
    *,
    model: BaseChatModel,
    session: Any,
    tools: list[Any],
    system_prompt: str,
    event_queue: asyncio.Queue[Any],
    checkpointer: Any,
    max_context_messages: int,
    max_tool_result_chars: int,
    tool_timeout_seconds: float,
) -> Any:
    """Build one provider-neutral graph around the existing MCP session."""
    bound_model = model.bind_tools([_tool_schema(tool) for tool in tools])

    async def call_model(state: AgentState) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        relevant = _provider_safe_context(messages, max_context_messages)
        prompt_messages = [SystemMessage(content=system_prompt), *relevant]
        combined: AIMessageChunk | None = None

        async for chunk in bound_model.astream(prompt_messages):
            if not isinstance(chunk, AIMessageChunk):
                continue
            combined = chunk if combined is None else combined + chunk
            text = _content_text(chunk.content)
            if text:
                await event_queue.put({"type": "token", "text": text})

        if combined is None:
            response = await bound_model.ainvoke(prompt_messages)
            text = _content_text(response.content)
            if text:
                await event_queue.put({"type": "token", "text": text})
            return {"messages": [response]}

        return {
            "messages": [
                AIMessage(
                    content=combined.content,
                    additional_kwargs=combined.additional_kwargs,
                    response_metadata=combined.response_metadata,
                    tool_calls=combined.tool_calls,
                    invalid_tool_calls=combined.invalid_tool_calls,
                    id=combined.id,
                )
            ]
        }

    async def call_tools(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        calls = list(getattr(last, "tool_calls", None) or [])
        payload = [
            {
                "id": call.get("id") or str(uuid.uuid4()),
                "name": call["name"],
                "arguments": call.get("args", {}),
            }
            for call in calls
        ]
        results: list[ToolMessage] = []
        for call, emitted in zip(calls, payload):
            name = call["name"]
            arguments = call.get("args", {})
            call_id = emitted["id"]
            # Calls execute sequentially because later mutations may depend on
            # earlier results. Announce only the call that is actually starting;
            # announcing the whole batch made queued calls look hung in the UI.
            await event_queue.put({"type": "tool_start", "calls": [emitted]})
            try:
                result = await asyncio.wait_for(
                    session.call_tool(name, arguments),
                    timeout=tool_timeout_seconds,
                )
                text = _mcp_result_text(result, max_tool_result_chars)
                await event_queue.put(
                    {
                        "type": "tool_result",
                        "id": call_id,
                        "name": name,
                        "result": text,
                        "images": _extract_preview_images(text),
                    }
                )
                results.append(
                    ToolMessage(content=text, tool_call_id=call_id, name=name)
                )
            except Exception as exc:
                error = str(exc)
                await event_queue.put(
                    {
                        "type": "tool_result",
                        "id": call_id,
                        "name": name,
                        "error": error,
                    }
                )
                results.append(
                    ToolMessage(
                        content=f"Error executing tool: {error}",
                        tool_call_id=call_id,
                        name=name,
                        status="error",
                    )
                )
        return {
            "messages": results,
        }

    def route_after_model(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        return "tools"

    builder = StateGraph(AgentState)
    builder.add_node("model", call_model)
    builder.add_node("tools", call_tools)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route_after_model)
    builder.add_edge("tools", "model")
    return builder.compile(checkpointer=checkpointer)


async def stream_agent_graph(
    *,
    query: str,
    thread_id: str,
    run_id: str,
    model: BaseChatModel,
    session: Any,
    system_prompt: str,
    checkpointer: Any,
    max_context_messages: int = 80,
    max_tool_result_chars: int = 50_000,
    tool_timeout_seconds: float = 120,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream the stable frontend event protocol while LangGraph owns execution."""
    tool_result = await session.list_tools()
    tools = list(tool_result.tools)
    tool_names = {tool.name for tool in tools}
    yield {
        "type": "tools_discovered",
        "tools": sorted(tool_names),
        "count": len(tool_names),
    }

    connection_context = await discover_powerbi_context(session, tool_names)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    graph = build_agent_graph(
        model=model,
        session=session,
        tools=tools,
        system_prompt=system_prompt + connection_context,
        event_queue=queue,
        checkpointer=checkpointer,
        max_context_messages=max_context_messages,
        max_tool_result_chars=max_tool_result_chars,
        tool_timeout_seconds=tool_timeout_seconds,
    )
    graph_config = {
        "configurable": {"thread_id": thread_id},
        # No application-level tool-iteration budget. This high engine guard
        # exists only to terminate a genuinely non-converging graph.
        "recursion_limit": 1000,
    }

    async def execute() -> None:
        try:
            await graph.ainvoke(
                {
                    "messages": [HumanMessage(content=query)],
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "last_error": None,
                },
                config=graph_config,
            )
        finally:
            await queue.put(_SENTINEL)

    task = asyncio.create_task(execute())
    try:
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield event
        await task
    except BaseException:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
