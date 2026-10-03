# AI Healthcare Workflow Automation Platform

A portfolio project for a Workflow Automation Specialist role, built incrementally to demonstrate API integrations, workflow automation, validated AI outputs, human review, auditability, monitoring, and security-conscious engineering.

**Use only synthetic/fake healthcare data. This application is not HIPAA compliant.** HIPAA-conscious practices are educational goals, not a compliance claim. Pattern-based redaction is incomplete, and there is no application authentication; use locally with fake data only.

## Phase 6 scope

- FastAPI, Pydantic validation, and SQLAlchemy 2.x with PostgreSQL via psycopg 3.
- Persisted requests and `REQUEST_RECEIVED` audit events in one transaction.
- UUID-based lookup and Alembic-managed schema changes.
- Non-root backend container, PostgreSQL, and a one-shot migration service in Docker Compose.
- Bounded database startup retries, liveness/readiness endpoints, and structured JSON logs.
- A separate disposable PostgreSQL test service.
- n8n orchestration: webhook -> create -> process -> branch on backend decision -> response.
- Deterministic sensitive-data redaction before classification; OpenAI provider abstraction and an offline fake provider.
- Strict Pydantic AI validation and deterministic AUTO_PROCESS / HUMAN_REVIEW / REJECT rules.
- Persisted decisions, transactional audit events, and human approval/rejection with duplicate-decision protection.
- Controlled operations agent with five approved tools, UUID scope checks, execution limits, structured results and audits.
- No application authentication, Redis, dashboard, or background queue.

The **Healthcare Operations Agent** is available at `POST /api/v1/agent/run`. See [the agent architecture, Swagger/n8n demo and changed files](docs/controlled-agent.md). Its export is [02_agent_operations.json](n8n/workflows/02_agent_operations.json). The model can request read tools or human escalation; it cannot execute code, arbitrary SQL/HTTP, or approve/reject reviews. Scope checks constrain tool access within a run; they are not user authentication.

The **Healthcare Request Automation** workflow, architecture, decision rules, API examples, and end-to-end verification are documented in [docs/ai-processing.md](docs/ai-processing.md). Import [n8n/workflows/01_healthcare_request_automation.json](n8n/workflows/01_healthcare_request_automation.json). The [Phase 4 intake guide](docs/n8n-intake.md) and original create-only workflow remain available.

**API change from Phase 1:** POST now returns HTTP **201 Created**, `request_uuid` (replacing the old `request_id` acknowledgement field), status `received`, and `persisted: true` after commit. It does not queue background work.

## Docker setup (recommended)

Requires Docker Desktop/Engine running with Linux containers and a recent Docker Compose v2+ supporting `--wait`. Run from the repository root:

```powershell
# First setup only; preserve an existing .env.
Copy-Item .env.example .env
```

