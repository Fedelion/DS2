"""
DeepSight - Script di Avvio
Avvia l'applicazione dalla radice del progetto.
Uso: python start_app.py
"""

import os
import sys

# Aggiunge la cartella UI al path per gli import relativi
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR   = os.path.join(BASE_DIR, "UI")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, UI_DIR)

# Verifica dipendenze critiche
def _is_conda_env():
    """Controlla se siamo in un ambiente conda."""
    return (os.environ.get("CONDA_DEFAULT_ENV") is not None
            or os.path.exists(os.path.join(sys.prefix, "conda-meta")))

def controlla_dipendenze():
    """
    Verifica che tutte le librerie esterne necessarie per il funzionamento dell'app
    siano installate nell'ambiente Python corrente. Se manca qualche dipendenza
    o c'è un'incompatibilità di versione, stampa a schermo il comando di
    installazione suggerito (pip o conda) e interrompe l'avvio.
    """
    # modulo_python -> (pacchetto_pip, pacchetto_conda)
    dipendenze = {
        "customtkinter": ("customtkinter",      "customtkinter"),
        "PIL":           ("pillow",              "pillow"),
        "duckdb":        ("duckdb",              "python-duckdb"),
        "chromadb":      ("chromadb",            "chromadb"),
        "torch":         ("torch",               "pytorch"),
        "transformers":  ("transformers",        "transformers"),
        "cv2":           ("opencv-python-headless", "opencv"),
        "easyocr":       ("easyocr",             "easyocr"),
        "matplotlib":    ("matplotlib",          "matplotlib"),
        "deep_translator": ("deep_translator",   "deep_translator"),
        "facenet_pytorch": ("facenet-pytorch",   "facenet-pytorch"),
        "requests":      ("requests",            "requests"),
    }

    in_conda = _is_conda_env()
    mancanti = []       # (pip_name, conda_name)
    incompatibili = []  # (modulo, messaggio_errore)

    for modulo, (pip_pkg, conda_pkg) in dipendenze.items():
        try:
            __import__(modulo)
        except ImportError:
            mancanti.append((pip_pkg, conda_pkg))
        except Exception as e:
            # Gestisce errori di incompatibilità (es. NumPy 1.x vs 2.x con torch)
            incompatibili.append((modulo, pip_pkg, conda_pkg, str(e)))

    errori = False

    if incompatibili:
        errori = True
        print("\n[!] Librerie con problemi di compatibilita':")
        for modulo, pip_pkg, conda_pkg, msg in incompatibili:
            print(f"\n   [X] '{modulo}' -- errore durante l'import:")
            # Mostra solo le prime 3 righe dell'errore per leggibilità
            for line in msg.splitlines()[:3]:
                print(f"      {line}")
            if "numpy" in msg.lower():
                print(f"\n   [*] Soluzione: aggiornare/reinstallare il pacchetto per allinearlo a NumPy.")
                if in_conda:
                    print(f"      conda install numpy \"pytorch>=2.0\" -c pytorch")
                else:
                    print(f"      pip install \"numpy<2\" oppure pip install --upgrade {pip_pkg}")

    if mancanti:
        errori = True
        print("\n[!] Dipendenze mancanti:")
        if in_conda:
            nomi_conda = " ".join(c for _, c in mancanti)
            print(f"\n   conda install {nomi_conda}")
            print("   (oppure con pip):")
        for pip_pkg, _ in mancanti:
            print(f"   pip install {pip_pkg}")

    if errori:
        print(f"\n   Python in uso: {sys.executable}")
        if in_conda:
            env_name = os.environ.get("CONDA_DEFAULT_ENV", os.path.basename(sys.prefix))
            print(f"   Ambiente conda: {env_name}")
        print("\nCorreggere gli errori sopra e riprovare.")
        sys.exit(1)
    else:
        print("[OK] Tutte le dipendenze sono presenti.")

def _verifica_avvio_da_launcher():
    """
    Su Windows, DeepSight deve essere avviato esclusivamente tramite
    DeepSight.bat (che imposta la variabile d'ambiente DEEPSIGHT_LAUNCHER).
    Questo evita avvii "sparsi" da altri script/scorciatoie e garantisce che
    l'ambiente virtuale e i controlli pre-avvio siano sempre quelli corretti.
    Su macOS/Linux (nessun equivalente .bat) l'avvio diretto resta consentito.
    """
    if os.name == "nt" and os.environ.get("DEEPSIGHT_LAUNCHER") != "1":
        print("\n[ERRORE] DeepSight va avviato tramite DeepSight.bat.")
        print("         Fai doppio click su DeepSight.bat nella cartella del")
        print("         progetto (oppure eseguilo da terminale).")
        print("         Se non hai ancora installato l'app, esegui prima install.bat.\n")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 50)
    print("  DeepSight - Multimedia Intelligence System")
    print("=" * 50)
    _verifica_avvio_da_launcher()
    controlla_dipendenze()
    print(" Avvio interfaccia grafica...")

    from UI.home import DeepSightApp
    app = DeepSightApp()
    app.mainloop()