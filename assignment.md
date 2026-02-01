# APT-ONE – AI Engineer Assessment

Hi Auvi,

Below you will find the assessment for the two AI engineers for **APT-ONE**.

---

## TASK 1

### Subtask 1: Service Orchestration
- As a user, I want the components of the application to be able to interact with one another in a simple but secure way. Therefore, Docker Compose should be used as the top-level orchestration of single services.

**Acceptance Criteria:**
- Latest Docker version  
- Standard and secure Docker Compose file with all services  

---

### Subtask 2: Vector & Document Database
- As a user, I want to manage structured and vectorized topic-specific data in databases. Therefore, I need a MongoDB (version **8.0.0 or higher**).

**Acceptance Criteria:**
- MongoDB available in Docker Compose  
- MongoDB with vector and similarity capabilities (can be queried in natural language)  
- MongoDB port available within Docker Compose, but not externally  

---

### Subtask 3: Graph Database
- As a user, I want structured data to be stored in a native graph database. Therefore, I need **Neo4j** available in Docker Compose.

**Acceptance Criteria:**
- Neo4j installed  
- Neo4j ready to be injected with data  
- Neo4j ready to be queried with Cypher  
- Neo4j port available within Docker Compose, but not externally  

---

### Subtask 4: User Interface
- As a user, I need a UI to interact with the application. Therefore, a Python UI should be integrated based on **NiceGUI**.

**Acceptance Criteria:**
- One service in Docker Compose is the Python GUI  
- GUI port exposed via Docker Compose  

---

### Subtask 5: Backend API
- As a user, I want the frontend to execute functionality. Therefore, a responsive async backend server built with **FastAPI** should be implemented.

**Acceptance Criteria:**
- FastAPI server with all backend functionalities available as a separate service in Docker Compose  
- Server ports only available within Docker Compose, not externally  

---

### Subtask 6: LLM Service
- As a user, I want the application to use LLMs. Therefore, **LM Studio** should be implemented as its own service.

**Acceptance Criteria:**
- LM Studio available in Docker Compose  
- LM Studio ports only available within Docker Compose  

---

## TASK 2

### Subtask 0: MITRE Data Management
- As a user, I want to access and maintain MITRE data in a modern way so that I can quickly find and use MITRE data via natural language queries and Cypher.

**Acceptance Criteria:**
- Database creation logic runs once per instance (shared among clients)  
- MITRE document management is well defined when external MITRE data is updated:
  - Insert  
  - Replace  
  - Delete  
- MITRE data available as proper and usable embeddings (vectorized) in MongoDB  
- MITRE data available in Neo4j (supports recursive queries more effectively)  

---

## Subtask 1:

- As a user I want to see the MITRE version, so that I have an understanding of the latest MITRE version.
- **Acceptance Criteria:**
  - Shows latest `x_mitre_version` stored in backend
- **API:** `GET /api/mitre/version`

---

## Subtask 2:

- As a user I want to have a download button for the current MITRE dataset, so that I can retrieve the MITRE entity content.
- **Acceptance Criteria:**
  - “Download” action.
  - Clicking it fetches the MITRE content and returns JSON.
  - Errors during retrieval are shown.
- **API:** `GET /api/mitre/`

---

## Subtask 3:

- As a user I want to have an upload/update button for the MITRE data, so that I can replace the existing MITRE with a new version.
- **Acceptance Criteria:**
  - An “Update” action.
  - The user can select a new MITRE file (or provide updated content).
  - The new file is validated if valid MITRE
  - The existing MITRE is replaced/updated.
  - Errors during update are shown.
- **API:** `PUT /api/mitre/{ x_mitre_version }`

---

## Subtask 4:

- As a backend system I want to provide the current `x_mitre_version` of MITRE data, so that the frontend can display it.
- **Acceptance Criteria:**
  - The API returns the `x_mitre_version`
  - Proper errors are returned for unexpected failures.
- **API:** `GET /api/mitre/version`

---

## Subtask 5:

- As a backend system I want to return a specific MITRE (metadata + content or file stream), so that users can view or download it.
- **Acceptance Criteria:**
  - The API returns MITRE json file.
  - Returns 404 if the MITRE data missing.
  - Returns meaningful error messages on failure.
- **API:** `GET /api/mitre/`

---

## Subtask 6:

- As a backend system I want to allow updating an existing MITRE `x_mitre_version`, so that users can publish new versions without changing references.
- **Acceptance Criteria:**
  - The API accepts new MITRE content/file for the given id as json.
  - Stored MITRE is replaced/updated successfully.
  - Metadata is updated (e.g., last modified, size, type, `x_mitre_version`).
  - Optional: audit log/versioning is created if required.
  - Returns success or a detailed validation error.
- **API:** `PUT /api/mitre/`
