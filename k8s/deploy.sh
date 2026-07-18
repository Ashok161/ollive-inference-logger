#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Building images…"
# Build web with cluster-reachable API URL (NodePort/Ingress host as needed).
API_PUBLIC_URL="${API_PUBLIC_URL:-http://localhost:8000}"
docker build -t ollive-api:latest -f "$ROOT/apps/api/Dockerfile" "$ROOT"
docker build -t ollive-worker:latest -f "$ROOT/apps/worker/Dockerfile" "$ROOT"
docker build -t ollive-web:latest -f "$ROOT/apps/web/Dockerfile" \
  --build-arg "VITE_API_URL=${API_PUBLIC_URL}" "$ROOT"

if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q .; then
  echo "Loading images into kind…"
  kind load docker-image ollive-api:latest ollive-worker:latest ollive-web:latest
elif command -v minikube >/dev/null 2>&1 && minikube status >/dev/null 2>&1; then
  echo "Loading images into minikube…"
  minikube image load ollive-api:latest
  minikube image load ollive-worker:latest
  minikube image load ollive-web:latest
else
  echo "NOTE: Load images into your cluster manually if needed (kind/minikube/k3s)."
fi

echo "Applying manifests…"
kubectl apply -k "$ROOT/k8s"

echo "Waiting for API…"
kubectl -n ollive rollout status deploy/api
kubectl -n ollive rollout status deploy/web

echo "Done. Web NodePort: http://<node-ip>:30080"
echo "Or: kubectl -n ollive port-forward svc/web 8080:80"