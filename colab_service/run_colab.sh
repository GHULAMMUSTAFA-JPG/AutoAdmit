#!/usr/bin/env bash
set -uo pipefail

# Fail closed: require COLAB_API_KEY to be explicitly set before launch (never print key)
: "${COLAB_API_KEY:?ERROR: COLAB_API_KEY environment variable must be set before launching colab_server.}"

PORT="${COLAB_PORT:-8001}"
LOG_FILE="/tmp/colab_qwen.log"
PID_FILE="/tmp/colab_qwen.pid"
WAIT_TIMEOUT_SEC="${COLAB_LOAD_TIMEOUT_SEC:-600}"
TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-auto}"  # auto | cloudflared | localhost.run | ngrok

# ---------------------------------------------------------------------------
# STEP 1: Decoupled Qwen2.5-7B Server Launch (NEVER killed by tunnel failure)
# ---------------------------------------------------------------------------
if curl -fsS -H "X-API-Key: ${COLAB_API_KEY}" "http://127.0.0.1:${PORT}/health" >/tmp/colab_health.json 2>/dev/null; then
  echo "[OK] Existing Qwen2.5-7B server already healthy on 127.0.0.1:${PORT}: $(cat /tmp/colab_health.json)"
  rm -f /tmp/colab_health.json
else
  echo "[1/3] Starting detached 4-bit Qwen/Qwen2.5-7B-Instruct server on 127.0.0.1:${PORT}..."
  echo "      Logs: ${LOG_FILE} (first-time HF Hub download ~15.2GB takes 2-5 min; set HF_TOKEN for faster speeds)"
  nohup python3 -u -c "
from colab_service.colab_server import app
app.state.registry.load_qwen_4bit()
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=int('${PORT}'), log_level='warning')
" >"${LOG_FILE}" 2>&1 &
  SERVER_PID=$!
  echo "${SERVER_PID}" > "${PID_FILE}"

  # Poll up to WAIT_TIMEOUT_SEC (default 600s); detect early crash via kill -0
  ELAPSED=0
  READY=0
  while [ "${ELAPSED}" -lt "${WAIT_TIMEOUT_SEC}" ]; do
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      echo "[ERROR] Qwen server process (PID ${SERVER_PID}) exited unexpectedly! Last 30 log lines:"
      tail -n 30 "${LOG_FILE}"
      exit 1
    fi
    if curl -fsS -H "X-API-Key: ${COLAB_API_KEY}" "http://127.0.0.1:${PORT}/health" >/tmp/colab_health.json 2>/dev/null; then
      echo "[OK] Qwen2.5-7B server ready after ${ELAPSED}s: $(cat /tmp/colab_health.json)"
      rm -f /tmp/colab_health.json
      READY=1
      break
    fi
    if [ $((ELAPSED % 20)) -eq 0 ] && [ "${ELAPSED}" -gt 0 ]; then
      echo "      Still downloading/loading Qwen (${ELAPSED}s / ${WAIT_TIMEOUT_SEC}s)..."
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
  done

  if [ "${READY}" -ne 1 ]; then
    echo "[ERROR] Timed out waiting ${WAIT_TIMEOUT_SEC}s for Qwen server (PID ${SERVER_PID} is STILL running in background)."
    echo "        Check progress with: tail -n 30 ${LOG_FILE}"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# STEP 2: Auto-install cloudflared if missing (AMD64/ARM64)
# ---------------------------------------------------------------------------
ensure_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  echo "[2/3] cloudflared not found — auto-installing to /usr/local/bin/cloudflared..."
  local arch="amd64"
  [ "$(uname -m)" = "aarch64" ] && arch="arm64"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}" -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
}

# ---------------------------------------------------------------------------
# STEP 3: Start Public HTTPS Tunnel (Decoupled — failure NEVER kills Qwen!)
# ---------------------------------------------------------------------------
start_localhost_run() {
  local sync_url="${ORACLE_SYNC_URL:-https://catalogue-tutorial-ending-homepage.trycloudflare.com/api/v1/admin/colab-url}"
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
    echo "[WARN] localhost.run tunnel disconnected; Qwen stays loaded in VRAM. Reconnecting in 2s..."
    sleep 2
  done
}

start_ngrok() {
  echo "[3/3] Starting ngrok HTTPS tunnel..."
  python3 -c "
import os, time
from pyngrok import ngrok
ngrok.set_auth_token(os.environ['NGROK_AUTHTOKEN'])
tun = ngrok.connect(int('${PORT}'), 'http')
print('NGROK PUBLIC URL:', tun.public_url, flush=True)
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
  echo "[3/3] Starting Cloudflare Quick Tunnel (auto-falls back to localhost.run if trycloudflare returns 429)..."
  for attempt in 1 2; do
    cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" 2>&1 | tee /tmp/cloudflared_run.log
    if grep -q "429" /tmp/cloudflared_run.log 2>/dev/null; then
      echo "[WARN] trycloudflare.com returned HTTP 429 (attempt ${attempt}/2). Qwen server (PID $(cat "${PID_FILE}" 2>/dev/null || echo running)) stays alive!"
      sleep 5
    else
      break
    fi
  done
  echo "[INFO] Switching automatically to localhost.run HTTPS tunnel (Qwen server remains running)..."
  start_localhost_run
fi
