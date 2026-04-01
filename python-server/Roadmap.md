# Roadmap: RAG + Post-Training

Two independent capabilities to add to the Gosipel Llama Python Server.

---

## Part 1: RAG — Document Lookup

Let the AI look up content from a shared knowledge base (plain text, markdown, PDFs, URLs) before answering. On every `/chat` request, relevant chunks are retrieved and injected automatically.

The Llama Stack infrastructure is already configured: FAISS (`vector_io`) and `rag-runtime` (`tool_runtime`) are both listed in `configs/local-config.yaml`. Only application code needs to be added.

### Approach

Manual pre-retrieval on every `/chat` request — before calling `_iter_turn()`, query the FAISS vector DB with the user's last message and prepend retrieved chunks as context. Deterministic: retrieval always happens regardless of model tool-use decisions.

Documents are managed by the developer, not end users. There is no public upload endpoint. To update the knowledge base, edit files in `docs/` and re-run the indexing script.

### Implementation steps

#### 1. Developer-managed `docs/` folder

Place reference files in a `docs/` folder at the project root:

```
docs/
  about.md
  faq.txt
  reference.pdf
  urls.txt        # one URL per line
```

#### 2. New `scripts/index_documents.py`

A developer script that reads `docs/`, extracts text, chunks it, and pushes everything into FAISS. Run manually whenever documents are updated.

**Logic:**
1. Register the vector DB (idempotent — safe to re-run)
2. For each file in `docs/`:
   - `.txt` / `.md`: read directly
   - `.pdf`: extract text per page with `pypdf`
   - `urls.txt`: fetch each URL with `httpx`, strip HTML with `beautifulsoup4`
3. Chunk text into ~512-token segments with ~50-token overlap
4. Call `client.vector_io.insert(vector_db_id=VECTOR_DB_ID, chunks=[...])`
5. Print summary: `Indexed N chunks from M documents`

**New dependencies** (add to `requirements.txt`):
- `pypdf` — PDF text extraction
- `httpx` — URL fetching
- `beautifulsoup4` — HTML stripping

#### 3. Vector DB registration on startup

In the `lifespan` function (`app/service.py:80`), register the vector DB so the service can query it. No re-indexing at startup — that's the script's job.

```python
VECTOR_DB_ID = "gosipel_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

client.vector_dbs.register(
    vector_db_id=VECTOR_DB_ID,
    embedding_model=EMBEDDING_MODEL,
    embedding_dimension=384,
    provider_id="faiss",
)
```

> **Config update needed**: Add the embedding model to `configs/local-config.yaml` under `models:`.

#### 4. Auto-retrieval in `/chat`

In the `chat()` handler (`app/service.py:183`), before `_iter_turn()`:

```python
def _retrieve_context(query: str) -> str | None:
    with LlamaStackClient(base_url=SERVER_URL) as client:
        results = client.vector_io.query(
            vector_db_id=VECTOR_DB_ID,
            query=query,
            params={"max_chunks": 5, "score_threshold": 0.3},
        )
    if not results.chunks:
        return None
    parts = [f"[{i+1}] {c.content}" for i, c in enumerate(results.chunks)]
    return "Relevant context:\n" + "\n\n".join(parts)
```

Inject the result as a context message before the user's message. If the DB is empty (no docs indexed yet), retrieval is silently skipped.

#### 5. `GET /health` update

Add `"vector_db": VECTOR_DB_ID, "docs_indexed": N` to the health response.

### Files to change

| File | Change |
|------|--------|
| `app/service.py` | Vector DB init in lifespan, auto-retrieval in `/chat`, health update |
| `configs/local-config.yaml` | Add embedding model under `models:` |
| `requirements.txt` | Add `pypdf`, `httpx`, `beautifulsoup4` |
| `docs/` | New folder — developer-managed reference documents |
| `scripts/index_documents.py` | New — reads `docs/`, chunks and indexes into FAISS |

### Verification

```bash
# 1. Add a reference document
echo "Gosipel is a platform for..." > docs/about.md

# 2. Index it
conda run -n llamastack-local-llama-stack python scripts/index_documents.py
# Expected: "Indexed N chunks from 1 document"

# 3. Start Llama Stack + service
llama stack run configs/local-config.yaml
conda run -n llamastack-local-llama-stack python app/service.py

# 4. Chat and confirm context is injected
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is Gosipel?"}]}'

# 5. Confirm health shows docs indexed
curl http://localhost:8000/health
```

---

### Per-session documents (future consideration)

