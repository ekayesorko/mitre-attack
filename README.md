# MITRE Data Management

A full-stack application for managing **MITRE ATT&CK** (and related) data with vector search, graph visualization, and RAG-powered chat. Built for the APT-ONE AI Engineer assessment.

## Features

- **MITRE dataset management** — Upload, update, and download MITRE STIX bundles (JSON). Track versions and metadata.
- **Vector search** — Natural-language and prefix/suffix search over MITRE entities using MongoDB Atlas vector search and embeddings.
- **Graph view** — Explore relationships (e.g. USES) between entities in Neo4j, rendered as interactive SVG graphs.
- **Chat** — Conversational interface backed by an LLM (Ollama) with RAG over the stored MITRE data.

## Tech Stack

| Component        | Technology                          |
|-----------------|-------------------------------------|
| Orchestration   | Docker Compose                      |
| Backend API     | FastAPI (async)                     |
| Frontend        | NiceGUI (Python)                    |
| Document + vector DB | MongoDB 8 (Atlas-compatible) |
| Graph DB        | Neo4j                               |
| LLM / embeddings | Ollama (OpenAI-compatible API)    |

## Prerequisites

- **Docker** and **Docker Compose** (latest recommended)
- No local Python/Node required for running via Docker

## Quick Start

1. **Clone and enter the repo**
   ```bash
   cd mitre
   ```

3. **Start all services**
   ```bash
   docker compose up --build
   ```
   First run will build images and pull Ollama models (`gemma3:4b`, `nomic-embed-text`), which can take a few minutes.

4. **Open the app**
   - **UI:** [http://localhost:8080](http://localhost:8080)
   - **Backend API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health check:** [http://localhost:8000/health](http://localhost:8000/health)

## Ports

| Service   | Port(s)        | Purpose                    |
|-----------|----------------|----------------------------|
| Frontend  | 8080           | NiceGUI app                |
| Backend   | 8000           | FastAPI                    |
| MongoDB   | 27017          | Document/vector DB         |
| Neo4j     | 7474, 7687     | Browser UI, Bolt           |
| Ollama    | 11434          | LLM API                    |


## Project Structure

```
mitre/
├── docker-compose.yaml   # Orchestration: mongodb, neo4j, ollama, backend, frontend
├── backend/              # FastAPI app
│   ├── app/
│   │   ├── api/          # Routers: mitre, graph, chat, search
│   │   ├── db/           # MongoDB + Neo4j clients, MITRE persistence
│   │   ├── schemas/      # Pydantic models
│   │   └── services/     # RAG, embeddings, chat
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/             # NiceGUI app
│   ├── main.py           # Pages: /, /mitre, /chat, /graph
│   ├── config.py         # API_BASE and derived URLs
│   ├── Dockerfile
│   └── requirements.txt
└── ollama/               # Ollama service + entrypoint (pull models)
    ├── Dockerfile
    └── entrypoint.sh
```

## API Overview

| Area   | Prefix           | Main endpoints |
|--------|------------------|----------------|
| MITRE  | `/api/mitre`     | `GET /latest-version`, `GET /list`, `GET /{version}/download`, `PUT /` (create/update by version) |
| Search | `/api/search`    | `GET /?q=...&top_k=10` — vector + text search over entities |
| Graph  | `/api/graph`     | `GET /svg?stix_id=...` — Neo4j subgraph as SVG |
| Chat   | `/api/chat`      | `POST /` — chat with RAG context (body: `messages`, optional `system`) |

Open [http://localhost:8000/docs](http://localhost:8000/docs) for full OpenAPI schema and try-it-out.

## UI Pages

- **/** — Redirects to Chat.
- **/mitre** — View current MITRE version, list versions, download JSON, and create/update datasets (paste or upload bundle JSON).
- **/chat** — Send messages; backend uses RAG over MITRE data and streams a reply from the configured LLM.
- **/graph** — Search entities, then click a result to see its relationship graph (e.g. USES) as SVG.

## Development

- **Backend (local):** From `backend/`, create a `.env` (or set env vars) matching `example.env`, then run `uvicorn app.main:app --reload`.
- **Frontend (local):** From `frontend/`, set `API_BASE` (e.g. `http://localhost:8000`) and run `python main.py` (or `nicegui run main.py`).
- **Tests:** Backend includes `test_mitre.py`; run with pytest or similar from `backend/` with backend and dependencies available.

## License

See repository or assignment terms.
