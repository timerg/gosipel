from contextlib import asynccontextmanager
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import os

from llama_stack_client import LlamaStackClient

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8321")
MODEL_ID = "ollama/llama3.2:3b"
SYSTEM_PROMPT = (
    "You are a helpful Bible assistant. "
    "When the user asks about scripture, relevant KJV verses may be provided to you as context. "
    "Always quote those verses verbatim — never paraphrase, modernize, or alter the wording. "
    "If no relevant scripture is provided, say you don't know rather than making something up."
)

MANIFEST_PATH = Path("docs/.index_manifest.json")

_vector_store_id: str | None = None


def _load_vector_store_id() -> str | None:
    global _vector_store_id
    if _vector_store_id:
        return _vector_store_id
    if MANIFEST_PATH.exists():
        try:
            _vector_store_id = json.loads(MANIFEST_PATH.read_text()).get("vector_store_id")
        except Exception:
            pass
    return _vector_store_id


def _retrieve_context(query: str) -> str | None:
    vector_store_id = _load_vector_store_id()
    if not vector_store_id:
        return None
    with LlamaStackClient(base_url=SERVER_URL) as client:
        results = client.vector_io.query(
            vector_store_id=vector_store_id,
            query=query,
            params={"max_chunks": 5, "score_threshold": 0.3},
        )
    if not results.chunks:
        return None
    parts = [f"[{i+1}] {c.content}" for i, c in enumerate(results.chunks)]
    return "Relevant KJV scripture:\n\n" + "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
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


class ChatRequest(BaseModel):
    messages: list[Message]
    previous_response_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    response_id: str
    reply: str
    stop_reason: str | None = None


def _iter_response(messages: list, previous_response_id: str | None, instructions: str = SYSTEM_PROMPT):
    """Yields (text, stop_reason, response_id) per chunk from a streaming response."""
    with LlamaStackClient(base_url=SERVER_URL) as client:
        kwargs = dict(
            input=messages,
            model=MODEL_ID,
            instructions=instructions,
            stream=True,
        )
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id

        response_id = None
        for event in client.responses.create(**kwargs):

            # Capture response_id from the first event, then yield text/status as they come in
            if event.type == "response.created":
                response_id = event.response.id

            # For text delta events, yield the new text along with the response_id (once we have it)
            elif event.type == "response.output_text.delta":
                yield event.delta, None, response_id

            # When the response is completed, yield a final None with the stop reason and response_id
            elif event.type == "response.completed":
                response_id = event.response.id
                yield None, event.response.status, response_id


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    messages = [msg.model_dump() for msg in req.messages]
    print(f"Chat | previous_response_id={req.previous_response_id} +{len(messages)} message(s)")

    # Retrieve relevant scripture for the last user message
    user_query = ""
    for m in reversed(messages):
        if m["role"] == "user":
            user_query = m["content"]
            break
    instructions = SYSTEM_PROMPT
    print('user_query', user_query)

    if user_query:
        context = _retrieve_context(user_query)
        if not context:
            print("RAG | no relevant context found")
            instructions = SYSTEM_PROMPT + "\n\n" + "No relevant KJV scripture was found for the user's query."
        else:
            print(f"RAG | injected {len(context)} chars of context")
            instructions = SYSTEM_PROMPT + "\n\n" + (context or "")

    try:
        if req.stream:
            def generate():
                response_id = None
                for text, sr, resp_id in _iter_response(messages, req.previous_response_id, instructions):
                    res = ""
                    if resp_id and resp_id != response_id:
                        response_id = resp_id
                        res += f"data: {{\"response_id\": \"{resp_id}\"}}\n\n"
                    if text:
                        res += f"data: {text}\n\n"
                    if sr:
                        res += f"data: [DONE]\n\n"
                    if res:
                        yield res
            return StreamingResponse(generate(), media_type="text/event-stream")

        reply, stop_reason, response_id = "", None, None
        for text, sr, resp_id in _iter_response(messages, req.previous_response_id, instructions):
            if text:
                reply += text
            if sr:
                stop_reason = sr
            if resp_id:
                response_id = resp_id

        return ChatResponse(response_id=response_id, reply=reply, stop_reason=stop_reason)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/responses/{response_id}")
def delete_response(response_id: str):
    with LlamaStackClient(base_url=SERVER_URL) as client:
        client.responses.delete(response_id=response_id)
    return {"status": "deleted", "response_id": response_id}


@app.get("/health")
def health():
    try:
        with LlamaStackClient(base_url=SERVER_URL) as client:
            models = [m.identifier for m in client.models.list()]
        return {"status": "ok", "model_available": MODEL_ID in models}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    uvicorn.run("service:app", host="0.0.0.0", port=8000, reload=True)
