# Google Colab T4 GPU — 4-bit Qwen2.5-7B-Instruct Server (3-Cell Quickstart)

Runs **`Qwen/Qwen2.5-7B-Instruct`** in 4-bit NF4 (`bitsandbytes`, `torch.float16` compute, pinned to GPU 0) using **~5.5 GB VRAM** on a standard **Colab T4 GPU (15 GB VRAM)** — decoupled from the tunnel so tunnel restarts or Cloudflare `429` rate limits **never** kill the loaded Qwen server.

### Cell 1 — Clone/Pull `p12` & Install Dependencies
```bash
!git clone -b p12 https://github.com/GHULAMMUSTAFA-JPG/AutoAdmit.git || (cd AutoAdmit && git pull origin p12)
%cd AutoAdmit
!pip install -q -r colab_service/requirements_colab.txt
```

### Cell 2 — Set Your Shared `COLAB_API_KEY` (Must Match Oracle `.env`)
```python
import os
os.environ["COLAB_API_KEY"] = "your_exact_colab_api_key_from_oracle_env"
# Optional: speeds up 15.2GB HuggingFace download
# os.environ["HF_TOKEN"] = "hf_..."
# Optional: force tunnel provider ('auto' | 'cloudflared' | 'localhost.run' | 'ngrok')
# os.environ["TUNNEL_PROVIDER"] = "localhost.run"
```

### Cell 3 — Launch Decoupled 4-bit Qwen2.5-7B Server + Auto-Fallback HTTPS Tunnel
```bash
!bash colab_service/run_colab.sh
```
- Starts Qwen detached in the background (`/tmp/colab_qwen.log`) and waits up to 10 minutes for first-time HF Hub download + GPU load.
- Auto-installs `cloudflared` if missing; if `trycloudflare.com` returns `429` on Colab shared IPs, it **keeps Qwen alive** and automatically falls back to **`localhost.run`** (`https://*.lhr.life`).
- Copy the printed HTTPS URL into `COLAB_BASE_URL` in your Oracle VPS `.env` and run `sudo systemctl restart autoadmit`.
