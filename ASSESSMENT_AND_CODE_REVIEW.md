# Assessment Evaluation & Code Review Guide

Step-by-step guide to evaluate the **APT-ONE AI Engineer Assessment** implementation and review the codebase. Reference: `assignment.md`.

---

## 1. Prerequisites

- **Docker** and **Docker Compose** (latest)
- Clone repo and ensure `assignment.md` and `README.md` are present

---

## 2. Task 1 – Service Orchestration & Components

### Step 2.1 – Docker Compose

| Check | File | What to verify |
|-------|------|----------------|
| Orchestration | `docker-compose.yaml` | Single compose file; all services under one project; `version: '3.8'` or compatible |
| MongoDB 8+ | `docker-compose.yaml` | Image `mongodb/mongodb-atlas-local:8.0.3` (or ≥ 8.0.0); vector/search capable |
| Neo4j | `docker-compose.yaml` | Service `neo4j`; ready for data and Cypher |
| UI | `docker-compose.yaml` | NiceGUI service (`frontend`); port **8080** exposed |
| Backend | `docker-compose.yaml` | FastAPI service (`backend`); no host port mapping (internal only) |
| LLM | `docker-compose.yaml` | LLM service present; no host ports (internal only) |
| MongoDB/Neo4j ports | `docker-compose.yaml` | MongoDB (27017) and Neo4j (7687/7474) not exposed to host (commented or omitted) |
| Network | `docker-compose.yaml` | All services on same internal network (e.g. `mitre_network`) |

**Deviation:** LLM service is **Ollama** (with `ollama/` Dockerfile and entrypoint), not **LM Studio** as specified. LM Studio is commented out in `docker-compose.yaml`. Backend still uses an OpenAI-compatible API (`LM_STUDIO_URI` points to `http://ollama:11434/v1`). Functionally equivalent; document as “Ollama used instead of LM Studio.”

---

## 3. Task 2 – MITRE Data Management & APIs

### Step 3.1 – Backend API Routes

| Assignment | Expected API | Implementation | File to check |
|------------|--------------|----------------|---------------|
| Subtask 2.1 & 2.4 | `GET /api/mitre/version` | ✅ `GET /version` (prefix `/api/mitre`) | `backend/app/api/mitre.py` |
| Subtask 2.2 & 2.5 | `GET /api/mitre/` | ✅ `GET /`; optional `?version=` for specific version | `backend/app/api/mitre.py` |
| Subtask 2.3 | `PUT /api/mitre/{x_mitre_version}` | ✅ `PUT /{x_mitre_version}` | `backend/app/api/mitre.py` |
| Subtask 2.6 | `PUT /api/mitre/` | ✅ `PUT /` (creates new version; 409 if exists) | `backend/app/api/mitre.py` |

Router is mounted in `backend/app/main.py` with `prefix="/api/mitre"`, so full paths match the assignment.

### Step 3.2 – API Behavior

| Endpoint | Check |
|----------|--------|
| `GET /api/mitre/version` | Returns `x_mitre_version`; 404 when no data |
| `GET /api/mitre/` | Returns MITRE JSON (bundle); 404 when no data; optional `?version=` for a specific version |
| `PUT /api/mitre/{version}` | Replaces/updates that version; validates bundle; updates metadata |
| `PUT /api/mitre/` | Inserts new version (version from bundle); 409 if version already exists |

**Note:** `GET /api/mitre/` returns the **raw bundle** as JSON with `Content-Disposition: attachment`. Any test expecting a wrapper like `{ "content": { "objects": [...] } }` is incorrect; the response body is the bundle (e.g. `objects` at top level).

### Step 3.3 – Database Logic (Task 2, Subtask 0)

| Criterion | Where to check |
|-----------|----------------|
| Creation logic once per instance | MongoDB/Neo4j connections in `backend/app/main.py` (lifespan); indexes/constraints in `backend/app/db/mongo.py` and `backend/app/db/neo4j.py` |
| Insert / Replace / Delete | Insert: `insert_mitre_document`; Replace: `put_mitre_document`; “Delete” = replace entities + replace doc (see `_update_mitre_entities`, `_update_mitre_documents`) in `backend/app/db/mongo.py` |
| Embeddings in MongoDB | `backend/app/services/mitre_write.py` builds entities with embeddings; `backend/app/db/mongo.py` stores in `mitre_entities` with vector index |
| Neo4j sync | `backend/app/db/neo4j.py`: `store_mitre_bundle`; called from `MitreWriteService` in `backend/app/services/mitre_write.py` |

