# Architecture Notes — Ollive Inference Logger

## System overview

```
┌────────────┐     SSE stream      ┌─────────────────────┐
│  Web UI    │ ──────────────────► │  FastAPI (chat+API) │
│  React     │ ◄────────────────── │  InstrumentedLLM    │
└────────────┘                     └─────────┬───────────┘
                                             │ auto-instrumented logs
                                             ▼
                                   ┌─────────────────────┐
                                   │  POST /v1/ingest    │
                                   │  validate + redact  │
                                   └─────────┬───────────┘
                          ┌──────────────────┼──────────────────┐
                          ▼                                     ▼
                 ┌────────────────┐                    ┌────────────────┐
                 │ Redis Streams  │                    │   PostgreSQL   │
                 │ (event bus)    │                    │ (sync write)   │
                 └───────┬────────┘                    └────────────────┘
                         ▼
                 ┌────────────────┐
                 │ Worker(s)      │── insert-or-skip (event_id) ──► PostgreSQL
                 └────────────────┘
```

## Ingestion flow

1. Every LLM call goes through `inference-sdk.InstrumentedLLM` (auto-instrumentation).
2. On completion / cancel / error, the SDK builds an `InferenceLog` with:
   - provider, model, latency, TTFT, token usage
   - conversation/session/request IDs
   - status + error fields
   - redacted input/output previews
3. The SDK ships the log near-real-time via HTTP (`POST /v1/ingest`) on a background thread / awaitable.
4. The ingestion API:
   - authenticates with `X-Ingest-Key`
   - validates with Pydantic
   - publishes to **Redis Streams** (event-based path)
   - also persists synchronously so dashboards stay snappy
5. Workers consume the stream with consumer groups (plus `XAUTOCLAIM` for idle pending), re-validate, redact PII again, and insert-or-skip by unique `event_id`.

## Logging strategy

- **Auto-instrumentation**: application code never manually logs tokens/latency; wrapping the provider call is enough.
- **Dual-write**: sync DB write + async queue. Sync path optimizes UX; queue path optimizes durability/scale.
- **Previews, not full prompts**: store short redacted previews to limit PII/storage cost.
- **Idempotency**: `event_id` unique constraint prevents double-counting when both API and worker persist.

## Schema design decisions

| Table | Purpose | Tradeoff |
|-------|---------|----------|
| `conversations` | chat session metadata + cancel flag | Separate from messages for cheap list/resume |
| `messages` | full chat transcript | Keep full text for product UX; also store `content_redacted` |
| `inference_events` | telemetry warehouse | Wide row with JSONB `raw_payload` for forward-compat |
| `ingest_dead_letters` | poison messages | Fail-open for the API, inspect later |

Indexes on `started_at`, `(provider, model)`, `status`, and `conversation_id` support dashboard queries without a separate OLAP store.

## Scaling considerations

- **API**: horizontally scale FastAPI replicas; Redis + Postgres are shared.
- **Workers**: scale consumer group members; Redis Streams distributes messages.
- **Stream trim**: `XADD maxlen≈100000` bounds memory.
- **Postgres**: for larger volume, partition `inference_events` by time and move dashboards to materialized views / ClickHouse.
- **LLM fan-out**: provider adapters are stateless; add rate-limit middleware per provider key.

## Failure handling assumptions

- **Ingest shipper failure**: SDK logs a warning and drops the event (chat UX must not break). Acceptable for demo; production would buffer to disk.
- **Redis down**: API still sync-persists; `queued=false` in response.
- **Bad payloads**: worker ACKs after writing dead-letter rows (no infinite retry loops).
- **Cancel mid-stream**: cancel endpoint flips `cancel_requested`; stream loop refreshes and stops; inference log status becomes `cancelled`.
- **Duplicate delivery**: unique `event_id` makes at-least-once queue delivery safe.

## Multi-provider & streaming

Providers: Groq (OpenAI-compatible), OpenAI, Anthropic Messages API, Google Gemini.

Streaming uses SSE from API → browser, and provider-native streams under the SDK. TTFT is measured at first token.

## PII redaction

Regex redaction for email, phone, SSN-like, credit-card-like, and IPv4 patterns applied:

- in the SDK before shipping previews
- again in the ingestion/worker path before storage

This is defense-in-depth, not a substitute for a dedicated DLP service.

## Self-hosted Kubernetes

`k8s/` contains Namespace, ConfigMap, Secret, Deployments, Services, Ingress, and a `deploy.sh` helper for kind/minikube/self-hosted clusters. Images are built locally (`ollive-api`, `ollive-worker`, `ollive-web`) and loaded into the cluster.