@echo off
echo ============================================================
echo Starting MongoDB Community Server (No Admin Privileges Needed)
echo ============================================================
"C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe" --dbpath D:\Sch\data\db --bind_ip 127.0.0.1 --port 27017
pause

