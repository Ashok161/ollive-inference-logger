# --- frontend build (same-origin API calls) ---
FROM node:20-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ENV VITE_API_URL=
RUN npm run build

# --- api + worker + redis + static UI ---
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential redis-server \
  && rm -rf /var/lib/apt/lists/*

COPY packages/inference-sdk /packages/inference-sdk
COPY apps/api/requirements.txt /app/requirements.txt
COPY apps/worker/requirements.txt /app/worker-requirements.txt

RUN pip install --no-cache-dir -e /packages/inference-sdk \
  && pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.34.0" \
    "sqlalchemy[asyncio]==2.0.36" asyncpg==0.30.0 psycopg2-binary==2.9.10 \
    alembic==1.14.0 pydantic==2.10.4 pydantic-settings==2.7.0 httpx==0.28.1 \
    redis==5.2.1 python-dotenv==1.0.1 sse-starlette==2.2.1 \
  && pip install --no-cache-dir -r /app/worker-requirements.txt

COPY apps/api /app
COPY apps/worker/worker.py /app/worker.py
COPY apps/api/start.sh /app/start.sh
COPY --from=web /web/dist /app/static
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV EMBED_WORKER=true
ENV EMBED_REDIS=true
ENV STATIC_DIR=/app/static
EXPOSE 8000

CMD ["/app/start.sh"]
