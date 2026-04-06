#!/bin/sh
set -e

ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama to start..."
until ollama list 2>/dev/null; do
  sleep 2
done

echo "Pulling model ${OLLAMA_MODEL}..."
ollama pull ${OLLAMA_MODEL}

echo "Pulling embedding model ${OLLAMA_EMBEDDING_MODEL}..."
ollama pull ${OLLAMA_EMBEDDING_MODEL}

echo "Models ready."

wait $OLLAMA_PID
