#!/usr/bin/env bash
# ============================================================================
# DeepSight - Script di Installazione (macOS / Linux)
# ============================================================================
# Crea un ambiente virtuale Python (.venv) nella cartella del progetto e
# installa tutte le dipendenze elencate in requirements.txt.
# Uso: ./install.sh   (rendere eseguibile con: chmod +x install.sh)
# ============================================================================
set -e

echo "============================================================"
echo "  DeepSight - Script di Installazione (macOS / Linux)"
echo "============================================================"
echo

# --- Posizionati nella cartella dello script (radice del progetto) ---
cd "$(dirname "$0")"

# --- Individua un interprete Python (supportate 3.9 - 3.12) ---
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERRORE] Nessun interprete Python 3 trovato nel PATH."
    echo "Installa Python 3.11 o 3.12 da https://www.python.org/downloads/"
    exit 1
fi

PYVER_FULL="$($PYTHON_BIN --version 2>&1)"
echo "Interprete individuato: $PYTHON_BIN ($PYVER_FULL)"

PYVER_MAJOR="$($PYTHON_BIN -c 'import sys; print(sys.version_info[0])')"
PYVER_MINOR="$($PYTHON_BIN -c 'import sys; print(sys.version_info[1])')"
if [ "$PYVER_MAJOR" -ne 3 ] || [ "$PYVER_MINOR" -lt 9 ] || [ "$PYVER_MINOR" -gt 12 ]; then
    echo "[AVVISO] Versione Python $PYVER_MAJOR.$PYVER_MINOR non testata (supportate 3.9 - 3.12, consigliate 3.11 / 3.12)."
fi
echo

# --- Verifica presenza di tkinter (modulo di sistema, non installabile via pip) ---
if ! "$PYTHON_BIN" -c "import tkinter" >/dev/null 2>&1; then
    echo "[ERRORE] Il modulo 'tkinter' non e' disponibile per questo interprete Python."
    echo "         E' un pacchetto di sistema, non installabile con pip. Installalo con:"
    echo "           Ubuntu/Debian : sudo apt-get install python3-tk"
    echo "           Fedora        : sudo dnf install python3-tkinter"
    echo "           macOS (brew)  : brew install python-tk"
    exit 1
fi

# --- Crea l'ambiente virtuale se non esiste ---
if [ -d ".venv" ]; then
    echo "Ambiente virtuale '.venv' gia' presente, salto la creazione."
else
    echo "Creazione ambiente virtuale '.venv' in corso..."
    "$PYTHON_BIN" -m venv .venv
fi
echo

# --- Attiva l'ambiente virtuale ---
# shellcheck disable=SC1091
source .venv/bin/activate

# --- Aggiorna pip e installa le dipendenze ---
echo "Aggiornamento di pip..."
python -m pip install --upgrade pip

echo
echo "Installazione delle dipendenze da requirements.txt..."
echo "(il download dei modelli AI e delle librerie puo' richiedere diversi minuti)"
pip install -r requirements.txt

echo
echo "============================================================"
echo "  Installazione completata con successo!"
echo "============================================================"
echo
echo "Per avviare DeepSight in futuro:"
echo "  1. Apri un terminale in questa cartella"
echo "  2. Esegui: source .venv/bin/activate"
echo "  3. Esegui: python Config_Start/start_app.py"
echo

# Chiede se avviare subito l'app, solo se lo script gira in un terminale interattivo
if [ -t 0 ]; then
    read -r -p "Vuoi avviare DeepSight adesso? (s/N): " AVVIA
    if [[ "$AVVIA" =~ ^[Ss]$ ]]; then
        python Config_Start/start_app.py
    fi
fi
