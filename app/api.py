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
from fastapi.responses import HTMLResponse, StreamingResponse
from google.genai import types
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

USER_ID = getenv("API_USER_ID", "api_user")
_REQUEST_TIMEOUT = int(getenv("API_REQUEST_TIMEOUT", "600"))
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
        return await _stream(user_text, model_id, request.session_id, request.resume_tool_call_id)
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
        seen_texts: set[str] = set()
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
                            sig = part.text.strip()[:200]
                            if sig not in seen_texts:
                                seen_texts.add(sig)
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


async def _stream(
    user_text: str, model_id: str, session_id: str | None = None, resume_tool_call_id: str | None = None
) -> StreamingResponse:
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

            seen_texts: set[str] = set()
            pending_hitl: dict | None = None

            async for event in _runner.run_async(
                user_id=USER_ID,
                session_id=sid,
                new_message=msg,
                run_config=_run_config,
            ):
                if not event.content or not event.content.parts:
                    continue
                for part in event.content.parts:
                    if part.function_call:
                        fc_name = part.function_call.name
                        fc_id = part.function_call.id or ""
                        fc_args = dict(part.function_call.args) if part.function_call.args else {}

                        if fc_name == "adk_request_input":
                            hitl_msg = fc_args.get("message", "Approval required. Please respond yes or no.")
                            pending_hitl = {
                                "type": "human_approval",
                                "interrupt_id": fc_args.get("interruptId", fc_id),
                                "message": hitl_msg,
                                "tool_call_id": fc_id,
                            }
                            question_chunk = {
                                "id": cid,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model_id,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {
                                            "role": "assistant",
                                            "content": f"\n\n**[Approval Required]** {hitl_msg}\n\n",
                                        },
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(question_chunk)}\n\n"
                        else:
                            status_text = f"\n\n**[Tool: {fc_name}]** Running...\n\n"
                            chunk = {
                                "id": cid,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model_id,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"role": "assistant", "content": status_text},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                    elif part.text:
                        sig = part.text.strip()[:200]
                        if sig in seen_texts:
                            continue
                        seen_texts.add(sig)
                        chunk = {
                            "id": cid,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": part.text},
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
                "choices": [{"index": 0, "delta": {}, "finish_reason": "requires_action" if pending_hitl else "stop"}],
                "session_id": sid,
                "pending_action": pending_hitl,
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            log.exception("Error in streaming completion")
            error = {"error": {"message": "Internal server error", "type": "server_error"}}
            yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /ui  — browser chat interface
# ---------------------------------------------------------------------------
_UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OCP Virt Migration Agent</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0f1117; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }
  header { background: #1a1d27; border-bottom: 1px solid #2d3148; padding: 12px 20px;
           display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
  header h1 { font-size: 16px; font-weight: 600; color: #e2e8f0; }
  header .badge { font-size: 11px; padding: 2px 8px; border-radius: 12px;
                  background: #22c55e22; color: #22c55e; border: 1px solid #22c55e44; }
  header .badge.warn { background: #f59e0b22; color: #f59e0b; border-color: #f59e0b44; }
  #sid-display { margin-left: auto; font-size: 11px; color: #64748b; font-family: monospace; }
  #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 75%; line-height: 1.55; }
  .msg.user { align-self: flex-end; background: #1e40af; color: #eff6ff;
              padding: 10px 14px; border-radius: 16px 16px 4px 16px; font-size: 14px; }
  .msg.assistant { align-self: flex-start; background: #1e293b; color: #e2e8f0;
                   padding: 12px 16px; border-radius: 4px 16px 16px 16px; font-size: 14px;
                   border: 1px solid #2d3a52; white-space: pre-wrap; }
  .msg.tool { align-self: flex-start; font-size: 12px; color: #94a3b8;
              font-family: monospace; padding: 4px 10px; }
  .msg.hitl { align-self: flex-start; background: #1c1a05; border: 1px solid #ca8a04;
              border-radius: 10px; padding: 14px 18px; max-width: 85%; }
  .msg.hitl .hitl-title { color: #fbbf24; font-weight: 600; font-size: 13px; margin-bottom: 8px; }
  .msg.hitl .hitl-body { color: #e2e8f0; font-size: 14px; margin-bottom: 14px; line-height: 1.5; }
  .msg.hitl .hitl-actions { display: flex; gap: 10px; }
  .btn-approve { background: #16a34a; color: #fff; border: none; border-radius: 8px;
                 padding: 8px 18px; cursor: pointer; font-size: 13px; font-weight: 600; }
  .btn-approve:hover { background: #15803d; }
  .btn-decline { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b;
                 border-radius: 8px; padding: 8px 18px; cursor: pointer; font-size: 13px; }
  .btn-decline:hover { background: #991b1b; }
  .typing { align-self: flex-start; color: #64748b; font-size: 13px; font-style: italic; padding: 4px 0; }
  #footer { background: #1a1d27; border-top: 1px solid #2d3148; padding: 14px 20px;
            display: flex; gap: 10px; flex-shrink: 0; }
  #input { flex: 1; background: #0f1117; border: 1px solid #2d3a52; border-radius: 10px;
           color: #e2e8f0; font-size: 14px; padding: 10px 14px; resize: none;
           outline: none; line-height: 1.5; max-height: 120px; min-height: 42px; }
  #input:focus { border-color: #3b82f6; }
  #send-btn { background: #2563eb; color: #fff; border: none; border-radius: 10px;
              padding: 10px 20px; cursor: pointer; font-size: 14px; font-weight: 600;
              align-self: flex-end; }
  #send-btn:disabled { background: #1e3a6e; color: #64748b; cursor: not-allowed; }
  #send-btn:hover:not(:disabled) { background: #1d4ed8; }
  code { background: #0f172a; padding: 1px 5px; border-radius: 4px; font-family: monospace; font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>OCP Virt Migration Agent</h1>
  <span id="status-badge" class="badge warn">initializing…</span>
  <span id="sid-display"></span>
</header>
<div id="chat"></div>
<div id="footer">
  <textarea id="input" rows="1" placeholder="Ask the agent… (Shift+Enter for newline)"></textarea>
  <button id="send-btn" disabled>Send</button>
</div>
<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const badge = document.getElementById('status-badge');
const sidDisplay = document.getElementById('sid-display');

let sessionId = null;
let pendingHITL = null;   // { interrupt_id, tool_call_id, message }
let streaming = false;

async function checkHealth() {
  try {
    const r = await fetch('/health');
    const d = await r.json();
    if (d.agent_initialized) {
      badge.textContent = 'ready';
      badge.className = 'badge';
      sendBtn.disabled = false;
    } else {
      badge.textContent = 'not ready';
      badge.className = 'badge warn';
      setTimeout(checkHealth, 3000);
    }
  } catch { setTimeout(checkHealth, 3000); }
}

function addMsg(cls, html) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.innerHTML = html;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function renderMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\n/g,'<br>');
}

function showHITL(pa) {
  pendingHITL = pa;
  sendBtn.disabled = true;
  input.disabled = true;
  const div = addMsg('hitl', `
    <div class="hitl-title">⚠ Approval Required</div>
    <div class="hitl-body">${renderMarkdown(pa.message)}</div>
    <div class="hitl-actions">
      <button class="btn-approve" onclick="resumeHITL('yes, proceed with migration')">Approve</button>
      <button class="btn-decline" onclick="resumeHITL('no, cancel migration')">Decline</button>
    </div>
  `);
}

async function resumeHITL(answer) {
  const pa = pendingHITL;
  pendingHITL = null;
  input.disabled = false;
  // Remove HITL card
  const hitlCard = chat.querySelector('.msg.hitl');
  if (hitlCard) hitlCard.remove();
  addMsg('user', renderMarkdown(answer));
  await sendToAPI(answer, pa.tool_call_id);
}

async function sendToAPI(text, resumeId) {
  streaming = true;
  sendBtn.disabled = true;
  const typingEl = addMsg('typing', 'Agent is thinking…');

  try {
    const body = {
      messages: [{ role: 'user', content: text }],
      stream: true,
      model: 'openai/gemini-2.5-flash',
    };
    if (sessionId) body.session_id = sessionId;
    if (resumeId) body.resume_tool_call_id = resumeId;

    const resp = await fetch('/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      typingEl.remove();
      addMsg('tool', `Error ${resp.status}: ${await resp.text()}`);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let assistantDiv = null;
    let assistantText = '';

    typingEl.remove();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') continue;
        let chunk;
        try { chunk = JSON.parse(data); } catch { continue; }

        // Extract session_id from any chunk that has it
        if (chunk.session_id && !sessionId) {
          sessionId = chunk.session_id;
          sidDisplay.textContent = 'session: ' + sessionId.slice(0, 8) + '…';
        }
        if (chunk.session_id) sessionId = chunk.session_id;

        const choice = chunk.choices?.[0];
        if (!choice) continue;

        const content = choice.delta?.content;
        const finishReason = choice.finish_reason;

        if (content) {
          // Separate tool-status lines from assistant text
          if (content.includes('[Tool:') || content.includes('[Approval Required]')) {
            // Show as a tool status line, don't accumulate into assistant bubble
            addMsg('tool', renderMarkdown(content.trim()));
          } else {
            if (!assistantDiv) {
              assistantDiv = addMsg('assistant', '');
              assistantText = '';
            }
            assistantText += content;
            assistantDiv.innerHTML = renderMarkdown(assistantText);
            chat.scrollTop = chat.scrollHeight;
          }
        }

        if (finishReason === 'requires_action' && chunk.pending_action) {
          showHITL(chunk.pending_action);
        } else if (finishReason === 'stop' || finishReason) {
          if (!pendingHITL) {
            sendBtn.disabled = false;
            input.focus();
          }
        }
      }
    }
  } catch (e) {
    addMsg('tool', 'Connection error: ' + e.message);
  } finally {
    streaming = false;
    if (!pendingHITL) sendBtn.disabled = false;
  }
}

async function send() {
  const text = input.value.trim();
  if (!text || streaming || pendingHITL) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg('user', renderMarkdown(text));
  await sendToAPI(text, null);
}

sendBtn.addEventListener('click', send);
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

checkHealth();
</script>
</body>
</html>"""


@fastapi_app.get("/ui", response_class=HTMLResponse)
async def chat_ui():
    return HTMLResponse(content=_UI_HTML)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@fastapi_app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "healthy", "agent_initialized": _runner is not None}
