@echo off
rem Lancia ernesto con il Python del .venv del repository, da qualunque cartella.
rem %~dp0 e' la cartella di questo file, quindi non ci sono percorsi assoluti cablati.
rem La cartella di lavoro resta quella corrente: e' la workdir dell'agente.
setlocal
set "PYTHONIOENCODING=utf-8"
set "ERNESTO_HOME=%~dp0."
set "VENV_PY=%ERNESTO_HOME%\.venv\Scripts\python.exe"

rem Un virtualenv non contiene l'interprete: il suo python.exe e' un guscio che
rem cerca la libreria standard nel percorso assoluto scritto in pyvenv.cfg. Se la
rem cartella viene copiata su un altro computer quel percorso non esiste piu', e
rem controllare che il file ci sia non basta: lo si avvia davvero, e se non parte
rem il virtualenv viene ricostruito con il Python di questo computer.
"%VENV_PY%" -c "" >nul 2>&1
if not errorlevel 1 goto :avvia

echo [ernesto] virtualenv assente o inutilizzabile su questo computer: lo ricostruisco.
call :trova_python
if not defined HOST_PY (
  echo [ernesto] nessun Python utilizzabile nel PATH.
  echo [ernesto] installalo da https://www.python.org/downloads/ spuntando
  echo [ernesto] "Add python.exe to PATH", poi rilancia questo comando.
  exit /b 1
)
if exist "%ERNESTO_HOME%\.venv" rmdir /s /q "%ERNESTO_HOME%\.venv"
%HOST_PY% -m venv "%ERNESTO_HOME%\.venv"
if errorlevel 1 (
  echo [ernesto] creazione del virtualenv fallita.
  exit /b 1
)
echo [ernesto] installo le dipendenze da requirements.txt...
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r "%ERNESTO_HOME%\requirements.txt"
if errorlevel 1 (
  echo [ernesto] installazione delle dipendenze fallita: serve una connessione a internet.
  exit /b 1
)
echo [ernesto] virtualenv pronto.

:avvia
"%VENV_PY%" "%ERNESTO_HOME%\ernesto.py" %*
exit /b %errorlevel%

rem Prima il launcher py, che sa scegliere la versione, poi i nomi nel PATH.
rem Ogni candidato viene eseguito davvero perche' su Windows "python" puo' essere
rem il segnaposto del Microsoft Store, che apre il negozio invece di interpretare.
:trova_python
set "HOST_PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined HOST_PY (
    %%~C -c "" >nul 2>&1
    if not errorlevel 1 set "HOST_PY=%%~C"
  )
)
goto :eof
