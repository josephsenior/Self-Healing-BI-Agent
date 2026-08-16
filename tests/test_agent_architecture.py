import asyncio
import unittest
from types import SimpleNamespace

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.application.graph_agent import _provider_safe_context, stream_agent_graph
from backend.infrastructure.redis_state import AgentStateRuntime


class FakeMCPModel:
    def __init__(self):
        self.calls = []
        self.tool_schemas = []

    def bind_tools(self, tools):
        self.tool_schemas = tools
        return self

    async def astream(self, messages):
        self.calls.append(messages)
        if len(self.calls) == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "echo_tool",
                        "args": '{"value":"hello"}',
                        "id": "call-1",
                        "index": 0,
                    }
                ],
            )
        else:
            yield AIMessageChunk(content="Verified answer")


class FakeMCPSession:
    def __init__(self):
        self.calls = []
        self.tool = SimpleNamespace(
            name="echo_tool",
            description="Echo a value",
            inputSchema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        )

    async def list_tools(self):
        return SimpleNamespace(tools=[self.tool])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=arguments["value"])]
        )


class AgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    def test_context_compaction_keeps_tool_cycles_and_user_boundary(self):
        messages = [HumanMessage(content="old")]
        messages.extend(AIMessage(content=f"old-{index}") for index in range(6))
        messages.append(HumanMessage(content="active"))
        messages.append(AIMessage(content="", tool_calls=[{
            "name": "echo_tool", "args": {"value": "ok"}, "id": "call-ok"
        }]))
        messages.append(ToolMessage(content="ok", tool_call_id="call-ok"))

        compacted = _provider_safe_context(messages, max_messages=3)

        self.assertIsInstance(compacted[0], HumanMessage)
        self.assertEqual(compacted[0].content, "active")
        self.assertEqual([type(item) for item in compacted[1:]], [AIMessage, ToolMessage])

    def test_context_compaction_drops_incomplete_tool_cycles(self):
        incomplete = AIMessage(content="", tool_calls=[{
            "name": "echo_tool", "args": {"value": "lost"}, "id": "call-lost"
        }])
        messages = [
            HumanMessage(content="first"),
            incomplete,
            AIMessage(content="stopped before execution"),
            HumanMessage(content="next"),
        ]

        compacted = _provider_safe_context(messages, max_messages=20)

        self.assertNotIn(incomplete, compacted)
        self.assertFalse(any(isinstance(item, ToolMessage) for item in compacted))

    async def test_langgraph_executes_existing_mcp_tool_and_streams_stable_events(self):
        model = FakeMCPModel()
        session = FakeMCPSession()
        events = []
        async for event in stream_agent_graph(
            query="echo hello",
            thread_id="thread-1",
            run_id="run-1",
            model=model,
            session=session,
            system_prompt="Test system prompt",
            checkpointer=InMemorySaver(),
        ):
            events.append(event)

        self.assertEqual(session.calls, [("echo_tool", {"value": "hello"})])
        self.assertEqual(model.tool_schemas[0]["function"]["name"], "echo_tool")
        self.assertTrue(any(event["type"] == "tool_start" for event in events))
        self.assertTrue(any(event["type"] == "tool_result" for event in events))
        self.assertEqual(
            "".join(event["text"] for event in events if event["type"] == "token"),
            "Verified answer",
        )

    async def test_memory_fallback_keeps_locks_run_scoped(self):
        runtime = AgentStateRuntime("", required=False)
        await runtime.start()
        self.assertEqual(runtime.backend, "memory")

        entered = asyncio.Event()
        release = asyncio.Event()

        async def first_run():
            async with runtime.run_lock("thread-a", wait_seconds=1):
                entered.set()
                await release.wait()

        task = asyncio.create_task(first_run())
        await entered.wait()
        with self.assertRaises(RuntimeError):
            async with runtime.run_lock("thread-a", wait_seconds=0):
                pass
        async with runtime.run_lock("thread-b", wait_seconds=1):
            pass
        release.set()
        await task


if __name__ == "__main__":
    unittest.main()
