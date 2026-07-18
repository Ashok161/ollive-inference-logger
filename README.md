# Ollive — Lightweight LLM Inference Logging & Ingestion

End-to-end system for a multi-turn chatbot with **auto-instrumented** inference logging, near-real-time ingestion, Postgres storage, event-based workers, PII redaction, streaming chat, latency/throughput/error dashboards, Docker Compose, and self-hosted Kubernetes manifests.

## Live production demo

| | |
|---|---|
| **URL** | https://ollive-api.onrender.com |
| **Health** | https://ollive-api.onrender.com/health |
| **API docs** | https://ollive-api.onrender.com/docs |

**Production layout**

- **Render** (one free web service): UI + API + worker + embedded Redis
- **Neon**: managed Postgres (`DATABASE_URL` / `DATABASE_URL_SYNC`)

Cold starts on Render free tier can take ~30–60s after idle — refresh once if the first request times out.

Repo: https://github.com/Ashok161/ollive-inference-logger

## Features

| Requirement | Status |
|-------------|--------|
| Multi-turn chatbot + short context + UI | Done |
| Lightweight SDK / auto-instrumentation | Done — `packages/inference-sdk` |
| Near-real-time ingestion API | Done — `POST /v1/ingest` |
| Validate / parse / store metadata | Done |
| Chat messages + inference logs schema | Done |
| Multi-provider (Groq, OpenAI, Anthropic, Gemini) | Done |
| Streaming responses (SSE) | Done |
| Latency / throughput / errors dashboards | Done |
| Docker Compose one-command setup | Done |
| Event-based architecture (Redis Streams) | Done |
| PII redaction | Done |
| Self-hosted k8s manifests | Done |
| Cancel / list / resume conversations | Done |

Default provider is **Groq**; default model is `openai/gpt-oss-20b`.

Catalog (Groq): `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`.  
Gemini catalog uses `gemini-2.5-flash` / `gemini-2.5-flash-lite`.

---

## Path A — Local (Docker Compose)

Best for development and the full multi-container topology (separate Postgres, Redis, API, worker, web).

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- A [Groq](https://console.groq.com) API key (`GROQ_API_KEY`)

### Run

```bash
cp .env.example .env
# Set GROQ_API_KEY in .env

docker compose up --build
```

| Service | URL |
|---------|-----|
| UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

The web container proxies `/api/*` to the API (same-origin from the browser).

### Smoke tests (local)

```bash
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

### Local development (optional, without Docker for app code)

```bash
docker compose up -d postgres redis

python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e packages/inference-sdk
pip install -r apps/api/requirements-dev.txt

cd apps/api && uvicorn app.main:app --reload --port 8000

# separate terminal
cd apps/worker && pip install -r requirements.txt && python worker.py

# separate terminal
cd apps/web && npm install && npm run dev
```

UI: http://localhost:5173 (set `VITE_API_URL=http://localhost:8000` if needed).

---

## Path B — Production (Render + Neon)

Single public URL: UI and API on Render; Postgres on Neon.

### Architecture (production)

```
Browser → Render (FastAPI serves UI + /v1 API)
                ├─ embedded Redis Streams
                ├─ embedded worker
                └─ Neon Postgres
```

Root [`Dockerfile`](./Dockerfile) builds the web UI (`VITE_API_URL=` same-origin), then packs API + worker + Redis + static UI into one image.

### Deploy / redeploy

1. Create a free [Neon](https://neon.tech) Postgres project; copy the connection string.
2. Create a Render **Web Service** from this GitHub repo (Docker, root `Dockerfile`), or use:

```bash
# Requires RENDER_API_KEY from Render → Account Settings → API Keys
# Local .env must contain GROQ_API_KEY, DATABASE_URL, DATABASE_URL_SYNC
powershell -ExecutionPolicy Bypass -File scripts/deploy_render.ps1
```

3. Set these env vars on the Render service:

| Variable | Value |
|----------|--------|
| `GROQ_API_KEY` | your Groq key |
| `DATABASE_URL` | Neon URL (`postgresql://…` or `postgresql+asyncpg://…`) |
| `DATABASE_URL_SYNC` | same Neon URL (`postgresql://…`) |
| `EMBED_WORKER` | `true` |
| `EMBED_REDIS` | `true` |
| `STATIC_DIR` | `/app/static` |
| `CORS_ORIGINS` | `*` (or your exact origin) |
| `DEFAULT_PROVIDER` | `groq` |
| `DEFAULT_MODEL` | `openai/gpt-oss-20b` |

4. Open https://ollive-api.onrender.com

Blueprint reference: [`render.yaml`](./render.yaml).

---

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
- Production packs UI/API/worker/Redis into one Render service for free-tier simplicity; Compose keeps them separate for local fidelity.

## API surface

- `POST /v1/conversations` — create
- `GET /v1/conversations` — list
- `GET /v1/conversations/{id}` — resume/load
- `POST /v1/conversations/{id}/cancel`
- `POST /v1/conversations/{id}/resume`
- `POST /v1/conversations/{id}/chat` — streaming SSE or JSON
- `GET /v1/providers` — available providers/models
- `POST /v1/ingest` — SDK ingestion (single event)
- `POST /v1/ingest/batch` — batch ingestion
- `GET /v1/metrics/summary` — dashboard aggregates
- `GET /v1/inference-events` — recent telemetry

## SDK usage

```python
from inference_sdk import InstrumentedLLM, ChatMessage

llm = InstrumentedLLM(provider="groq", model="openai/gpt-oss-20b")
text = llm.chat(
    [ChatMessage(role="user", content="Hello")],
    conversation_id="...",
)
```

All calls auto-capture metadata and ship to `INGESTION_URL`.

## Kubernetes (advanced / self-hosted)

Compose is the primary local path; Render+Neon is the hosted path. Manifests under `k8s/` are for self-hosted clusters.

```bash
export API_PUBLIC_URL=http://<node-ip>:30800
bash k8s/deploy.sh

# Or manually
kubectl apply -k k8s/
kubectl -n ollive port-forward svc/web 8080:80
```

Update `k8s/secret.yaml` with real API keys before applying to a shared cluster.

## Demo checklist

1. Open the live URL (or local http://localhost:3000)
2. Send a few chat messages (include `user@example.com` to see PII redaction in dashboards)
3. Open **Dashboards** for latency / throughput / errors
4. Use **Stop** mid-stream, then **Resume** to continue the same conversation

## What we’d improve with more time

- Disk-backed SDK retry buffer + exponential backoff
- OpenTelemetry traces linking chat request → provider span → ingest event
- ClickHouse / Timescale for long-range analytics
- AuthN/Z for multi-tenant apps
- Stronger PII (NER-based) + field-level encryption
- Load tests + SLO burn-rate alerts
- Helm chart + Terraform for cloud k8s
- Split UI / API / worker into separate scaled services in production

## License

MIT
