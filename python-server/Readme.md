# Gosipel Llama Python Server

A FastAPI service that wraps [Llama Stack](https://github.com/meta-llama/llama-stack) to provide a simple chat API with persistent session history. Uses [Ollama](https://ollama.com) for local LLM inference.

---

## Prerequisites

- [Ollama](https://ollama.com/download) installed and running
- [pyenv](https://github.com/pyenv/pyenv) installed
- [Poetry](https://python-poetry.org/docs/#installation) installed

---

## Local Development Setup

### 1. Pull the model

```bash
ollama pull llama3.2:3b
```

### 2. Set up Python and install dependencies

```bash
pyenv install 3.12.12   # skip if already installed
poetry install
```

### 3. Install Llama Stack server-side dependencies

This step injects server-side packages (opentelemetry, faiss-cpu, torchtune, etc.) into the venv. **Must be re-run any time the venv is recreated.**

```bash
poetry run llama stack build --config configs/build.yaml --image-type venv
```

### 4. Start the Llama Stack server

```bash
poetry run llama stack run configs/local-config.yaml
```

The server starts on port `8321`.

### 5. Start the FastAPI service

In a second terminal:

```bash
poetry run python app/service.py
```

The service starts on port `8000`.

---

## API

### `POST /chat`

Send a message. On the first call, omit `session_id` — it will be created and returned. Pass it back on subsequent calls to continue the conversation.

**Request**
```json
{
  "messages": [{ "role": "user", "content": "Hello!" }],
  "session_id": "optional-on-first-call",
  "stream": false
}
```

**Response**
```json
{
  "session_id": "abc-123",
  "reply": "Hello! How can I help you?",
  "stop_reason": "end_of_turn"
}
```

**Streaming** — set `"stream": true`. The response is SSE. The first event contains the session ID, subsequent events contain text chunks:
```
data: {"session_id": "abc-123"}

data: Hello! How can I help

data: you?

data: [DONE]
```

### `DELETE /sessions/{session_id}`

Deletes a session and its full conversation history.

### `GET /health`

Returns service status and whether the model is available.

---

## Session management

- Sessions are created on the first `/chat` call and the `session_id` is returned in the response.
- Pass `session_id` on every subsequent call to continue the same conversation.
- Sessions idle for more than 24 hours are deleted automatically by a background cleanup task.
- To delete all sessions and reset state, run:

```bash
poetry run python scripts/clean_up.py
```

> Stop the Llama Stack server before running `clean_up.py`.

---

## Docker (production)

> Work in progress — see `Dockerfile` and `docker-compose.yml`.

```bash
docker compose up
```

On first run this downloads the model weights (~2 GB). Subsequent starts are fast.

---

## Project structure

```
app/
  service.py          # FastAPI service (main entrypoint)
  chat.py             # Manual test script
scripts/
  clean_up.py         # Wipes all agents/sessions from the LS database
Dockerfile            # Docker image for the FastAPI service
docker-compose.yml    # Full stack: Ollama + Llama Stack + service
docker/               # Llama Stack Dockerfile and entrypoint scripts
configs/              # Local development configs
pyproject.toml        # Python dependencies (Poetry)
poetry.lock           # Locked dependency versions
```
