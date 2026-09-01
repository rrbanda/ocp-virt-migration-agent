"""OpenAI-compatible /chat/completions API for the migration agent.

Provides a standard contract that the RHOAI eval harness, EvalHub, and
behavioral tests can target.  Runs alongside (or instead of) the ADK
built-in ``api_server``.

Start with::

    uvicorn app.api:app --host 0.0.0.0 --port 8080

Uses the ADK ``App`` wrapper so plugins and EventsCompactionConfig are
active on this code path as well.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from os import getenv
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from google.genai import types
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

USER_ID = getenv("API_USER_ID", "api_user")
_REQUEST_TIMEOUT = int(getenv("API_REQUEST_TIMEOUT", "300"))
_runner = None
_run_config = None


# ---------------------------------------------------------------------------
# Pydantic models (OpenAI-compatible contract)
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False
    session_id: str | None = None
    resume_tool_call_id: str | None = None


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int
    message: ChoiceMessage
    finish_reason: str


class PendingAction(BaseModel):
    """HITL interrupt details -- present when the workflow paused for human input."""

    type: str = "human_approval"
    interrupt_id: str
    message: str
    tool_call_id: str = ""


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    session_id: str | None = None
    pending_action: PendingAction | None = None
    context: list[dict] | None = None
    usage: dict | None = None


class HealthResponse(BaseModel):
    status: str
    agent_initialized: bool


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _runner, _run_config

    from google.adk.runners import InMemoryRunner

    from .agent import app as adk_app
    from .agent import default_run_config

    _runner = InMemoryRunner(app=adk_app)
    _run_config = default_run_config
    log.info("OpenAI-compatible API ready (app: %s)", adk_app.name)
    yield
    _runner = None
    _run_config = None


fastapi_app = FastAPI(
    title="Migration Agent API",
    description="OpenAI-compatible chat completions endpoint for the OCP Virt migration agent.",
    lifespan=lifespan,
)
app = fastapi_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _last_user_message(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    raise HTTPException(status_code=400, detail="No user message found")


# ---------------------------------------------------------------------------
# POST /chat/completions
# ---------------------------------------------------------------------------
@fastapi_app.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    if _runner is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    user_text = _last_user_message(request.messages)
    model_id = request.model or getenv("ADK_MODEL", "model")

    if request.stream:
        return await _stream(user_text, model_id, request.session_id)
    return await _non_stream(user_text, model_id, request.session_id, request.resume_tool_call_id)


async def _non_stream(
    user_text: str, model_id: str, session_id: str | None = None, resume_tool_call_id: str | None = None
) -> dict[str, Any]:
    try:
        if session_id:
            try:
                await _runner.session_service.get_session(
                    app_name=_runner.app_name,
                    user_id=USER_ID,
                    session_id=session_id,
                )
            except Exception:
                session_id = None

        if not session_id:
            session = await _runner.session_service.create_session(
                app_name=_runner.app_name,
                user_id=USER_ID,
            )
            session_id = session.id

        if resume_tool_call_id:
            msg = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=resume_tool_call_id,
                            name="adk_request_input",
                            response={"result": user_text},
                        )
                    )
                ],
            )
        else:
            msg = types.Content(role="user", parts=[types.Part.from_text(text=user_text)])

        all_text_parts: list[str] = []
        context: list[dict] = []
        pending_action: dict | None = None

        async def _run():
            nonlocal all_text_parts, pending_action
            async for event in _runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=msg,
                run_config=_run_config,
            ):
                if not event.content or not event.content.parts:
                    continue
                for part in event.content.parts:
                    if part.function_call:
                        fc_name = part.function_call.name
                        fc_args = dict(part.function_call.args) if part.function_call.args else {}
                        fc_id = part.function_call.id or ""
                        if fc_name == "adk_request_input":
                            pending_action = {
                                "type": "human_approval",
                                "interrupt_id": fc_args.get("interruptId", ""),
                                "message": fc_args.get("message", ""),
                                "tool_call_id": fc_id,
                            }
                        context.append(
                            {
                                "role": "assistant",
                                "content": f"Calling tool: {fc_name}",
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": fc_name,
                                            "arguments": json.dumps(fc_args),
                                        },
                                        "id": fc_id,
                                    }
                                ],
                            }
                        )
                    elif part.function_response:
                        context.append(
                            {
                                "role": "tool",
                                "name": part.function_response.name,
                                "content": json.dumps(
                                    dict(part.function_response.response) if part.function_response.response else {}
                                ),
                            }
                        )
                    elif part.text:
                        role = event.content.role or "model"
                        context.append(
                            {
                                "role": "assistant" if role == "model" else role,
                                "content": part.text,
                            }
                        )
                        if role == "model":
                            all_text_parts.append(part.text)

        await asyncio.wait_for(_run(), timeout=_REQUEST_TIMEOUT)

        final_text = "\n\n".join(all_text_parts) if all_text_parts else ""
        finish_reason = "requires_action" if pending_action else "stop"

        return {
            "id": _completion_id(),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": final_text},
                    "finish_reason": finish_reason,
                }
            ],
            "session_id": session_id,
            "pending_action": pending_action,
            "context": context,
            "usage": None,
        }
    except TimeoutError:
        log.error("Chat completion timed out after %ds", _REQUEST_TIMEOUT)
        raise HTTPException(status_code=504, detail=f"Request timed out after {_REQUEST_TIMEOUT}s")
    except Exception:
        log.exception("Error in chat completion")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _stream(user_text: str, model_id: str, session_id: str | None = None) -> StreamingResponse:
    cid = _completion_id()
    created = int(time.time())

    async def generate() -> AsyncIterator[str]:
        try:
            sid = session_id
            if sid:
                try:
                    await _runner.session_service.get_session(
                        app_name=_runner.app_name,
                        user_id=USER_ID,
                        session_id=sid,
                    )
                except Exception:
                    sid = None

            if not sid:
                session = await _runner.session_service.create_session(
                    app_name=_runner.app_name,
                    user_id=USER_ID,
                )
                sid = session.id

            msg = types.Content(role="user", parts=[types.Part.from_text(text=user_text)])

            async for event in _runner.run_async(
                user_id=USER_ID,
                session_id=sid,
                new_message=msg,
                run_config=_run_config,
            ):
                if not event.content or not event.content.parts:
                    continue
                for part in event.content.parts:
                    text = part.text if part.text else None
                    if not text:
                        continue
                    chunk = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_id,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": text},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

            done_chunk = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "session_id": sid,
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            log.exception("Error in streaming completion")
            error = {"error": {"message": "Internal server error", "type": "server_error"}}
            yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@fastapi_app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "healthy", "agent_initialized": _runner is not None}
