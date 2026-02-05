#!/bin/sh
set -e

# Start Ollama in the background
ollama serve &
OLLAMA_PID=$!

# Wait until the server is ready (ollama list returns 0 when server is up)
while ! ollama list >/dev/null 2>&1; do
  sleep 1
done

# Pull chat and embedding models (idempotent; skips if already present)
ollama pull gemma3:4b
ollama pull nomic-embed-text

# Keep container running
wait $OLLAMA_PID