If users need to upload their own temporary documents without polluting the shared knowledge base, Llama Stack supports this cleanly via **per-session vector DBs**.

**How it would work:**
- On session creation, register a new vector DB named `gosipel_docs_{session_id}`
- Add a `POST /sessions/{session_id}/documents` endpoint for user uploads
- In `/chat`, query **both** the shared DB and the session DB, then merge results
- On `DELETE /sessions/{session_id}`, delete the session's vector DB too
- TTL cleanup handles the session DB alongside the session itself

**Why not now:** Adds meaningful complexity — two DB queries per turn, per-session DB lifecycle management — and the use case isn't needed yet.

---

## Part 2: Post-Training / Fine-Tuning

Teach the model a custom tone or persona via supervised fine-tuning (SFT) with LoRA. Training data is not yet prepared — this covers the full setup so everything is ready when data is available.

The `post_training` (torchtune) and `datasetio` (localfs) providers are already configured in `configs/local-config.yaml`. No service code changes are needed for training.

### Key constraint: Ollama does not support fine-tuning

Ollama is inference-only. Fine-tuning requires downloading the raw model weights separately (Meta format) and making them accessible to the torchtune provider.

### Setup steps

#### Step 1 — Download model weights

```bash
# Requires a Meta access token at huggingface.co
llama model download --source meta --model-id Llama3.2-3B-Instruct
# Weights land at: ~/.llama/checkpoints/Llama3.2-3B-Instruct/
```

Alternatively, download from HuggingFace and convert to Meta format using torchtune's conversion tool.

#### Step 2 — Install training dependencies

```bash
conda run -n llamastack-local-llama-stack \
  pip install torch torchtune==0.5.0 torchao==0.8.0
```

Apple Silicon (Metal/MPS) is supported. Training will be slower than on CUDA.

#### Step 3 — Prepare training data

Format: JSONL, one conversation per line, `instruct` format:

```jsonl
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

For custom tone/persona, create 50–500 examples demonstrating the target style. Quality matters more than quantity.

Store at: `data/training/persona_sft.jsonl`

#### Step 4 — Register dataset

```python
# scripts/register_dataset.py
client.datasets.register(
    dataset_id="gosipel_persona_v1",
    provider_id="localfs",
    url={"uri": "file:///abs/path/to/data/training/persona_sft.jsonl"},
    metadata={"data_format": "instruct"},
)
```

#### Step 5 — Launch SFT job

```python
# scripts/run_finetune.py
job = client.post_training.supervised_fine_tune(
    job_uuid=str(uuid.uuid4()),
    model="Llama3.2-3B-Instruct",  # raw checkpoint ID, not the Ollama model ID
    training_config={
        "n_epochs": 3,
        "data_config": {
            "dataset_id": "gosipel_persona_v1",
            "batch_size": 2,
            "shuffle": True,
            "data_format": "instruct",
        },
        "optimizer_config": {
            "optimizer_type": "adamw",
            "lr": 2e-5,
            "weight_decay": 0.01,
            "num_warmup_steps": 10,
        },
    },
    algorithm_config={
        "type": "LoRA",
        "lora_attn_modules": ["q_proj", "v_proj"],
        "apply_lora_to_mlp": False,
        "apply_lora_to_output": False,
        "rank": 8,
        "alpha": 16,
    },
    hyperparam_search_config={},
    logger_config={},
    checkpoint_dir="~/.llama/checkpoints/gosipel-persona-v1",
)
```

#### Step 6 — Monitor and use the checkpoint

```python
# scripts/finetune_status.py
status = client.post_training.job.status(job_uuid="...")
print(status.status, status.checkpoints)
```

After `completed`, merge the LoRA weights into the base model and re-quantize to serve via Ollama (separate workflow).

### Scripts to create

| Script | Purpose |
|--------|---------|
| `scripts/register_dataset.py` | Register a local JSONL file as a Llama Stack dataset |
| `scripts/run_finetune.py` | Launch a fine-tune job and poll until completion |
| `scripts/finetune_status.py` | Check job status and list checkpoints |

### Verification

```bash
# Verify torchtune is installed
conda run -n llamastack-local-llama-stack \
  python -c "import torchtune; print(torchtune.__version__)"

# Register dataset
conda run -n llamastack-local-llama-stack python scripts/register_dataset.py

# Launch fine-tune
conda run -n llamastack-local-llama-stack python scripts/run_finetune.py

# Poll status
conda run -n llamastack-local-llama-stack python scripts/finetune_status.py
```
