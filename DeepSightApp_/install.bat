@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM  DeepSight - Script di Installazione (Windows)
REM ============================================================================
REM  Crea un ambiente virtuale Python (.venv) nella cartella del progetto e
REM  installa tutte le dipendenze elencate in requirements.txt.
REM
REM  Il progetto richiede specificamente Python 3.12 (alcune dipendenze, come
REM  torch, sono fissate a versioni compatibili solo fino a Python 3.12). Lo
REM  script cerca automaticamente una Python 3.12 gia' installata sul PC; se
REM  non la trova, la scarica e la installa da solo (senza serve i permessi
REM  di amministratore), cosi' funziona anche se sul computer e' presente
REM  solo una versione di Python diversa (es. 3.13/3.14) o nessuna.
REM
REM  Uso: doppio click su install.bat, oppure da terminale: install.bat
REM ============================================================================

echo ============================================================
echo   DeepSight - Script di Installazione (Windows)
echo ============================================================
echo.

REM --- Posizionati nella cartella dello script (radice del progetto) ---
cd /d "%~dp0"

REM ============================================================================
REM  INDIVIDUAZIONE / INSTALLAZIONE AUTOMATICA DI PYTHON 3.12
REM ============================================================================
set "PYEXE="

REM --- 1) Python Launcher (py.exe): se installato, sa trovare qualunque
REM        versione registrata sul sistema, indipendentemente da PATH ---
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    for /f "delims=" %%p in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%p"
)

REM --- 2) Percorsi di installazione standard, nel caso il Launcher non
REM        sia disponibile o non la trovi (es. installazioni non standard) ---
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles(x86)%\Python312\python.exe" set "PYEXE=%ProgramFiles(x86)%\Python312\python.exe"

