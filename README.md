# Ollive — Lightweight LLM Inference Logging & Ingestion

End-to-end system for a multi-turn chatbot with **auto-instrumented** inference logging, near-real-time ingestion, Postgres storage, event-based workers, PII redaction, streaming chat, latency/throughput/error dashboards, Docker Compose, and self-hosted Kubernetes manifests.

## Features

| Requirement | Status |
|-------------|--------|
| Multi-turn chatbot + short context + UI | ✅ |
| Lightweight SDK / auto-instrumentation | ✅ `packages/inference-sdk` |
| Near-real-time ingestion API | ✅ `POST /v1/ingest` |
| Validate / parse / store metadata | ✅ |
| Chat messages + inference logs schema | ✅ |
| Multi-provider (Groq, OpenAI, Anthropic, Gemini) | ✅ |
| Streaming responses (SSE) | ✅ |
| Latency / throughput / errors dashboards | ✅ |
| Docker Compose one-command setup | ✅ |
| Event-based architecture (Redis Streams) | ✅ |
| PII redaction | ✅ |
| Self-hosted k8s manifests | ✅ |
| Cancel / list / resume conversations | ✅ |

Default provider is **Groq** (OpenAI-compatible, free-tier friendly).

> **Note:** `mixtral-8x7b-32768` was removed from the catalog — Groq decommissioned it (HTTP 400). Current Groq models: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- A free [Groq](https://console.groq.com) API key (`GROQ_API_KEY`)

## Quick start (Docker Compose)

```bash
# 1. Configure env
cp .env.example .env
# Put your GROQ_API_KEY (or other provider keys) in .env

# 2. One command
docker compose up --build
```

Open:

- **UI**: http://localhost:3000
- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

## Local development (without Docker for app code)

```bash
# Infra
docker compose up -d postgres redis

# SDK
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e packages/inference-sdk
pip install -r apps/api/requirements-dev.txt

# API
cd apps/api
uvicorn app.main:app --reload --port 8000

# Worker (separate terminal)
cd apps/worker
pip install -r requirements.txt
python worker.py

# Web
cd apps/web
npm install
npm run dev
```

UI: http://localhost:5173

## Architecture (short)

See [ARCHITECTURE.md](./ARCHITECTURE.md) for ingestion flow, logging strategy, scaling, and failure handling.

```
Web → API (chat + InstrumentedLLM) → /v1/ingest
                                      ├─ Redis Streams → Workers → Postgres
                                      └─ sync persist → Postgres
Dashboards read inference_events from Postgres.
```

## Schema design decisions

- **`conversations`**: session metadata, provider/model, cancel flag — cheap list/resume.
- **`messages`**: full transcript for product UX + `content_redacted` column.
- **`inference_events`**: normalized telemetry (latency, TTFT, tokens, status) + JSONB `raw_payload` for forward compatibility.
- **`ingest_dead_letters`**: poison-pill storage so bad events don’t block the stream.

**Tradeoffs**

- Dual-write (API + worker) favors demo freshness + eventual consistency; `event_id` uniqueness prevents double counts.
- Previews (not full prompts) in telemetry reduce PII/storage risk.
- Regex PII redaction is lightweight; not a full DLP pipeline.
- Redis Streams over Kafka — simpler ops for this scale.

## API surface

- `POST /v1/conversations` — create
- `GET /v1/conversations` — list
- `GET /v1/conversations/{id}` — resume/load
- `POST /v1/conversations/{id}/cancel`
- `POST /v1/conversations/{id}/resume`
- `POST /v1/conversations/{id}/chat` — streaming SSE or JSON
- `POST /v1/ingest` — SDK ingestion
- `GET /v1/metrics/summary` — dashboard aggregates
- `GET /v1/inference-events` — recent telemetry

## SDK usage

```python
from inference_sdk import InstrumentedLLM, ChatMessage

llm = InstrumentedLLM(provider="groq", model="llama-3.3-70b-versatile")
text = llm.chat(
    [ChatMessage(role="user", content="Hello")],
    conversation_id="...",
)
```

All calls auto-capture metadata and ship to `INGESTION_URL`.

## Kubernetes (self-hosted)

```bash
# Build images + apply manifests (kind/minikube/k3s)
bash k8s/deploy.sh

# Or manually
kubectl apply -k k8s/
kubectl -n ollive port-forward svc/web 8080:80
```

Update `k8s/secret.yaml` with real API keys before applying to a shared cluster.

## Demo

1. Start with `docker compose up --build`
2. Open http://localhost:3000
3. Send a few chat messages (try including an email to see redaction in dashboards)
4. Open **Dashboards** for latency / throughput / errors
5. Use **Cancel** mid-stream, then **Resume** to continue the same conversation

Optional: record a Loom of the above flow for submission.

### Smoke tests

With the stack running:

```bash
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

Covers health, providers, multi-turn chat, streaming SSE, cancel/resume, every Groq model, PII redaction, metrics, and ingest auth.

## What we’d improve with more time

- Disk-backed SDK retry buffer + exponential backoff
- OpenTelemetry traces linking chat request → provider span → ingest event
- ClickHouse / Timescale for long-range analytics
- AuthN/Z for multi-tenant apps
- Stronger PII (NER-based) + field-level encryption
- Load tests + SLO burn-rate alerts
- Helm chart + Terraform for cloud k8s

## Submission checklist

- [x] GitHub-ready source
- [x] README (setup, architecture, schema, tradeoffs, future work)
- [x] Architecture notes (`ARCHITECTURE.md`)
- [x] Demo via Docker Compose (hosted link optional)

Email to: **team@brank.ai**
Deadline: **19 July 2026 EOD**

## License

MIT