Edit `.env` and set a local `POSTGRES_PASSWORD` and a generated persistent `N8N_ENCRYPTION_KEY`; the committed template deliberately leaves both blank. Compose refuses to start without them. When upgrading, preserve existing credentials, set `APP_VERSION=0.6.0`, and add `AI_PROVIDER=fake` for the offline demo. Follow the [Phase 6 setup instructions](docs/controlled-agent.md#start-and-configure). Do not commit `.env`.

```powershell
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 240
docker compose ps -a
```

Open http://127.0.0.1:8000/docs. `backend` and `postgres` should be healthy; `migrate` should show **Exited (0)**, which means it completed successfully. The backend runs as UID 10001, with no additional Linux capabilities. Build inputs exclude `.env`, virtual environments, test caches, and local data. No credentials are passed as build arguments or embedded in the image.

n8n should also be healthy at http://localhost:5678. Complete its native editor setup, then import and publish the workflow as described in the [automation guide](docs/ai-processing.md#n8n-import-and-verification). The n8n editor has its own built-in login; the healthcare API/webhook and review endpoints still have no application authentication.

The Compose bridge network provides service DNS: backend/migrations connect to `postgres:5432`. Host port settings only affect access from your computer. Backend and PostgreSQL ports bind to `127.0.0.1` on the host. The database retains its named volume. Runtime credentials come from explicitly passed environment variables, not a copied `.env`.

Startup order follows [Compose dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/):

1. PostgreSQL passes its `pg_isready` health check.
2. The migration service retries real DB connections, takes a PostgreSQL transaction advisory lock, and runs `alembic upgrade head` on that connection. It commits on success, rolls back on failure, and exits nonzero on error.
3. The backend starts only after successful migrations, retries DB connectivity itself, and runs Uvicorn. Its container health check uses `/ready`.

There is no infinite startup loop. Defaults permit 15 attempts with 2 seconds between them and a 3-second connection timeout. Migration lock contention times out after 30 seconds. Multiple instances of the migration runner share the advisory lock. Use this runner for upgrades; raw Alembic CLI commands do not take its advisory lock. Direct `docker start` or `--no-deps` bypasses Compose's migration gate.

After code or migration edits, rebuild and recreate through Compose:

```powershell
docker compose up -d --build --wait --wait-timeout 180
docker compose logs --tail 50 backend migrate
```

Code is copied into the image; there is no automatic host-code reload. Container restarts alone do not apply newly edited migrations. Failed migrations block a new backend startup; fix the issue and rerun Compose. Readiness flags runtime outages, but Docker health checks do not automatically restart unhealthy containers.

## Optional host Python setup

Requires Python 3.11+, Docker Desktop/Engine running with Linux containers, and Docker Compose. Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose up -d --wait postgres
docker compose stop backend
Push-Location backend
..\.venv\Scripts\python.exe -m app.db.migrate
if ($LASTEXITCODE -eq 0) { ..\.venv\Scripts\python.exe -m app.start }
# After stopping the API with Ctrl+C:
Pop-Location
```

Configure `.env` as above first. Stop the containerized backend to free port 8000. A local `.env` may already have been created during project verification. `app.start` applies the same logging and database retries used in the container; migrations remain a separate step.

On macOS/Linux use `python3`, `.venv/bin/python`, and `cp .env.example .env`; use `cd backend` and `../.venv/bin/python -m app.db.migrate && ../.venv/bin/python -m app.start` for host startup.

## Configuration and storage

App settings live in `backend/app/core/config.py`; database settings live separately in `backend/app/db/config.py`; AI settings live in `backend/app/core/ai_config.py`. They read the root `.env` regardless of working directory, with process environment variables taking precedence. Recreate the backend after changing container environment settings.

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `APP_ENVIRONMENT`, `APP_VERSION` | Application metadata |
| `APP_LOG_LEVEL` | JSON logging level: DEBUG, INFO, WARNING, or ERROR |
| `AI_PROVIDER` | `fake` (offline default) or `openai` |
| `OPENAI_API_KEY` | Backend-only secret, needed for the real provider; blank in template |
| `OPENAI_MODEL` | Structured-output model, defaults to `gpt-4.1-mini` |
| `AI_TIMEOUT_SECONDS` | Provider HTTP timeout, defaults to 20, allowed 1–30 |
| `AGENT_MAX_TOOL_CALLS` | Maximum tool attempts per run, defaults to 5, allowed 1–10 |
| `AGENT_TIMEOUT_SECONDS` | Planning/tool execution deadline, defaults to 25, allowed 0.1–40 |
| `AGENT_ALLOW_GLOBAL_COUNT` | Server policy for aggregate pending-review counts, defaults to true |
| `API_PORT` | Compose host API port, defaults to 8000 |
| `N8N_PORT` | Local n8n editor/webhook port, defaults to 5678 |
| `N8N_ENCRYPTION_KEY` | Required stable secret for n8n credential encryption |
| `GENERIC_TIMEZONE` | n8n instance timezone, defaults to UTC |
| `APP_HOST`, `APP_PORT` | Host Python bind settings; Compose fixes its internal bind to 0.0.0.0:8000 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Compose database initialization |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Host Python DB address, defaults to 127.0.0.1:5432; Compose uses postgres:5432 internally |
| `DATABASE_URL` | Optional host-only override using `postgresql+psycopg://`; blank uses POSTGRES settings |
| `DB_CONNECT_TIMEOUT`, `DB_POOL_TIMEOUT` | Connection/pool wait timeouts in seconds, default 3 |
| `DB_STATEMENT_TIMEOUT_MS` | API SQL statement timeout, default 3000; not applied to migrations |
| `DB_STARTUP_ATTEMPTS`, `DB_RETRY_INTERVAL_SECONDS` | Bounded startup retry settings, defaults 15 and 2 |
| `DB_MIGRATION_LOCK_TIMEOUT_SECONDS` | Migration advisory/DDL lock timeout, default 30 |
| `TEST_POSTGRES_PORT` | Dedicated test service host port, defaults to 5433 |
| `TEST_POSTGRES_HOST` | Test host, defaults to 127.0.0.1 |
| `TEST_DATABASE_URL` | Optional test-only override; database name must end in `_test` |

There is no default password. Separate POSTGRES settings build the URL safely, including passwords with URL special characters. If you supply a full host URL instead, URL-encode its password and keep it consistent with the initialized database. Compose deliberately ignores the host `DATABASE_URL`. Passwords/full URLs use secret settings types and are not printed by application code. Avoid sharing unredacted `docker compose config` or container inspection output, which can include environment values; use `config --quiet` to validate.

The application database uses `postgres_data`; n8n uses `n8n_data` for its SQLite/configuration storage. Ordinary `docker compose down` preserves both named volumes. **`docker compose down -v` deletes stored data and n8n configuration/workflows.** Changing initialization credentials in `.env` does not change users/passwords inside an existing volume. All published ports bind only to `127.0.0.1`.

## API and manual verification

With the API running, open another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready

$payload = @{
    patient_reference = 'PAT-10042'
    request_text = 'The claim was submitted but additional information is required.'
    source = 'api'
    priority = 'normal'
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post `
    -Uri http://127.0.0.1:8000/api/v1/requests `
    -ContentType 'application/json' -Body $payload
$created

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/requests/$($created.request_uuid)"
```

Expected behavior:

- Health: HTTP 200 with `{"status":"ok"}`. This checks process liveness, not database readiness.
- Ready: HTTP 200 with `{"status":"ready","database":"ok"}` after a live query and checks that all three migrated tables can be read. It returns HTTP 503 with `{"status":"not_ready","database":"unavailable"}` on DB/schema failure. It does not read patient fields or mutate data. It does not call the LLM provider.
- POST: HTTP 201, a `Location` header, UUID, status `received`, `category: null`, source, priority, timezone-aware timestamps, and `persisted: true`. It omits patient reference and request text.
- GET: HTTP 200 with stored request details, including the synthetic reference/text. Internal numeric IDs are omitted.
- Unknown UUID: HTTP 404. Malformed UUID, short text, or invalid priority: HTTP 422.
- Database operation failure: HTTP 503 with a generic message; no database exception or parameters are exposed.

Validation requires a `PAT-` reference followed by ASCII digits (max 64 characters); text of 10-10,000 characters after trimming; source `api` or `n8n`; priority `low`, `normal`, or `high`. Direct API source/priority default to `api`/`normal`; the n8n workflow stamps source `n8n`. Unknown fields are rejected. A `PAT-` reference does not guarantee fake data. Each POST creates a new request; deduplication is not implemented.

After creation, `POST /api/v1/requests/{request_uuid}/process` runs redaction, classification and decision rules synchronously. `GET /api/v1/reviews/pending` lists pending reviews; `POST /api/v1/reviews/{id}/approve` or `/reject` resolves one. See the [copyable manual test](docs/ai-processing.md#manual-api-verification). A processed request may still await human review; final disposition is in `system_decision`.

Verify the database and audit without selecting healthcare text. With the default example user/database:

```powershell
docker compose exec postgres psql -U healthcare -d healthcare -c "SELECT r.request_uuid, r.status, a.event_type, a.actor, a.metadata FROM requests r JOIN audit_events a ON a.request_id = r.id ORDER BY a.id DESC LIMIT 5;"
```

If you customized the user/database, substitute those names. You should see a `REQUEST_RECEIVED` event with actor `api` and metadata containing only source and priority. Actor `api` identifies the entry point, not an authenticated person.

Stop and restart the API and run `docker compose restart postgres`, then GET the same UUID to confirm persistence. In `/docs`, change text to `short` or priority to `urgent` to check validation.

Verify outage/recovery while the backend remains running:

```powershell
docker compose stop postgres
curl.exe -i http://127.0.0.1:8000/health  # 200
curl.exe -i http://127.0.0.1:8000/ready   # 503
docker compose up -d --wait postgres
curl.exe -i http://127.0.0.1:8000/ready   # 200 after recovery
```

On macOS/Linux use `curl`. The backend's connection pool checks stale connections and recovers without restarting the API. Existing writes are not automatically retried; failed transactions still roll back. If a POST connection is lost after the DB commits, verify the result before retrying because this API is not idempotent.

## Structured logs

`docker compose logs -f backend migrate` shows JSON application/server events with UTC timestamps, levels, and logger names. Request-completion events include method, route template (such as `/api/v1/requests/{request_uuid}`), HTTP status, and duration. Startup/retry/migration failures emit fixed event names without exception text or tracebacks.

Application logs exclude bodies, `patient_reference`, `request_text`, raw paths/query strings, credentials, headers, and arbitrary extra fields. Uvicorn access logs and SQL/driver debug logs are disabled. PostgreSQL retains its own server log format with error statement/row details suppressed. This is data minimization, not PHI masking or a HIPAA compliance guarantee.

## Models, transactions, and migrations

- `requests`: bigint identity `id`, unique UUID `request_uuid`, reference/text, source, priority, status, nullable category/confidence/AI recommendation/system decision/decision reason, timezone-aware `created_at` and `updated_at`.
- `audit_events`: bigint identity `id`, indexed nullable `request_id` foreign key, event type, actor, JSONB `metadata`, and timezone-aware `created_at`. Global agent audits have no request FK and correlate through `metadata.run_uuid`. Its Python attribute is `event_metadata` because SQLAlchemy reserves `metadata`.
- `human_reviews`: unique request foreign key, PENDING/APPROVED/REJECTED status, AI recommendation, reviewer decision/notes, creation/review timestamps. Review resolution and completion audits commit together.
- String enums have named database CHECK constraints. The UUID has a unique constraint/index; audits reference requests with deletion restricted. Audit data is not immutable/tamper-proof in this phase.
- Routes handle HTTP only. The creation service flushes the request, inserts the audit, and commits both using `Session.begin()`. Errors roll back both; success is returned only after commit. Sessions are opened/closed per HTTP request.
- PostgreSQL supplies creation timestamps. SQLAlchemy updates `updated_at` on ORM/Core updates; raw SQL writers must set it explicitly. Processing/review actions update the request through services.
- Alembic is the only schema creation mechanism. The API never calls `create_all()` or applies migrations on startup. Review generated migrations before applying them.
- Application SQL echo is disabled, SQL parameters are hidden, validation errors omit submitted values, and request bodies are not logged. Compose suppresses SQL error statements/row details in PostgreSQL logs. These measures are not PHI masking.

Useful migration commands:

```powershell
docker compose exec backend python -m alembic -c alembic.ini current
docker compose exec backend python -m alembic -c alembic.ini check
# After intentionally changing models in a future approved phase:
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini revision --autogenerate -m "describe schema change"
```

The initial migration is reversible, but downgrading removes both tables and their data. Tests verify downgrade/upgrade only inside temporary schemas. Implementation follows the [SQLAlchemy transaction pattern](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#framing-out-a-begin-commit-rollback-block) and [Alembic migration workflow](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

## Tests

Use the separate disposable PostgreSQL service (its data directory is in tmpfs):

```powershell
docker compose --profile test up -d --wait postgres-test
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests
docker compose --profile test stop postgres-test
```

Tests require the host Python dependencies from the optional setup section. They use `TEST_DATABASE_URL` if set; otherwise they build a URL from `TEST_POSTGRES_HOST`, `TEST_POSTGRES_PORT`, and the POSTGRES credentials, always selecting `healthcare_test`. They never fall back to the application database URL/name. Each database test creates a unique schema, applies real Alembic migrations, then drops only that schema. Test credentials need schema-creation permissions. Missing/unavailable configuration fails integration tests instead of silently skipping them.

Coverage includes persistence, readiness, startup retries, safe logs, migrations, redaction, validated classification, provider failures, decision thresholds, reviews, audits, concurrent processing/review protection, and agent scope/limits/failure/rollback behavior. Tests use fake providers and mocked HTTP; they require no paid LLM calls. See [agent tests and live verification](docs/controlled-agent.md#tests-and-files). For tests without PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -m "not integration"
```

## Structure

```text
backend/
  app/
    api/routes/       # Thin HTTP handlers
    schemas/          # Pydantic API contracts
    services/         # Requests, redaction, AI abstraction, decisions and reviews
    core/             # App/AI configuration and shared enums
    models/           # SQLAlchemy Request, AuditEvent and HumanReview
    db/               # Separate DB settings, engine, sessions, base
    agents/           # Bounded planner, explicit registry, trusted tool execution
    main.py           # App factory and safe error responses
    start.py          # DB wait and structured Uvicorn startup
  alembic/            # Migration environment, template, and revisions
  alembic.ini
  tests/
  pytest.ini
  requirements.txt
  Dockerfile
  .dockerignore
docker-compose.yml    # Backend, PostgreSQL, migrations, n8n, test PostgreSQL
n8n/workflows/        # Portable intake, classification and controlled agent workflows
n8n/verify_intake.py  # Real webhook + database verification with synthetic data
n8n/verify_automation.py # All decisions and review actions against local Docker
n8n/test_workflow.cjs # Exported workflow JavaScript checks
n8n/test_automation.cjs # Processing response/error and branch checks
n8n/verify_agent.py   # Real agent webhook/review/audit verification using fake provider
n8n/test_agent.cjs    # Agent workflow response, fallback and safety checks
dashboard/           # Placeholder only
database/
sample-data/
docs/
```
