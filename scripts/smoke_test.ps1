# End-to-end smoke tests for Ollive (PowerShell)
$ErrorActionPreference = "Stop"
$Base = $env:OLLIVE_API_URL
if (-not $Base) { $Base = "http://localhost:8000" }
$IngestKey = if ($env:INGESTION_API_KEY) { $env:INGESTION_API_KEY } else { "dev-ingest-key" }

function Invoke-Json($Method, $Path, $Body = $null, $Headers = @{}) {
  $params = @{
    Uri             = "$Base$Path"
    Method          = $Method
    UseBasicParsing = $true
    TimeoutSec      = 120
    Headers         = $Headers
  }
  if ($null -ne $Body) {
    $params.ContentType = "application/json"
    $params.Body = ($Body | ConvertTo-Json -Depth 10 -Compress)
  }
  $resp = Invoke-WebRequest @params
  return $resp.Content | ConvertFrom-Json
}

$failed = 0
function Assert($cond, $name) {
  if ($cond) {
    Write-Host "PASS  $name" -ForegroundColor Green
  } else {
    Write-Host "FAIL  $name" -ForegroundColor Red
    $script:failed++
  }
}

Write-Host "== Health =="
$health = Invoke-Json GET "/health"
Assert ($health.status -eq "ok") "health"

Write-Host "== Providers =="
$providers = Invoke-Json GET "/v1/providers"
$groq = $providers | Where-Object { $_.id -eq "groq" }
Assert ($groq.configured -eq $true) "groq configured"
Assert ($groq.models -contains "openai/gpt-oss-20b") "gpt-oss-20b listed"
Assert ($groq.models -notcontains "mixtral-8x7b-32768") "mixtral removed from catalog"

Write-Host "== Create conversation =="
$conv = Invoke-Json POST "/v1/conversations" @{ title = "Smoke test"; provider = "groq"; model = "openai/gpt-oss-20b" }
Assert ($null -ne $conv.id) "conversation created"
$cid = $conv.id

Write-Host "== Non-stream chat =="
$chat = Invoke-Json POST "/v1/conversations/$cid/chat" @{
  message  = "Reply with exactly: PONG. Ignore my email alice@example.com"
  stream   = $false
  provider = "groq"
  model    = "openai/gpt-oss-20b"
}
Assert (($chat.content -as [string]).Length -gt 0) "non-stream response non-empty"
Write-Host ("  reply: " + $chat.content.Substring(0, [Math]::Min(80, $chat.content.Length)))

Write-Host "== Multi-turn =="
$chat2 = Invoke-Json POST "/v1/conversations/$cid/chat" @{
  message  = "What was my previous one-word instruction? One word only."
  stream   = $false
  provider = "groq"
  model    = "openai/gpt-oss-20b"
}
Assert (($chat2.content -as [string]).Length -gt 0) "multi-turn response"

Write-Host "== List / resume =="
$list = Invoke-Json GET "/v1/conversations"
$ids = @($list | ForEach-Object { [string]$_.id })
Assert ($ids -contains [string]$cid) "list contains conversation"
$detail = Invoke-Json GET "/v1/conversations/$cid"
Assert ($detail.messages.Count -ge 4) "resume has messages"

Write-Host "== Streaming SSE =="
$streamConv = Invoke-Json POST "/v1/conversations" @{ title = "stream"; provider = "groq"; model = "openai/gpt-oss-20b" }
$streamBody = @{ message = "Say hi in 3 words."; stream = $true; provider = "groq"; model = "openai/gpt-oss-20b" } | ConvertTo-Json -Compress
$streamRaw = Invoke-WebRequest -Uri "$Base/v1/conversations/$($streamConv.id)/chat" -Method POST -ContentType "application/json" -Body $streamBody -UseBasicParsing -TimeoutSec 120
Assert ($streamRaw.Content -match "data:") "SSE stream returns data events"
Assert ($streamRaw.Content -match '"type": "done"' -or $streamRaw.Content -match '"type":"done"') "SSE stream completes"

Write-Host "== Cancel + resume =="
$cancelled = Invoke-Json POST "/v1/conversations/$cid/cancel"
Assert ($cancelled.status -eq "cancelled") "cancel sets status"
try {
  Invoke-Json POST "/v1/conversations/$cid/chat" @{ message = "should fail"; stream = $false } | Out-Null
  Assert $false "chat while cancelled should fail"
} catch {
  Assert $true "chat while cancelled rejected"
}
$resumed = Invoke-Json POST "/v1/conversations/$cid/resume"
Assert ($resumed.status -eq "active") "resume sets active"

Write-Host "== Test each Groq model =="
foreach ($model in $groq.models) {
  $c = Invoke-Json POST "/v1/conversations" @{ title = "model:$model"; provider = "groq"; model = $model }
  try {
    $r = Invoke-Json POST "/v1/conversations/$($c.id)/chat" @{
      message  = "Say OK in one word."
      stream   = $false
      provider = "groq"
      model    = $model
    }
    Assert (($r.content -as [string]).Length -gt 0) "model $model"
    Write-Host ("  $model -> " + $r.content.Substring(0, [Math]::Min(60, $r.content.Length)))
  } catch {
    Write-Host "FAIL  model $model : $($_.Exception.Message)" -ForegroundColor Red
    $failed++
  }
}

Write-Host "== Ingest + metrics + PII =="
Start-Sleep -Seconds 2
$events = Invoke-Json GET "/v1/inference-events?limit=20"
$pii = $events | Where-Object { $_.input_preview -match "REDACTED_EMAIL" }
Assert ($events.Count -ge 1) "inference events present"
Assert ($pii.Count -ge 1) "PII redaction in previews"
$metrics = Invoke-Json GET "/v1/metrics/summary?window_minutes=60"
Assert ($metrics.total_requests -ge 1) "metrics total_requests"

Write-Host "== Direct ingest auth =="
try {
  Invoke-WebRequest -Uri "$Base/v1/ingest" -Method POST -ContentType "application/json" `
    -Body '{"event_id":"x"}' -UseBasicParsing -TimeoutSec 10 | Out-Null
  Assert $false "ingest without key should 401"
} catch {
  Assert ($_.Exception.Response.StatusCode.value__ -eq 401 -or $_.Exception.Message -match "401") "ingest rejects bad key"
}

Write-Host ""
if ($failed -eq 0) {
  Write-Host "ALL SMOKE TESTS PASSED" -ForegroundColor Green
  exit 0
} else {
  Write-Host "$failed SMOKE TEST(S) FAILED" -ForegroundColor Red
  exit 1
}