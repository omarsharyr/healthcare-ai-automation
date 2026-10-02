# AI Healthcare Workflow Automation Platform

A portfolio project for a Workflow Automation Specialist role, built incrementally to demonstrate API integrations, workflow automation, validated AI outputs, human review, auditability, monitoring, and security-conscious engineering.

**Use only synthetic/fake healthcare data. This application is not HIPAA compliant.** HIPAA-conscious engineering practices are educational goals, not a compliance claim. There is no authentication in Phase 1; run locally with fake data only.

## Phase 1 scope

- FastAPI application with `GET /health` and `POST /api/v1/requests`.
- Pydantic validation, enum values, and UUID generation.
- Central environment-based configuration and pytest tests.
- No database, persistence, queue, AI, n8n integration, authentication, or processing.

HTTP 202 means the API accepted and validated the payload only. It does **not** promise background work. The UUID is an acknowledgement identifier, not a stored record identifier; there is no retrieval endpoint.

## Setup (Python 3.11+)

From the repository root, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
```

Copy the environment template only on first setup; preserve existing local settings. Open http://127.0.0.1:8000/docs for interactive API documentation.

Configuration lives in `backend/app/core/config.py`. It reads the root `.env` file regardless of working directory; process environment variables take precedence. Supported keys are `APP_NAME`, `APP_ENVIRONMENT`, and `APP_VERSION`. Settings are cached; restart after changes. `.env` is ignored by Git. No secrets are required in this phase.

## Manual verification

With the server running, open a second PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health

$payload = @{
    patient_reference = 'PAT-10042'
    request_text = 'The claim was submitted but additional information is required.'
    source = 'api'
    priority = 'normal'
} | ConvertTo-Json

Invoke-WebRequest -UseBasicParsing -Method Post `
    -Uri http://127.0.0.1:8000/api/v1/requests `
    -ContentType 'application/json' -Body $payload
```

Health returns HTTP 200 with `{"status":"ok"}`. POST returns HTTP 202, for example:

```json
{
  "request_id": "bb9f14fe-1df3-4674-878b-4ff6b9fb0025",
  "status": "accepted",
  "persisted": false,
  "message": "Request accepted for validation only; it has not been stored or queued for processing."
}
```

Each POST generates a fresh UUID. In `/docs`, change `request_text` to `short` or `priority` to `urgent`; either should return HTTP 422.

Validation rules:

- `patient_reference`: required, `PAT-` followed by ASCII digits, at most 64 characters. This naming convention does not guarantee data is synthetic.
- `request_text`: required, 10–10,000 characters after trimming surrounding whitespace.
- `source`: `api` only in Phase 1; defaults to `api`.
- `priority`: `low`, `normal`, or `high`; defaults to `normal`.
- Unknown fields are rejected. Responses do not echo patient references or request text. Validation errors omit submitted input values. Application code does not log request bodies.

## Tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini
```

On macOS/Linux use `.venv/bin/python` instead. The four tests cover health, accepted requests (including UUID uniqueness and explicit non-persistence), short text, and invalid priority. They use an in-process HTTP client and require no external services.

## Structure and decisions

```text
backend/
  app/
    api/routes/       # Thin HTTP handlers
    schemas/          # Pydantic input/output contracts and enums
    services/         # Acceptance service; no storage or processing
    core/             # Environment configuration
    agents/           # Reserved for a later phase
    models/           # Reserved for a later phase
    db/               # Reserved for a later phase
    main.py           # App factory and validation error handling
  tests/
  pytest.ini
  requirements.txt
n8n/workflows/        # Placeholder only
dashboard/           # Placeholder only
database/            # Placeholder only
sample-data/         # Reserved for synthetic fixtures
docs/
```

Empty directories use `.gitkeep` so Git retains the scaffold. Dockerfile and Compose configuration are deferred with infrastructure. Request categories, workflow outcomes, business rules, audit storage, masking, and AI providers will be introduced only in approved later phases. No empty implementation classes or simulated database have been added.
