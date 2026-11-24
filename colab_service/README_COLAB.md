# Google Colab T4 GPU — 4-bit Qwen2.5-7B-Instruct Server (3-Cell Quickstart)

Runs **`Qwen/Qwen2.5-7B-Instruct`** in 4-bit NF4 (`bitsandbytes`, `torch.float16` compute) using **~5.5 GB VRAM** on a standard **Colab T4 GPU (15 GB VRAM)** — zero 429 rate limits and native Chinese academic understanding.

### Cell 1 — Clone/Pull `p12` & Install Dependencies
```bash
!git clone -b p12 https://github.com/GHULAMMUSTAFA-JPG/AutoAdmit.git
%cd AutoAdmit
!pip install -q -r colab_service/requirements_colab.txt
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared-linux-amd64.deb
```

### Cell 2 — Set Your Shared `COLAB_API_KEY` (Must Match Oracle `.env`)
```python
import os
os.environ["COLAB_API_KEY"] = "your_exact_colab_api_key_from_oracle_env"
```

### Cell 3 — Launch 4-bit Qwen2.5-7B Server & Cloudflare HTTPS Tunnel
```bash
!bash colab_service/run_colab.sh
```

Copy the printed `https://<random>.trycloudflare.com` URL into `COLAB_BASE_URL` in your Oracle VPS `.env` and restart `autoadmit.service`.
