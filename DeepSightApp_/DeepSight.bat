@echo off
REM ============================================================================
REM  DeepSight - Avvio Applicazione (Windows)
REM ============================================================================
REM  Questo e' l'UNICO script da usare per avviare DeepSight su Windows.
REM  Non avviare l'app tramite "python Config_Start\start_app.py" a mano,
REM  ne' tramite install.bat: usa sempre DeepSight.bat (doppio click, oppure
REM  da terminale: DeepSight.bat).
REM
REM  Se non hai ancora installato l'ambiente virtuale e le dipendenze, esegui
REM  prima install.bat.
REM ============================================================================

setlocal

REM --- Posizionati nella cartella dello script (radice del progetto) ---
cd /d "%~dp0"

REM --- Punta SEMPRE all'interprete dentro .venv, mai al "python" di sistema ---
REM     Chiamare direttamente .venv\Scripts\python.exe (invece di passare da
REM     activate.bat + il comando "python") non dipende dal PATH: funziona
REM     in modo identico anche se sul PC e' installata un'altra versione di
REM     Python come predefinita, o se "python" punta altrove.
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo ============================================================
    echo   DeepSight - Ambiente non trovato
    echo ============================================================
    echo.
    echo [ERRORE] Ambiente virtuale ".venv" non trovato o incompleto
    echo ^(manca %VENV_PY%^).
    echo Esegui prima install.bat per installare DeepSight, poi riprova
    echo avviando DeepSight.bat.
    echo.
    pause
    exit /b 1
)

REM --- Marca il processo come avviato correttamente da questo launcher ---
set "DEEPSIGHT_LAUNCHER=1"

echo ============================================================
echo   DeepSight - Avvio in corso...
echo ============================================================
echo.

"%VENV_PY%" "%~dp0Config_Start\start_app.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERRORE] DeepSight si e' chiuso con un errore ^(codice %EXIT_CODE%^).
    pause
)

endlocal
