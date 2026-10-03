# Five-minute portfolio demo

## Story

A synthetic claim-status inquiry arrives through a webhook. The classifier recommends automatic handling but reports low confidence. Deterministic rules override that recommendation, queue a human review, and record the decision trail. A human resolves it. An operations agent then retrieves status/history using only approved tools. The dashboard shows the request and human review without counting the human approval as automation.

This is a portfolio/educational project using synthetic healthcare data. It demonstrates security-conscious and HIPAA-aware design principles but is not a claim of HIPAA compliance.

## Prepare

1. Configure `.env` as in the README and select `AI_PROVIDER=fake`.
2. Run `docker compose up -d --build --wait --wait-timeout 240`.
3. Import/publish the classification and agent workflows using [the workflow guide](n8n-workflows.md).
4. Open Swagger at http://localhost:8000/docs, n8n at http://localhost:5678 and the dashboard at http://localhost:8501.

The fake provider makes this demonstration deterministic and free. It substitutes for the LLM API; no real model is called. The same provider abstraction, redaction, Pydantic validation, decision service, transactions and audit logic run. A real OpenAI adapter is implemented and HTTP-mocked in tests; real-provider outputs are not promised to match the fixture.

## Present the workflow

| Step | Show / explain |
| --- | --- |
| 1. Intake | POST `sample-data/demo-low-confidence.json` to the n8n classification webhook |
| 2. Persistence | FastAPI creates a UUID request and REQUEST_RECEIVED in one transaction |
| 3. Redaction | PAT/CLM identifiers, DOB, email and phone are replaced before the provider call |
| 4. Classification | Fake LLM fixture returns CLAIM_STATUS, confidence 0.60, recommendation AUTO_PROCESS |
| 5. Validation | Pydantic enforces exact enums, numeric range, required fields and no extras |
| 6. Rules | Confidence 0.60 < 0.85 takes priority over the recommendation |
| 7. Human queue | Response shows HUMAN_REVIEW, review ID and fixed reason `Confidence below 0.85.` |
| 8. Decision | Reviewer explicitly approves or rejects; a second decision returns 409 |
| 9. Agent | `Check status and history` runs two scoped read-only tools; no direct database/model authority |
| 10. Audit | Correlation ID ties intake/redaction/classification/decision/review/tool events together |
| 11. Dashboard | Refresh totals/activity; review count increases while Automated does not |

Original synthetic text includes `PAT-90001`, `CLM-90001`, `1995-10-02`, `demo@example.test` and `202-555-0199`. Redaction tests inspect provider inputs; the application intentionally does not log those inputs to make the demo visible.

## One-command verified demo

Requires host Python dependencies from the README; it reads application data only through FastAPI. The Docker CLI checks the running provider is fake before any request.

```powershell
.\.venv\Scripts\python.exe scripts/demo.py
# Optional second run demonstrating rejection, with a new synthetic request:
.\.venv\Scripts\python.exe scripts/demo.py --decision reject
```

The script asserts the 0.60 confidence override, resolves the review, checks duplicate protection, calls the agent through n8n, reads audit activity, and verifies dashboard metric changes. It prints only generated UUIDs, controlled outcomes and tool names. It leaves the synthetic rows/audits in place. Run on an otherwise idle local demo instance because metric assertions compare before/after totals. Custom ports can use `--api` and `--n8n` URL options.

## Interactive alternative

```powershell
$trace = [guid]::NewGuid().ToString()
$headers = @{ 'X-Correlation-ID' = $trace }
$result = Invoke-RestMethod -Method Post `
    -Uri http://localhost:5678/webhook/healthcare-request-automation `
    -Headers $headers -ContentType 'application/json' `
    -Body (Get-Content -Raw sample-data/demo-low-confidence.json)
$result
Invoke-RestMethod http://localhost:8000/api/v1/reviews/pending

# An explicit human action; change approve to reject for the other outcome.
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8000/api/v1/reviews/$($result.review_id)/approve" `
    -Headers $headers -ContentType 'application/json' `
    -Body '{"reviewer_notes":"Synthetic portfolio demo reviewed."}'

$agent = @{message='Check status and history'; request_uuid=$result.request_uuid} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/healthcare-agent-operations `
    -Headers $headers -ContentType 'application/json' -Body $agent
Invoke-RestMethod 'http://localhost:8000/api/v1/analytics/activity?limit=30'
```

The same calls are available in Swagger. In the dashboard, click Refresh and inspect Human Reviews, workflow decisions and activity. `processed` includes a request awaiting human review; explain final `system_decision` separately.

## Closing talking points

The project demonstrates workflow integration, provider abstraction, deterministic policy, human escalation, transactional persistence, bounded agent capabilities and operational visibility. It does not claim actual medical outcomes, calibrated AI accuracy, measured business savings, authentication, production readiness or HIPAA compliance.
