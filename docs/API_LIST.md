# MITRE Backend API List (FastAPI)

APIs are defined per **assignment.md** (Task 2). Base URL: `/api/mitre`.

| Method | Path | Assignment ref | Description |
|--------|------|----------------|-------------|
| **GET** | `/api/mitre/version` | Subtask 1 & 4 | Returns latest `x_mitre_version` stored in backend. |
| **GET** | `/api/mitre/` | Subtask 2 & 5 | Returns MITRE entity content as JSON. 404 if data missing. |
| **PUT** | `/api/mitre/{x_mitre_version}` | Subtask 3 | Update/replace MITRE: provide new file or content for given version. |
| **PUT** | `/api/mitre/` | Subtask 6 | Update existing MITRE: body contains `x_mitre_version` + content (JSON). |

## Details

- **GET /api/mitre/version**  
  Response: `{ "x_mitre_version": "<string>" }`.  
  Errors: 404 when no MITRE data is loaded.

- **GET /api/mitre/**  
  Response: `{ "x_mitre_version": "<string>", "content": <object>, "metadata": <object> }`.  
  Errors: 404 when MITRE data is missing.

- **PUT /api/mitre/{x_mitre_version}**  
  Body: MITRE JSON (raw or file upload). Validates and replaces data for that version.  
  Errors: 400 if body missing or invalid.

- **PUT /api/mitre/**  
  Body: `{ "x_mitre_version": "<string>", "content": <object> }`. Replaces stored MITRE and updates metadata.  
  Returns success or validation error.

## Health

- **GET /health**  
  Returns `{ "status": "ok" }` for orchestration/health checks.

## OpenAPI

When the FastAPI server is running: **GET /docs** (Swagger UI), **GET /redoc** (ReDoc).
