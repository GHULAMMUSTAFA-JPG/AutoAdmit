#!/usr/bin/env bash
set -euo pipefail

# Fail closed: require COLAB_API_KEY to be explicitly set before launch (never print key)
: "${COLAB_API_KEY:?ERROR: COLAB_API_KEY environment variable must be set before launching colab_server.}"

# 1. Start FastAPI 4-bit NF4 Qwen2.5-7B-Instruct server on 127.0.0.1:8001
python3 -c "
from colab_service.colab_server import app
app.state.registry.load_qwen_4bit()
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8001, log_level='warning')
" &
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT

# 2. Wait for 4-bit Qwen2.5-7B load & run local health self-test without echoing secret
for i in $(seq 1 60); do
  if curl -fsS -H "X-API-Key: ${COLAB_API_KEY}" http://127.0.0.1:8001/health >/tmp/colab_health.json 2>/dev/null; then
    echo "Colab T4 Qwen2.5-7B server healthy: $(cat /tmp/colab_health.json)"
    rm -f /tmp/colab_health.json
    break
  fi
  sleep 2
done

# 3. Expose via Cloudflare HTTPS Quick Tunnel
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8001
