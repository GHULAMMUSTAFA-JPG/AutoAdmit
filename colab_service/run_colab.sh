#!/usr/bin/env bash
set -uo pipefail

# Fail closed: require COLAB_API_KEY to be explicitly set before launch (never print key)
: "${COLAB_API_KEY:?ERROR: COLAB_API_KEY environment variable must be set before launching colab_server.}"

PORT="${COLAB_PORT:-8001}"
VLLM_PORT="${VLLM_PORT:-8002}"
COLAB_MODEL="${COLAB_MODEL:-Qwen/Qwen3-8B-AWQ}"
VLLM_LOG_FILE="/tmp/colab_vllm.log"
PROXY_LOG_FILE="/tmp/colab_proxy.log"
VLLM_PID_FILE="/tmp/colab_vllm.pid"
PROXY_PID_FILE="/tmp/colab_proxy.pid"
WAIT_TIMEOUT_SEC="${COLAB_LOAD_TIMEOUT_SEC:-600}"
TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-auto}"  # auto | cloudflared | localhost.run | ngrok
ORACLE_SYNC_URL="${ORACLE_SYNC_URL:-https://catalogue-tutorial-ending-homepage.trycloudflare.com/api/v1/admin/colab-url}"

# ---------------------------------------------------------------------------
# STEP 1A: Launch vLLM OpenAI-Compatible Engine on internal 127.0.0.1:8002
# ---------------------------------------------------------------------------
if curl -fsS "http://127.0.0.1:${VLLM_PORT}/v1/models" >/tmp/vllm_models.json 2>/dev/null; then
  echo "[OK] Existing vLLM server already healthy on 127.0.0.1:${VLLM_PORT}"
  rm -f /tmp/vllm_models.json
else
  echo "[1/3] Starting detached vLLM engine (${COLAB_MODEL}) on 127.0.0.1:${VLLM_PORT}..."
  echo "      Logs: ${VLLM_LOG_FILE} (first-time HF download takes 2-4 min; set HF_TOKEN for faster speeds)"
  QUANT_ARGS=()
  if echo "${COLAB_MODEL}" | grep -qi "awq"; then
    QUANT_ARGS=(--quantization awq)
  fi
  VLLM_USE_V1=0 nohup python3 -m vllm.entrypoints.openai.api_server \
    --model "${COLAB_MODEL}" \
    --host 127.0.0.1 \
    --port "${VLLM_PORT}" \
    --dtype half \
    "${QUANT_ARGS[@]}" \
    --enforce-eager \
    --gpu-memory-utilization 0.88 \
    --max-model-len 4096 \
    --max-num-seqs 4 \
    --max-num-batched-tokens 2048 \
    --enable-prefix-caching \
    >"${VLLM_LOG_FILE}" 2>&1 &
  VLLM_PID=$!
  echo "${VLLM_PID}" > "${VLLM_PID_FILE}"

  ELAPSED=0
  READY=0
  while [ "${ELAPSED}" -lt "${WAIT_TIMEOUT_SEC}" ]; do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
      echo "[ERROR] vLLM server (PID ${VLLM_PID}) exited unexpectedly! Last 35 log lines:"
      tail -n 35 "${VLLM_LOG_FILE}"
      exit 1
    fi
    if curl -fsS "http://127.0.0.1:${VLLM_PORT}/v1/models" >/dev/null 2>&1; then
      echo "[OK] vLLM engine ready after ${ELAPSED}s on 127.0.0.1:${VLLM_PORT}"
      READY=1
      break
    fi
    if [ $((ELAPSED % 20)) -eq 0 ] && [ "${ELAPSED}" -gt 0 ]; then
      echo "      Still loading vLLM (${ELAPSED}s / ${WAIT_TIMEOUT_SEC}s)..."
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
  done

  if [ "${READY}" -ne 1 ]; then
    echo "[ERROR] Timed out waiting ${WAIT_TIMEOUT_SEC}s for vLLM (PID ${VLLM_PID} still running). Check: tail -n 30 ${VLLM_LOG_FILE}"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# STEP 1B: Launch Lightweight FastAPI Auth & Health Proxy on 127.0.0.1:8001
# ---------------------------------------------------------------------------
if curl -fsS -H "X-API-Key: ${COLAB_API_KEY}" "http://127.0.0.1:${PORT}/health" >/tmp/colab_health.json 2>/dev/null; then
  echo "[OK] Existing Auth Proxy already healthy on 127.0.0.1:${PORT}: $(cat /tmp/colab_health.json)"
  rm -f /tmp/colab_health.json
