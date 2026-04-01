import json
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import os

from llama_stack_client import LlamaStackClient
from llama_stack_client import types as LlamaStackClientTypes

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8321")
MODEL_ID = "llama3.2:3b"
SYSTEM_PROMPT = "You are a helpful assistant."

SESSION_TTL = timedelta(hours=24)
CLEANUP_INTERVAL = 3600  # seconds
CLEAR_SESSIONS_ON_STARTUP = True

STATE_FILE = Path(os.environ.get("STATE_DIR", str(Path(__file__).parent))) / ".service_state.json"

agent_id: str | None = None
last_used: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# State persistence (agent_id + session IDs survive process restarts)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state():
    STATE_FILE.write_text(json.dumps({
        "agent_id": agent_id,
        "sessions": list(last_used.keys()),
    }))


# ---------------------------------------------------------------------------
# Background TTL cleanup
# ---------------------------------------------------------------------------

def _cleanup_loop():
    while True:
        threading.Event().wait(CLEANUP_INTERVAL)
        cutoff = datetime.now(timezone.utc) - SESSION_TTL
        stale = [sid for sid, ts in list(last_used.items()) if ts < cutoff]
        if stale:
            with LlamaStackClient(base_url=SERVER_URL) as client:
                for sid in stale:
                    try:
                        client.agents.session.delete(agent_id=agent_id, session_id=sid)
                    except Exception:
                        pass
                    last_used.pop(sid, None)
            _save_state()
            print(f"Cleaned up {len(stale)} stale session(s)")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_id

    state = _load_state()
    saved_agent_id = state.get("agent_id")
    saved_sessions: list[str] = state.get("sessions", [])

    with LlamaStackClient(base_url=SERVER_URL) as client:
        # Reuse existing agent if available, otherwise create a new one
        if saved_agent_id:
            agent_id = saved_agent_id
            print(f"Reusing agent: {agent_id}")
        else:
            agent: LlamaStackClientTypes.AgentCreateResponse = client.agents.create(
                agent_config={
                    "model": MODEL_ID,
                    "instructions": SYSTEM_PROMPT,
                }
            )
            agent_id = agent.agent_id
            print(f"Agent created: {agent_id}")

        if CLEAR_SESSIONS_ON_STARTUP and saved_sessions:
            for sid in saved_sessions:
                try:
                    client.agents.session.delete(agent_id=agent_id, session_id=sid)
                except Exception:
                    pass
            print(f"Cleared {len(saved_sessions)} session(s) from previous run")

    _save_state()

    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()

    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Gosipel Llama Chat Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    print(f"Validation error on {request.method} {request.url.path}: {errors}")
    return JSONResponse(status_code=422, content={"detail": "Validation error", "errors": errors})


class Message(BaseModel):
    role: str
    content: str
    stop_reason: str | None = None


class ChatRequest(BaseModel):
    messages: list[Message]
    session_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    stop_reason: str | None = None


def _iter_turn(session_id: str, messages: list):
    """Yields (text, stop_reason) per chunk from an agent turn."""
    with LlamaStackClient(base_url=SERVER_URL) as client:
        response = client.agents.turn.create(
            agent_id=agent_id,
            session_id=session_id,
            messages=messages,
            stream=True,
        )
        for chunk in response:
            payload = chunk.event.payload
            event_type = getattr(payload, "event_type", None)

            if event_type == "step_progress":
                text = getattr(payload.delta, "text", None) or None
                yield text, None

            elif event_type == "turn_complete":
                stop_reason = getattr(payload.turn.output_message, "stop_reason", None)
                yield None, stop_reason


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id

    if session_id is None:
        with LlamaStackClient(base_url=SERVER_URL) as client:
            session = client.agents.session.create(
                agent_id=agent_id,
                session_name=str(uuid.uuid4()),
            )
        session_id = session.session_id

    last_used[session_id] = datetime.now(timezone.utc)
    _save_state()

    messages = [msg.model_dump(exclude_none=True) for msg in req.messages]
    print(f"Session {session_id} | +{len(messages)} message(s)")

    try:
        if req.stream:
            def generate():
                yield f"data: {{\"session_id\": \"{session_id}\"}}\n\n"
                for text, sr in _iter_turn(session_id, messages):
                    if text:
                        yield f"data: {text}\n\n"
                    if sr:
                        yield f"data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        reply, stop_reason = "", None
        for text, sr in _iter_turn(session_id, messages):
            if text:
                reply += text
            if sr:
                stop_reason = sr

        return ChatResponse(session_id=session_id, reply=reply, stop_reason=stop_reason)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    with LlamaStackClient(base_url=SERVER_URL) as client:
        client.agents.session.delete(agent_id=agent_id, session_id=session_id)
    last_used.pop(session_id, None)
    _save_state()
    return {"status": "deleted", "session_id": session_id}


@app.get("/health")
def health():
    try:
        with LlamaStackClient(base_url=SERVER_URL) as client:
            models = [m.identifier for m in client.models.list()]
        return {"status": "ok", "agent_id": agent_id, "model_available": MODEL_ID in models}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    uvicorn.run("service:app", host="0.0.0.0", port=8000, reload=True)
