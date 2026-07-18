FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY packages/inference-sdk /packages/inference-sdk
COPY apps/api/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -e /packages/inference-sdk \
  && pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.34.0" \
    "sqlalchemy[asyncio]==2.0.36" asyncpg==0.30.0 psycopg2-binary==2.9.10 \
    alembic==1.14.0 pydantic==2.10.4 pydantic-settings==2.7.0 httpx==0.28.1 \
    redis==5.2.1 python-dotenv==1.0.1 sse-starlette==2.2.1

COPY apps/api /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]