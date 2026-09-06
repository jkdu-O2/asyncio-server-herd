@echo off
cd /d "%~dp0"
start "Bailey" cmd /k python server.py Bailey
start "Bona" cmd /k python server.py Bona
start "Campbell" cmd /k python server.py Campbell
start "Clark" cmd /k python server.py Clark
start "Jaquez" cmd /k python server.py Jaquez
echo All servers launched.