# Creates/updates a Render web service via API (real cloud host, not a laptop tunnel).
# Requires: $env:RENDER_API_KEY from https://dashboard.render.com/u/settings#api-keys

param(
  [string]$Repo = "https://github.com/Ashok161/ollive-inference-logger",
  [string]$Branch = "main",
  [string]$ServiceName = "ollive-api"
)

$ErrorActionPreference = "Stop"
if (-not $env:RENDER_API_KEY) {
  Write-Error "Set RENDER_API_KEY first (Render Dashboard -> Account Settings -> API Keys)."
}

$headers = @{
  Authorization = "Bearer $($env:RENDER_API_KEY)"
  Accept        = "application/json"
  "Content-Type" = "application/json"
}

# Load secrets from local .env (gitignored)
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
$groq = ""; $dbAsync = ""; $dbSync = ""
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*GROQ_API_KEY=(.*)$') { $groq = $Matches[1].Trim() }
  if ($_ -match '^\s*DATABASE_URL=(.*)$') { $dbAsync = $Matches[1].Trim() }
  if ($_ -match '^\s*DATABASE_URL_SYNC=(.*)$') { $dbSync = $Matches[1].Trim() }
}
if (-not $groq -or -not $dbAsync -or -not $dbSync) {
  Write-Error ".env missing GROQ_API_KEY / DATABASE_URL / DATABASE_URL_SYNC"
}

$owners = Invoke-RestMethod -Headers $headers -Uri "https://api.render.com/v1/owners"
$owner = @($owners) | Where-Object { $_.owner.type -eq "user" } | Select-Object -First 1
if (-not $owner) { $owner = $owners[0] }
$ownerId = $owner.owner.id
Write-Host "Owner: $ownerId"

$envVars = @(
  @{ key = "EMBED_WORKER"; value = "true" },
  @{ key = "EMBED_REDIS"; value = "true" },
  @{ key = "STATIC_DIR"; value = "/app/static" },
  @{ key = "DEFAULT_PROVIDER"; value = "groq" },
  @{ key = "DEFAULT_MODEL"; value = "openai/gpt-oss-20b" },
  @{ key = "PII_REDACTION_ENABLED"; value = "true" },
  @{ key = "CONTEXT_WINDOW_MESSAGES"; value = "12" },
  @{ key = "CORS_ORIGINS"; value = "*" },
  @{ key = "INGESTION_API_KEY"; value = "prod-ingest-key" },
  @{ key = "GROQ_API_KEY"; value = $groq },
  @{ key = "DATABASE_URL"; value = $dbAsync },
  @{ key = "DATABASE_URL_SYNC"; value = $dbSync }
)

$body = @{
  type = "web_service"
  name = $ServiceName
  ownerId = $ownerId
  repo = $Repo
  branch = $Branch
  autoDeploy = "yes"
  serviceDetails = @{
    env = "docker"
    plan = "free"
    region = "singapore"
    dockerfilePath = "./apps/api/Dockerfile"
    dockerContext = "."
    healthCheckPath = "/health"
    envVars = $envVars
  }
} | ConvertTo-Json -Depth 8

Write-Host "Creating Render service $ServiceName…"
try {
  $created = Invoke-RestMethod -Method POST -Headers $headers -Uri "https://api.render.com/v1/services" -Body $body
  $svc = $created
} catch {
  Write-Host "Create failed, listing existing services…"
  $list = Invoke-RestMethod -Headers $headers -Uri "https://api.render.com/v1/services?limit=50"
  $svc = @($list) | Where-Object { $_.service.name -eq $ServiceName } | Select-Object -First 1
  if (-not $svc) { throw $_ }
}

$serviceId = if ($svc.service.id) { $svc.service.id } else { $svc.id }
$serviceUrl = if ($svc.service.serviceDetails.url) { $svc.service.serviceDetails.url } else { $svc.serviceDetails.url }
Write-Host "Service ID: $serviceId"
Write-Host "URL: $serviceUrl"

# Trigger deploy
Invoke-RestMethod -Method POST -Headers $headers -Uri "https://api.render.com/v1/services/$serviceId/deploys" -Body '{}' | Out-Null
Write-Host "Deploy triggered. Poll /health until live."
Write-Output $serviceUrl
