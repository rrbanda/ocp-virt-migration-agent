"""Unit tests for the OpenAI-compatible FastAPI endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_runner():
    runner = AsyncMock()
    runner.app_name = "migration_coordinator"

    session = MagicMock()
    session.id = "test-session-001"
    runner.session_service.create_session = AsyncMock(return_value=session)
    runner.session_service.get_session = AsyncMock(return_value=session)
    return runner


# ---------------------------------------------------------------------------
# Helpers for streaming tests
# ---------------------------------------------------------------------------


def _make_function_call_part(name: str, args: dict | None = None, fc_id: str | None = None):
    """Build a mock event part with a function_call."""
    part = MagicMock()
    part.text = None
    part.function_response = None
    fc = MagicMock()
    fc.name = name
    fc.id = fc_id or name
    fc.args = args or {}
    part.function_call = fc
    return part


def _make_text_part(text: str):
    """Build a mock event part with text."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    part.function_response = None
    return part


def _make_event(parts: list):
    """Wrap parts in a minimal mock ADK event."""
    event = MagicMock()
    event.content = MagicMock()
    event.content.parts = parts
    return event


async def _collect_sse_chunks(response) -> list[dict]:
    """Drain a StreamingResponse and return all parsed SSE data chunks."""
    chunks = []
    async for raw in response.body_iterator:
        text = raw.decode() if isinstance(raw, bytes) else raw
        for line in text.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunks.append(json.loads(line[6:]))
    return chunks


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_before_init(self):
        import app.api as api_mod

        original = api_mod._runner
        api_mod._runner = None
        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(transport=ASGITransport(app=api_mod.fastapi_app), base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                data = resp.json()
                assert data["agent_initialized"] is False
        finally:
            api_mod._runner = original


class TestChatCompletions:
    @pytest.mark.asyncio
    async def test_missing_user_message_returns_400(self):
        import app.api as api_mod

        api_mod._runner = MagicMock()
        api_mod._run_config = MagicMock()
        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(transport=ASGITransport(app=api_mod.fastapi_app), base_url="http://test") as client:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "messages": [{"role": "system", "content": "You are a bot"}],
                    },
                )
                assert resp.status_code == 400
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_503_when_not_initialized(self):
        import app.api as api_mod

        api_mod._runner = None
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=api_mod.fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 503


