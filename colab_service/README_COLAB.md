# Google Colab Pro T4 GPU Model Server (3-Cell Quickstart)

Designed for a standard **Colab T4 GPU (15 GB VRAM / 12.7 GB System RAM)** — no High-RAM runtime required.

### Cell 1 — Clone Repo & Install Dependencies
```bash
!git clone -b p12 https://github.com/GHULAMMUSTAFA-JPG/AutoAdmit.git
%cd AutoAdmit
!pip install -q -r colab_service/requirements_colab.txt
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared-linux-amd64.deb
```

### Cell 2 — Set Your Shared Secret Key
```python
import os
os.environ["COLAB_API_KEY"] = "your_strong_shared_secret_here"
```

### Cell 3 — Launch GPU Server & Cloudflare HTTPS Tunnel
```bash
!bash colab_service/run_colab.sh
```

Copy the printed `https://<random>.trycloudflare.com` URL into your Oracle VPS `.env`:
```env
COLAB_BASE_URL=https://<random>.trycloudflare.com
COLAB_API_KEY=your_strong_shared_secret_here
```
