# Phase 7: operations dashboard and monitoring

Synthetic data only. This local portfolio application is not HIPAA compliant and has no application authentication.

## Start the platform

Preserve the existing `.env`. For a new checkout only, copy `.env.example` to `.env`, then set a local `POSTGRES_PASSWORD` and stable `N8N_ENCRYPTION_KEY`. Keep `AI_PROVIDER=fake` for an offline demo. Set `APP_VERSION=0.7.0`. Never commit `.env`.

Run from the repository root:

```powershell
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 240
docker compose ps -a
```

| Service | Address |
| --- | --- |
| FastAPI Swagger | http://localhost:8000/docs |
| Liveness | http://localhost:8000/health |
| Readiness | http://localhost:8000/ready |
| n8n | http://localhost:5678 |
| Streamlit | http://localhost:8501 |
| PostgreSQL | Internal Compose service `postgres:5432` |

The migration service must exit with code 0; the other application services should become healthy. The dashboard runs as a non-root user and receives only `API_BASE_URL=http://backend:8000`. It has no database credentials or PostgreSQL driver and uses a separate network shared with the backend, not PostgreSQL. `DASHBOARD_PORT` changes the host port, default 8501.

For optional host Python access or older `n8n/verify_*.py` scripts that inspect PostgreSQL directly, explicitly enable the loopback database port:

```powershell
docker compose -f docker-compose.yml -f docker-compose.host-db.yml up -d --wait --wait-timeout 240
```

Ordinary `docker compose up` keeps the database internal. PostgreSQL test service access remains on a separate host port for pytest. No volume deletion is necessary for upgrades.

## Analytics and filters

Dashboard → FastAPI analytics API → PostgreSQL. No patient reference, request text, reviewer notes, prompt or unrestricted audit metadata is returned by these endpoints.

- GET `/api/v1/analytics/summary`: KPI totals, category/decision/status charts, AI failures, agent execution/failure totals and tool usage.
- GET `/api/v1/analytics/activity`: bounded recent activity, default 30, maximum 100 via `limit`.
- Both accept optional `date_from`, `date_to` (ISO dates), `category` and `status` (`received`, `processed`, `failed`). Invalid filters return 422.

Dates include both endpoints in UTC. Request metrics use request creation dates and current category/status. Agent metrics and activity use audit event dates. With category/status filters, agent events are limited to matching requests and runs linked through a request-specific event. Unlinked global/failed-before-execution runs are excluded under these filters. Without category/status filters, all agent activity in the event date range is counted.

| Metric | Definition |
| --- | --- |
| Total requests | Requests in the filtered creation cohort |
| Completed requests | Processed requests with final AUTO_PROCESS or REJECT decision |
| Pending requests | Received requests or final HUMAN_REVIEW decision |
| Automated | Processed AUTO_PROCESS requests with no human review record |
| Human reviews | All review records for the filtered requests, including resolved reviews |
| Pending reviews | Review records still PENDING |
| Failed | Requests with status failed |
| Automation rate | Automated / total requests × 100; zero for an empty cohort |
| Average AI confidence | Mean non-null confidence; N/A for no classifications |
| AI failures | AI_CLASSIFICATION_FAILED events, including safely escalated failures |
| Agent executions | AGENT_STARTED events |
| Agent failures | Distinct run UUIDs with AGENT_FAILED, avoiding multiple failure events per run |
| Agent tool calls/usage | AGENT_TOOL_EXECUTED events, grouped by registered tool |

Human approvals do not inflate automation rate. Request failures, AI failures and agent failures are separate metrics. Category/decision charts include UNCLASSIFIED/UNDECIDED. All summary calculations use one read-only repeatable-read transaction; activity is fetched separately and can reflect newer events.

The Streamlit sidebar provides date, category and workflow status filters plus Refresh. It displays six KPI cards, four bar charts, completion/pending counts, agent counts and recent activity. Each refresh performs live API reads; errors show an unavailable message rather than cached or invented zero totals. Recent activity exposes only controlled event/actor labels, timestamp and opaque trace/run IDs.

## Reliability and tracing

