# Final verification record

Verified on 2026-10-03 against the local Docker stack with synthetic data and `AI_PROVIDER=fake`.

| Check | Result |
| --- | --- |
| Complete pytest suite | 120 passed; one upstream Starlette/HTTPX deprecation warning |
| Complete exported n8n JavaScript suite | 16 passed across five test files |
| Docker Compose build/start | Backend, n8n, dashboard and PostgreSQL healthy; migration service exited 0 |
| Alembic | `0005 (head)`; `alembic check` reports no new upgrade operations |
| FastAPI root and Swagger | HTTP 200 after root redirects to `/docs` |
| `/health` and `/ready` | HTTP 200; database ready |
| n8n and Streamlit | Readiness/health endpoints accessible; real browser dashboard and Swagger screenshots captured |
| Low-confidence approval demo | Passed: 0.60 confidence overrides AUTO_PROCESS, human approves, duplicate review rejected, scoped agent reads history/status, metrics/audits verified |
| Low-confidence rejection demo | Passed with a new synthetic request and human rejection |
| Browser webhook guards | All three published workflows return 403 for an external Origin |
| Secret/export check | Working files and 150 reachable Git blobs checked; no known local secret values or selected API/private-key patterns found |
| Git hygiene | `.env` ignored/untracked; all three workflow JSON files exist with no credentials/pinned data |
| Documentation | Requested README sections and five final guides written; local file links resolve |

Run commands are in [README](../README.md), [workflow tests](n8n-workflows.md#demo-and-tests), [security checks](security.md#repository-check) and [demo](demo.md). The scripts leave synthetic demo requests/reviews/audits in PostgreSQL for inspection. Test schemas are isolated and cleaned up; no application volumes were deleted.

Automated external HTTP transports are blocked and real provider contracts are mocked. No paid LLM call was made. The focused repository check is not a full dependency vulnerability scan, penetration test, or proof that every possible secret pattern is absent. Remaining local-demo authentication, redaction, audit integrity and deployment limitations are documented in [security.md](security.md).
