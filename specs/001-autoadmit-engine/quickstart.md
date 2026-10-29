# Quickstart: AutoAdmit Engine

## Prerequisites
1. Python 3.11+
2. MongoDB 6.0+ (Local community server, Docker, or Atlas)
3. Google Gemini API Key (`GEMINI_API_KEY`)
4. SMTP & IMAP credentials (e.g. Gmail App Password or custom academic mail domain)

## Installation & Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. **Run Verification Test Matrix:**
   ```bash
   pytest tests/ -v
   ```

4. **Start the Application:**
   ```bash
   uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
   ```

5. **Access the Dashboard:**
   Open `http://localhost:8000/` in your browser.
   Authenticate using your configured Basic Auth credentials (default: `admin` / `autoadmit2026`).

## Cloud & VPS Deployment (Colab Pro / Nginx / Cloudflare Tunnel)

To expose the dashboard over a secure mobile-friendly HTTPS tunnel:
```bash
cloudflared tunnel --url http://localhost:8000
```
Persistent MongoDB files are automatically directed to `DB_STORAGE_PATH` (e.g. `/content/drive/MyDrive/AutoAdmit_Data/db`).

