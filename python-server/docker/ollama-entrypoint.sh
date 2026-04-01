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
echo "Model ready."

wait $OLLAMA_PID
