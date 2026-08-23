@echo off
cd /d "%~dp0"
python -m uvicorn server.main:app --reload