else
  echo "[2/3] Starting FastAPI X-API-Key auth proxy on 127.0.0.1:${PORT} -> vLLM 127.0.0.1:${VLLM_PORT}..."
  COLAB_MODEL="${COLAB_MODEL}" VLLM_BACKEND_URL="http://127.0.0.1:${VLLM_PORT}" COLAB_API_KEY="${COLAB_API_KEY}" \
    nohup python3 -u -m uvicorn colab_service.colab_server:app --host 127.0.0.1 --port "${PORT}" --log-level warning \
    >"${PROXY_LOG_FILE}" 2>&1 &
  PROXY_PID=$!
  echo "${PROXY_PID}" > "${PROXY_PID_FILE}"

  for i in $(seq 1 20); do
    if curl -fsS -H "X-API-Key: ${COLAB_API_KEY}" "http://127.0.0.1:${PORT}/health" >/tmp/colab_health.json 2>/dev/null; then
      echo "[OK] Colab vLLM Proxy ready: $(cat /tmp/colab_health.json)"
      rm -f /tmp/colab_health.json
      break
    fi
    sleep 1
  done
fi

# ---------------------------------------------------------------------------
# STEP 2: Auto-install cloudflared if missing (AMD64/ARM64)
# ---------------------------------------------------------------------------
ensure_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  echo "[INFO] Auto-installing cloudflared to /usr/local/bin/cloudflared..."
  local arch="amd64"
  [ "$(uname -m)" = "aarch64" ] && arch="arm64"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}" -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
}

# ---------------------------------------------------------------------------
# STEP 3: Auto-Reconnecting & Auto-Syncing Public HTTPS Tunnel
# ---------------------------------------------------------------------------
start_localhost_run() {
  local sync_url="${ORACLE_SYNC_URL}"
  echo "[3/3] Starting auto-reconnecting + auto-syncing HTTPS tunnel via localhost.run..."
  echo "      Auto-sync target: ${sync_url}"
  while true; do
    ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R "80:127.0.0.1:${PORT}" nokey@localhost.run -- --output json 2>&1 | python3 -u -c "
import json, os, sys, urllib.request

sync_url = os.environ.get('ORACLE_SYNC_URL', '${sync_url}').strip()
api_key = os.environ.get('COLAB_API_KEY', '').strip()

for raw in sys.stdin:
    line = raw.strip()
    if not line.startswith('{'):
        if line and 'Welcome to' not in line and 'admin.localhost.run' not in line:
            print(line, flush=True)
        continue
    try:
        ev = json.loads(line)
    except Exception:
        continue
    if ev.get('type') == 'run.localhost.tunnel.registered':
        addr = (ev.get('data') or {}).get('address') or ev.get('subject')
        if addr:
            url = f'https://{addr}'
            print(f'[TUNNEL LIVE] {url}', flush=True)
            if sync_url and api_key:
                try:
                    req = urllib.request.Request(
                        sync_url,
                        data=json.dumps({'base_url': url}).encode('utf-8'),
                        headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
                        method='POST',
                    )
                    with urllib.request.urlopen(req, timeout=10) as r:
                        print(f'[AUTO-SYNC OK] Oracle VPS updated -> {url} ({r.status})', flush=True)
                except Exception as exc:
                    print(f'[AUTO-SYNC WARN] Failed to sync {url}: {exc}', flush=True)
" || true
    echo "[WARN] localhost.run tunnel disconnected; vLLM stays loaded in VRAM. Reconnecting in 2s..."
    sleep 2
  done
}

start_ngrok() {
  echo "[3/3] Starting ngrok HTTPS tunnel..."
  python3 -c "
import json, os, time, urllib.request
from pyngrok import ngrok
ngrok.set_auth_token(os.environ['NGROK_AUTHTOKEN'])
tun = ngrok.connect(int('${PORT}'), 'http')
print('NGROK PUBLIC URL:', tun.public_url, flush=True)
sync_url = os.environ.get('ORACLE_SYNC_URL', '${ORACLE_SYNC_URL}').strip()
api_key = os.environ.get('COLAB_API_KEY', '').strip()
if sync_url and api_key:
    try:
        req = urllib.request.Request(
            sync_url,
            data=json.dumps({'base_url': tun.public_url}).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f'[AUTO-SYNC OK] Oracle VPS updated -> {tun.public_url} ({r.status})', flush=True)
    except Exception as exc:
        print(f'[AUTO-SYNC WARN] {exc}', flush=True)
while True:
    time.sleep(60)
"
}

if [ "${TUNNEL_PROVIDER}" = "ngrok" ] || { [ "${TUNNEL_PROVIDER}" = "auto" ] && [ -n "${NGROK_AUTHTOKEN:-}" ]; }; then
  start_ngrok
elif [ "${TUNNEL_PROVIDER}" = "localhost.run" ]; then
  start_localhost_run
else
  ensure_cloudflared
  echo "[3/3] Starting Cloudflare Quick Tunnel (auto-falls back to localhost.run on 429)..."
  for attempt in 1 2; do
    cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" 2>&1 | tee /tmp/cloudflared_run.log
    if grep -q "429" /tmp/cloudflared_run.log 2>/dev/null; then
      echo "[WARN] trycloudflare.com returned HTTP 429 (attempt ${attempt}/2). vLLM stays alive!"
      sleep 5
    else
      break
    fi
  done
  echo "[INFO] Switching automatically to localhost.run HTTPS tunnel..."
  start_localhost_run
fi