REM --- 3) Nessuna Python 3.12 trovata: scaricala ed installala in automatico ---
REM     NOTA: dentro un blocco (...) con "setlocal enabledelayedexpansion"
REM     attivo, le variabili impostate ED usate all'interno dello STESSO
REM     blocco vanno lette con !VAR! (espansione ritardata) e non %VAR%
REM     (espansione immediata): %VAR% verrebbe sostituita subito, quando il
REM     blocco viene analizzato come testo, cioe' PRIMA che il "set" al suo
REM     interno sia effettivamente eseguito, risultando quindi vuota.
if not defined PYEXE (
    echo Python 3.12 non trovato sul sistema.
    echo Scaricamento e installazione automatica in corso, potrebbe richiedere
    echo qualche minuto ^(serve una connessione a internet^)...
    echo.

    set "PY_TARGET=%LocalAppData%\Programs\Python\Python312"
    set "PY_INSTALLER=%TEMP%\python-3.12.10-installer.exe"

    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ProgressPreference = 'SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '!PY_INSTALLER!' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"

    if not exist "!PY_INSTALLER!" (
        echo.
        echo [ERRORE] Download di Python 3.12 fallito. Controlla la connessione a
        echo internet, oppure installalo manualmente da:
        echo   https://www.python.org/downloads/release/python-31210/
        echo ^(assicurati di includere il componente "tcl/tk and IDLE"^), poi
        echo rilancia install.bat.
        pause
        exit /b 1
    )

    echo Installazione di Python 3.12 in corso ^(solo per l'utente corrente,
    echo non serve l'amministratore^)...
    set "PY_INSTALL_LOG=%TEMP%\deepsight_python312_install.log"
    set "PY_INSTALL_OK="

    REM Include_launcher=0: il launcher "py.exe" a volte richiede permessi
    REM elevati anche in un'installazione "solo utente corrente", causando
    REM un fallimento silenzioso in modalita' non interattiva (/passive).
    REM Non ci serve: la ricerca di Python in questo script usa comunque il
    REM percorso diretto dell'interprete, non il launcher.
    "!PY_INSTALLER!" /passive /log "!PY_INSTALL_LOG!" InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_tcltk=1 Include_pip=1 Include_test=0 Include_doc=0 TargetDir="!PY_TARGET!"
    set "PY_INSTALL_EXIT=!ERRORLEVEL!"
    del "!PY_INSTALLER!" >nul 2>nul

    REM 0 = successo, 3010 = successo ma richiede riavvio (non bloccante)
    if "!PY_INSTALL_EXIT!"=="0" set "PY_INSTALL_OK=1"
    if "!PY_INSTALL_EXIT!"=="3010" set "PY_INSTALL_OK=1"

    if not defined PY_INSTALL_OK (
        echo.
        echo [ERRORE] Il programma di installazione di Python si e' chiuso con
        echo codice di errore !PY_INSTALL_EXIT!.
        echo Dettagli completi nel log: !PY_INSTALL_LOG!
        echo.
        echo Installalo manualmente da:
        echo   https://www.python.org/downloads/release/python-31210/
        echo ^(assicurati di includere il componente "tcl/tk and IDLE"^), poi
        echo rilancia install.bat.
        pause
        exit /b 1
    )

    if exist "!PY_TARGET!\python.exe" (
        set "PYEXE=!PY_TARGET!\python.exe"
    ) else (
        echo.
        echo [ERRORE] L'installer ha segnalato successo ^(codice !PY_INSTALL_EXIT!^)
        echo ma python.exe non risulta presente in:
        echo   !PY_TARGET!
        echo Controlla il log per i dettagli: !PY_INSTALL_LOG!
        echo.
        echo Installalo manualmente da:
        echo   https://www.python.org/downloads/release/python-31210/
        echo ^(assicurati di includere il componente "tcl/tk and IDLE"^), poi
        echo rilancia install.bat.
        pause
        exit /b 1
    )
    echo.
)

echo Interprete Python 3.12 individuato:
echo   !PYEXE!
"!PYEXE!" --version
echo.

REM --- Verifica presenza di tkinter per QUESTO specifico interprete ---
"!PYEXE!" -c "import tkinter" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERRORE] Il modulo "tkinter" non e' disponibile per l'interprete:
    echo   !PYEXE!
    echo Reinstalla Python 3.12 dal sito ufficiale
    echo https://www.python.org/downloads/release/python-31210/
    echo assicurandoti di includere il componente "tcl/tk and IDLE".
    pause
    exit /b 1
)

REM ============================================================================
REM  CREAZIONE AMBIENTE VIRTUALE (SEMPRE CON QUESTO INTERPRETE 3.12)
REM ============================================================================
if exist ".venv" (
    echo Ambiente virtuale ".venv" gia' presente, salto la creazione.
) else (
    echo Creazione ambiente virtuale ".venv" con Python 3.12 in corso...
    "!PYEXE!" -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo [ERRORE] Creazione ambiente virtuale fallita.
        pause
        exit /b 1
    )
)
echo.

REM --- Da qui in poi si usa SEMPRE l'interprete dentro .venv, chiamato con il
REM     suo percorso completo: non serve "activate.bat" e non si dipende mai
REM     dal PATH di sistema o da quale "python" risulti installato altrove. ---
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

echo Aggiornamento di pip...
"%VENV_PY%" -m pip install --upgrade pip

echo.
echo Installazione delle dipendenze da requirements.txt...
echo (il download dei modelli AI e delle librerie puo' richiedere diversi minuti)
"%VENV_PY%" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRORE] Installazione delle dipendenze fallita. Controlla i messaggi sopra.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installazione completata con successo!
echo ============================================================
echo.
echo Per avviare DeepSight in futuro (ora e nelle prossime volte):
echo   Fai doppio click su DeepSight.bat nella cartella del progetto.
echo.
echo NOTA: DeepSight.bat e' l'UNICO modo supportato per avviare l'app:
echo       non avviarla manualmente con "python Config_Start\start_app.py".
echo.

set /p AVVIA="Vuoi avviare DeepSight adesso? (S/N): "
if /i "%AVVIA%"=="S" (
    call "%~dp0DeepSight.bat"
)

pause
endlocal