**Files:**  
`backend/app/db/mongo.py`, `backend/app/db/neo4j.py`, `backend/app/services/mitre_write.py`, `backend/app/main.py` (lifespan).

---

## 4. Files to Check (Summary)

### Core backend

| File | Purpose |
|------|--------|
| `backend/app/main.py` | FastAPI app; lifespan; route registration; health |
| `backend/app/api/mitre.py` | MITRE REST: version, list, download, PUT by version, PUT create |
| `backend/app/db/mongo.py` | MongoDB repo; collections; vector search; CRUD |
| `backend/app/db/neo4j.py` | Neo4j repo; bundle sync; graph query (e.g. USES) |
| `backend/app/services/mitre_write.py` | Write orchestration: embeddings + Mongo + Neo4j |
| `backend/app/services/embeddings.py` | Embedding client (OpenAI-compatible; config uses `LM_STUDIO_URI`) |
| `backend/app/services/rag.py` | RAG context retrieval for chat |
| `backend/app/config.py` | Env-based settings (required vars) |

### Frontend

| File | Purpose |
|------|--------|
| `frontend/main.py` | NiceGUI pages: `/`, `/mitre`, `/chat`, `/graph` |
| `frontend/config.py` | `API_BASE`, URLs for version/list/download |

### Orchestration & config

| File | Purpose |
|------|--------|
| `docker-compose.yaml` | All services; ports; env vars |
| `assignment.md` | Official acceptance criteria |
| `README.md` | Run instructions; structure; API overview |

### Tests

| File | Purpose |
|------|--------|
| `backend/test_mitre.py` | MITRE API tests (GET version/content, PUT create, 409, etc.) |

---

## 5. Deviations Summary

| Item | Assignment | Implementation | Severity |
|------|------------|----------------|----------|
| LLM service | LM Studio in Docker Compose | **Ollama** in Docker Compose; LM Studio commented out | Low – same API shape |
| GET /api/mitre/ response | “Returns MITRE json file” | Raw bundle JSON + `Content-Disposition: attachment`; optional `?version=` | None – acceptable |
| PUT /api/mitre/ | “Allow updating existing” | Implemented as **insert** new version (409 if exists); “update existing” = `PUT /api/mitre/{version}` | None – both behaviors covered |
| API path wording | “GET /api/mitre/” | Implemented as `GET /api/mitre/` (root of router) | None |
| Backend port exposure | “Server ports only within Compose” | Backend port not in `ports:` (commented) | None |

---

## 6. Quick Verification Commands

**Before running these:** Ensure the backend port is accessible. If using Docker Compose with the backend port not exposed, either expose it in `docker-compose.yaml` (e.g. `ports: ["8000:8000"]` for the backend service) or run the backend locally so that `http://localhost:8000` is reachable. The frontend proxy and the commands below need to reach the backend.

```bash
# Start stack
docker compose up --build -d

# Health
curl -s http://localhost:8000/health

# Version (expect 404 if no data, or JSON with x_mitre_version)
curl -s http://localhost:8000/api/mitre/version

# Docs
open http://localhost:8000/docs
open http://localhost:8080
```

Run backend tests (with backend and MongoDB available):

```bash
cd backend && python test_mitre.py
```

---

## 7. Review Checklist

- [ ] Docker Compose starts all services without errors  
- [ ] MongoDB 8+ with vector search index (`mitre_entities_vector`)  
- [ ] Neo4j accepts data and is used for graph (e.g. USES)  
- [ ] NiceGUI on 8080; backend only on internal network  
- [ ] `GET /api/mitre/version` and `GET /api/mitre/` behave as above  
- [ ] `PUT /api/mitre/{version}` updates; `PUT /api/mitre/` creates (409 if exists)  
- [ ] MITRE entities have embeddings in MongoDB; RAG/chat uses them  
- [ ] Document LLM deviation: Ollama instead of LM Studio  

Use this guide together with `assignment.md` and `README.md` for a full evaluation and code review.