The dashboard retries only GET requests after network failures or HTTP 429/502/503/504: at most three attempts, five-second HTTP operation timeouts, and 0.25/0.5-second backoff. Validation/authentication errors, unexpected 500s and malformed response JSON are not retried. Creation, processing, agent runs, review actions and n8n POSTs have no automatic retries. Duplicate processing returns the stored result or 409 while in progress; completed review actions return 409.

Existing LLM malformed-output/timeout handling routes classification to human review. Agent failures use the bounded fallback described in the agent guide. Database errors return generic responses; logs omit SQL parameters and credentials. API validation now also masks unknown input field names because those names can themselves contain sensitive text.

Every API request gets an `X-Correlation-ID` response header, including errors. A supplied canonical UUIDv4 is reused; missing or invalid headers are replaced with a random UUID. Do not encode healthcare identifiers in trace IDs. The context propagates to application JSON logs and a new nullable indexed `audit_events.correlation_id` column (migration `0005`). Old audit rows retain null IDs. Correlation IDs are tracing hints, not authentication or idempotency keys.

Updated n8n exports forward incoming correlation headers to FastAPI and propagate the backend response ID. The classification workflow forwards the creation call's validated ID to its processing call. Re-import and publish the exports to update an existing n8n instance:

```powershell
docker compose exec n8n n8n import:workflow --input=/workflows/01_request_intake.json
docker compose exec n8n n8n publish:workflow --id=healthcareRequestIntake01
docker compose exec n8n n8n import:workflow --input=/workflows/01_healthcare_request_automation.json
docker compose exec n8n n8n publish:workflow --id=healthcareRequestAutomation01
docker compose exec n8n n8n import:workflow --input=/workflows/02_agent_operations.json
docker compose exec n8n n8n publish:workflow --id=healthcareAgentOperations02
docker compose restart n8n
```

An envelope rejected by n8n before calling FastAPI has no backend trace/audit. Existing temporary n8n execution-storage limitations remain; use only synthetic input.

## Manual verification

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/api/v1/analytics/summary
Invoke-RestMethod 'http://localhost:8000/api/v1/analytics/activity?limit=5'
docker compose exec backend python -m alembic -c alembic.ini check
```

Use Swagger or the existing n8n flows to create/process a synthetic request, then refresh Streamlit. Check the total, category/decision/status charts and activity. A request sent to human review remains pending until a human resolves it. A manually approved request must not increase Automated.

For tracing, send the same UUIDv4 header to the creation and processing calls, inspect their response headers, then find the ID in backend logs or recent activity. The updated n8n classification flow does this automatically between its two calls.

For dependency outage/recovery:

```powershell
docker compose stop postgres
curl.exe -i http://localhost:8000/health
curl.exe -i http://localhost:8000/ready
docker compose up -d --wait postgres
```

Liveness stays 200, readiness returns 503 during outage, and the dashboard reports unavailable after bounded retries. Refresh after recovery. Readiness checks PostgreSQL and migrated table access, including the correlation column; it does not make paid LLM calls.

## Automated verification

```powershell
docker compose --profile test up -d --wait postgres-test
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests
Get-Content -Raw n8n/test_workflow.cjs | docker compose exec -T n8n node
Get-Content -Raw n8n/test_automation.cjs | docker compose exec -T n8n node
Get-Content -Raw n8n/test_agent.cjs | docker compose exec -T n8n node
Get-Content -Raw n8n/test_monitoring.cjs | docker compose exec -T n8n node
docker compose --profile test stop postgres-test
```

Tests cover aggregate calculations, manual approval exclusion, empty cohorts, filters, agent-run grouping, bounded safe activity, correlation headers/logs/audits, input privacy and bounded dashboard retries. Earlier provider, agent, readiness, duplicate-processing and transactional tests remain included. No automated test requires a paid LLM.

## Files changed

New: analytics route/schema/service; correlation context helper; Alembic migration `0005`; analytics and dashboard-client tests; dashboard app/API client/requirements/Dockerfile/build exclusions; optional host-DB Compose override; n8n monitoring tests; this guide.

Updated: main middleware/error handling, JSON logging, audit model, readiness service, migration-head test, app version, `.env.example`, Compose services/networks, README and all three n8n workflow exports. Ignored local `.env` has the new app version and remains untracked.