class TestResponseSchema:
    """Verify the response model includes session_id and pending_action fields."""

    def test_response_model_has_session_id(self):
        from app.api import ChatCompletionResponse

        fields = ChatCompletionResponse.model_fields
        assert "session_id" in fields
        assert "pending_action" in fields

    def test_pending_action_model(self):
        from app.api import PendingAction

        action = PendingAction(interrupt_id="migration_approval", message="Approve?")
        assert action.type == "human_approval"
        assert action.interrupt_id == "migration_approval"
        assert action.message == "Approve?"

    def test_response_with_pending_action(self):
        from app.api import ChatCompletionResponse, Choice, ChoiceMessage, PendingAction

        resp = ChatCompletionResponse(
            id="test-1",
            created=1000,
            model="test",
            choices=[Choice(index=0, message=ChoiceMessage(content="Plan created"), finish_reason="requires_action")],
            session_id="sess-123",
            pending_action=PendingAction(interrupt_id="migration_approval", message="Approve migration?"),
        )
        data = resp.model_dump()
        assert data["session_id"] == "sess-123"
        assert data["choices"][0]["finish_reason"] == "requires_action"
        assert data["pending_action"]["interrupt_id"] == "migration_approval"

    def test_response_without_pending_action(self):
        from app.api import ChatCompletionResponse, Choice, ChoiceMessage

        resp = ChatCompletionResponse(
            id="test-2",
            created=1000,
            model="test",
            choices=[Choice(index=0, message=ChoiceMessage(content="Hello"), finish_reason="stop")],
            session_id="sess-456",
        )
        data = resp.model_dump()
        assert data["session_id"] == "sess-456"
        assert data["pending_action"] is None
        assert data["choices"][0]["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# HITL streaming tests
# ---------------------------------------------------------------------------


class TestHITLStream:
    """Verify the streaming path surfaces HITL correctly and resumes properly.

    Root-cause context: before this fix, _stream() treated adk_request_input
    identically to every other tool call (showed "Running...") and always sent
    finish_reason=stop. The approval question was hidden from the user, and
    there was no pending_action / tool_call_id for the client to resume with.
    The user's next message therefore started a fresh workflow turn at the
    Coordinator instead of resuming the paused session.
    """

    @pytest.mark.asyncio
    async def test_adk_request_input_sets_requires_action(self, mock_runner):
        """done_chunk must have finish_reason=requires_action when HITL fires."""
        import app.api as api_mod

        hitl_part = _make_function_call_part(
            "adk_request_input",
            args={"message": "Do you approve?", "interruptId": "migration_approval"},
            fc_id="migration_approval",
        )

        async def fake_run(**kw):
            yield _make_event([hitl_part])

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("migrate database-user1", "test-model", "sess-1")
            chunks = await _collect_sse_chunks(response)
            done = chunks[-1]
            assert done["choices"][0]["finish_reason"] == "requires_action"
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_adk_request_input_populates_pending_action(self, mock_runner):
        """pending_action must carry interrupt_id, message, and tool_call_id."""
        import app.api as api_mod

        hitl_part = _make_function_call_part(
            "adk_request_input",
            args={"message": "Approve migration of database-user1?", "interruptId": "migration_approval"},
            fc_id="migration_approval",
        )

        async def fake_run(**kw):
            yield _make_event([hitl_part])

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("migrate database-user1", "test-model", "sess-1")
            chunks = await _collect_sse_chunks(response)
            done = chunks[-1]
            pa = done.get("pending_action")
            assert pa is not None, "pending_action must be present in done chunk"
            assert pa["type"] == "human_approval"
            assert pa["interrupt_id"] == "migration_approval"
            assert pa["tool_call_id"] == "migration_approval"
            assert "Approve migration" in pa["message"]
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_adk_request_input_streams_question_text(self, mock_runner):
        """The HITL approval question must appear as visible text in the stream."""
        import app.api as api_mod

        hitl_part = _make_function_call_part(
            "adk_request_input",
            args={"message": "Do you approve the migration?", "interruptId": "migration_approval"},
            fc_id="migration_approval",
        )

        async def fake_run(**kw):
            yield _make_event([hitl_part])

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("migrate database-user1", "test-model", "sess-1")
            chunks = await _collect_sse_chunks(response)
            # All streamed content (excluding the done chunk)
            content_chunks = [c for c in chunks if c["choices"][0]["delta"].get("content")]
            all_content = "".join(c["choices"][0]["delta"]["content"] for c in content_chunks)
            assert "Do you approve the migration?" in all_content
            assert "[Approval Required]" in all_content
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_normal_tool_call_still_shows_running(self, mock_runner):
        """Non-HITL tool calls still stream as '[Tool: X] Running...' with finish_reason=stop."""
        import app.api as api_mod

        tool_part = _make_function_call_part("list_vmware_vms", fc_id="call-123")

        async def fake_run(**kw):
            yield _make_event([tool_part])

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("list VMs", "test-model", "sess-1")
            chunks = await _collect_sse_chunks(response)
            done = chunks[-1]
            assert done["choices"][0]["finish_reason"] == "stop"
            assert done.get("pending_action") is None

            content_chunks = [c for c in chunks if c["choices"][0]["delta"].get("content")]
            all_content = "".join(c["choices"][0]["delta"]["content"] for c in content_chunks)
            assert "[Tool: list_vmware_vms]" in all_content
            assert "Running..." in all_content
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_resume_with_tool_call_id_sends_function_response(self, mock_runner):
        """When resume_tool_call_id is set, ADK must receive a FunctionResponse, not plain text.

        This is the core fix: 'yes' sent with the interrupt_id becomes a
        FunctionResponse that ADK routes back to the paused migration_approval
        node instead of restarting from START → Coordinator.
        """

        import app.api as api_mod

        captured_messages = []

        async def fake_run(*, new_message, **kw):
            captured_messages.append(new_message)
            return
            yield  # make it an async generator

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream(
                "yes",
                "test-model",
                session_id="sess-1",
                resume_tool_call_id="migration_approval",
            )
            # Drain to execute the generator
            await _collect_sse_chunks(response)

            assert len(captured_messages) == 1
            msg = captured_messages[0]
            assert len(msg.parts) == 1
            fr = msg.parts[0].function_response
            assert fr is not None, "message must contain a FunctionResponse, not plain text"
            assert fr.name == "adk_request_input"
            assert fr.id == "migration_approval"
            assert fr.response == {"result": "yes"}
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_no_resume_id_sends_plain_text(self, mock_runner):
        """Without resume_tool_call_id, the message is plain user text (normal turn)."""
        import app.api as api_mod

        captured_messages = []

        async def fake_run(*, new_message, **kw):
            captured_messages.append(new_message)
            return
            yield

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("list VMs", "test-model", session_id="sess-1")
            await _collect_sse_chunks(response)

            assert len(captured_messages) == 1
            msg = captured_messages[0]
            assert msg.parts[0].function_response is None
            assert msg.parts[0].text == "list VMs"
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_session_id_included_in_done_chunk(self, mock_runner):
        """session_id must always appear in the done chunk so the client can resume."""
        import app.api as api_mod

        async def fake_run(**kw):
            return
            yield

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            response = await api_mod._stream("hello", "test-model", session_id="my-session")
            chunks = await _collect_sse_chunks(response)
            done = chunks[-1]
            assert done.get("session_id") == "my-session"
        finally:
            api_mod._runner = None
            api_mod._run_config = None


# ---------------------------------------------------------------------------
# HITL non-stream resume test
# ---------------------------------------------------------------------------


class TestHITLNonStream:
    """Verify the non-streaming path already handles HITL resume correctly."""

    @pytest.mark.asyncio
    async def test_non_stream_resume_sends_function_response(self, mock_runner):
        """POST /chat/completions with resume_tool_call_id routes via FunctionResponse."""
        import app.api as api_mod

        captured_messages = []

        async def fake_run(*, new_message, **kw):
            captured_messages.append(new_message)
            # Yield nothing — simulates empty response after resume
            return
            yield

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(transport=ASGITransport(app=api_mod.fastapi_app), base_url="http://test") as client:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": "yes"}],
                        "stream": False,
                        "session_id": "sess-1",
                        "resume_tool_call_id": "migration_approval",
                    },
                )
            assert resp.status_code == 200
            assert len(captured_messages) == 1
            msg = captured_messages[0]
            fr = msg.parts[0].function_response
            assert fr is not None
            assert fr.name == "adk_request_input"
            assert fr.id == "migration_approval"
            assert fr.response == {"result": "yes"}
        finally:
            api_mod._runner = None
            api_mod._run_config = None

    @pytest.mark.asyncio
    async def test_non_stream_hitl_detection_sets_pending_action(self, mock_runner):
        """Non-stream path must detect adk_request_input and return pending_action."""
        import app.api as api_mod

        hitl_part = _make_function_call_part(
            "adk_request_input",
            args={"message": "Approve migration?", "interruptId": "migration_approval"},
            fc_id="migration_approval",
        )
        event = _make_event([hitl_part])
        event.content.role = "model"

        async def fake_run(**kw):
            yield event

        mock_runner.run_async = fake_run
        api_mod._runner = mock_runner
        api_mod._run_config = MagicMock()
        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(transport=ASGITransport(app=api_mod.fastapi_app), base_url="http://test") as client:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": "migrate database-user1"}],
                        "stream": False,
                        "session_id": "sess-1",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["finish_reason"] == "requires_action"
            pa = data.get("pending_action")
            assert pa is not None
            assert pa["interrupt_id"] == "migration_approval"
            assert pa["tool_call_id"] == "migration_approval"
            assert "Approve migration?" in pa["message"]
        finally:
            api_mod._runner = None
            api_mod._run_config = None
