@echo off
echo ============================================================
echo Launching AutoAdmit Engine (MongoDB + FastAPI Web Gateway)
echo ============================================================
start "MongoDB Server" "C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe" --dbpath D:\Sch\data\db --bind_ip 127.0.0.1 --port 27017
timeout /t 2 /nobreak >nul
echo.
echo Opening Web Gateway on http://localhost:8000 ...
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
pause

