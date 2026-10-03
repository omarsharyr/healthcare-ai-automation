# Security review

This is a portfolio/educational project using synthetic healthcare data. It demonstrates security-conscious and HIPAA-aware design principles but is not a claim of HIPAA compliance.

## Scope and threat model

The review covers application source/configuration, reachable Git history, exported n8n workflows, the local Compose deployment and tests. Treat incoming healthcare text and every LLM response as untrusted. Trusted operators control `.env`, the Docker host, n8n editing and application source. This is a local single-user demo, not an internet-facing healthcare system. This review is not penetration testing, dependency-CVE certification or a compliance assessment.

## Findings and actions

| Area | Result / control | Residual limitation |
| --- | --- | --- |
| Secrets, API keys, DB credentials | Ignored `.env`; blank example secrets; secret settings types; no secrets in build contexts/arguments; focused workspace and Git-history scan | Environment values are visible to host/container administrators; use a secret manager in production |
| PHI and LLM exposure | Rule-based redaction before classification/planning; only synthetic fixtures; free-text LLM reasons discarded | Patterns miss names, addresses and unsupported formats; raw synthetic input remains in request records and request GET responses |
| Agent permissions | Fixed registry, Pydantic schemas, UUID scope, bounded plan, timeout/call budget, explicit read/escalation policy | Caller scope is not identity/tenant authorization; authenticated ownership rules are absent |
| Prompt injection | Untrusted-data instructions plus actual registry/policy checks; no dynamic code/SQL/URL execution or approval/rejection tools | Injection may influence classification or escalation; structured output validates shape, not truth |
| Input and SQL injection | Pydantic enum/length/extra-field validation; parameterized SQLAlchemy expressions; UUID path parsing; fixed SQL statements | An authenticated deployment still needs authorization, rate limits and workload isolation |
| HTTP body/browser boundary | **Fixed:** 64 KiB streamed body cap, JSON-only nonempty writes, same-origin write check, trusted local/backend hostnames | No identity checks or rate limits; trusted local processes can still call endpoints; no slow-client protection SLA |
| CORS | No permissive CORS middleware; cross-origin writes rejected before execution | CORS is not authentication and does not prevent non-browser clients |
| n8n webhooks | **Fixed:** JSON-only inputs and rejection of non-loopback browser origins; 1 MiB configured payload cap; no automatic POST retry | Webhooks remain unauthenticated for local demo use; Origin can be spoofed by non-browser clients |
| n8n capabilities | Community packages/env access disabled; execute-command, file-write/read and local-file-trigger nodes explicitly excluded | A trusted n8n editor can author code/HTTP workflows; internal JS runner is not hardened multi-user isolation |
| Docker | Loopback ports, internal DB, separate dashboard network, non-root app images, dropped capabilities, no Docker socket | DB initialization user also serves app/migrations; separate least-privilege roles, TLS and secret lifecycle are future work |
| Logging/errors | Structured field allowlist; no request bodies/SQL params/credentials; safe error messages; unknown validation keys masked | Upstream infrastructure/operator commands can expose data; do not share raw container config or inspect output |
| Audit metadata | Controlled event types, reason codes, counts, decisions and opaque trace IDs; no prompts/provider reasoning | Audits are mutable; database outages can prevent failure-audit persistence |
| Review actions | Row locks, unique review FK, duplicate decisions rejected; agent cannot approve/reject | Human reviewer label is not a verified identity; local review APIs have no authentication |

## HTTP controls

FastAPI accepts Host names `localhost`, `127.0.0.1` and internal `backend`. Unsafe requests with an Origin header must match their own scheme/Host. Nonempty writes require `application/json`; empty process/review action bodies remain valid. Requests over 65,536 bytes return 413, including streamed bodies that omit or misrepresent Content-Length. Unknown hosts return 400; cross-origin writes return 403; non-JSON writes return 415. Error responses retain opaque correlation IDs. Responses disable caching and set `nosniff` and `no-referrer`.

n8n performs corresponding JSON/origin checks before forwarding. Only loopback HTTP browser origins are accepted; non-browser demo clients omit Origin. Webhook headers are not authorization credentials. No webhook secret is embedded in JSON. Before exposing services beyond localhost, add an authenticated TLS gateway, signed/authenticated webhooks, rate limits and role/tenant authorization. Do not solve exposure by enabling wildcard CORS.

## LLM boundary

The real adapters use a fixed OpenAI endpoint, no redirects/proxy environment inheritance, configurable timeouts and structured schemas. They receive redacted text, not DB objects/credentials. `store:false` does not guarantee zero provider retention or HIPAA compliance. Automated tests block real HTTP transports and use fake providers/MockTransport. The live scripted demo refuses to run unless the container selects the fake provider. No paid provider call is required for verification.

Confidence is a model-produced value, not calibrated certainty. Business rules enforce confidence < 0.85, OTHER, invalid output and provider errors → HUMAN_REVIEW. Administrative AUTO_PROCESS/REJECT outcomes do not transfer money, deny coverage or make treatment decisions.

## Repository check

```powershell
.\.venv\Scripts\python.exe scripts/security_check.py
git check-ignore .env
git ls-files .env
```

The script checks tracked/unignored working files and all reachable Git blobs for known local secret values and selected API/private-key patterns. It reports filenames only, never matched values. It also rejects historical tracked `.env`, credential references and pinned workflow data. This focused check is not exhaustive entropy scanning; no automated scan can prove the absence of every possible secret. If a credential ever enters Git, rotate it and address history, not just the latest file.

## Security regression tests

Tests cover browser origins/hosts, body streaming/size, JSON content type, safe validation/error responses, SQL payloads stored as data, agent tool invention/scope/future-write denial, redaction-before-provider, audit privacy, human review concurrency, duplicate processing, and safe analytics. n8n security tests exercise every exported envelope guard. Existing LLM schema/failure and bounded-agent tests remain included.

## Before any real deployment

Keep synthetic-only use until identity/RBAC/tenant authorization, TLS, authenticated webhooks, encrypted backups, least-privilege DB roles, controlled egress, rate limits, retention/deletion, dependency scanning, tamper-resistant auditing and incident procedures are designed and reviewed. Any actual healthcare deployment requires separate organizational, contractual, legal and security evaluation.

The n8n configuration uses its documented [node exclusion controls](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/security/block-specific-nodes.md) and [endpoint limits](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/endpoints.md).
