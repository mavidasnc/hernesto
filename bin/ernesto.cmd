@echo off
rem Lancia ernesto con il Python del .venv del repository, da qualunque cartella.
rem %~dp0 e' la cartella di questo file, quindi non ci sono percorsi assoluti cablati.
rem La cartella di lavoro resta quella corrente: e' la workdir dell'agente.
setlocal
set "PYTHONIOENCODING=utf-8"
set "ERNESTO_HOME=%~dp0.."
if not exist "%ERNESTO_HOME%\.venv\Scripts\python.exe" (
  echo [ernesto] virtualenv non trovato in %ERNESTO_HOME%\.venv
  echo [ernesto] crealo con: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
"%ERNESTO_HOME%\.venv\Scripts\python.exe" "%ERNESTO_HOME%\ernesto.py" %*
