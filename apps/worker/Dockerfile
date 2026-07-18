FROM python:3.12-slim

WORKDIR /app

COPY apps/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/worker/worker.py /app/worker.py
COPY apps/api/app/services/pii.py /app/app/services/pii.py
COPY apps/api/app/services/__init__.py /app/app/services/__init__.py
COPY apps/api/app/__init__.py /app/app/__init__.py

ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]