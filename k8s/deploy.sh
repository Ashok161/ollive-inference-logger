#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Building images…"
docker build -t ollive-api:latest -f "$ROOT/apps/api/Dockerfile" "$ROOT"
docker build -t ollive-worker:latest -f "$ROOT/apps/worker/Dockerfile" "$ROOT"
docker build -t ollive-web:latest -f "$ROOT/apps/web/Dockerfile" "$ROOT"

# For kind: kind load docker-image ollive-api:latest ollive-worker:latest ollive-web:latest
# For minikube: minikube image load ollive-api:latest && ...

echo "Applying manifests…"
kubectl apply -k "$ROOT/k8s"

echo "Waiting for API…"
kubectl -n ollive rollout status deploy/api
kubectl -n ollive rollout status deploy/web

echo "Done. Web NodePort: http://<node-ip>:30080"
echo "Or: kubectl -n ollive port-forward svc/web 8080:80"