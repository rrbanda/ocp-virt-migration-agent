"""Unit tests for the OpenAI-compatible FastAPI endpoint."""

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
