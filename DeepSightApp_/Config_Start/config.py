"""
DeepSight - File di configurazione centralizzato
Tutti i path e parametri dell'applicazione sono definiti qui.
Questo modulo viene importato dalle altre parti del programma per avere
accesso a variabili costanti condivise, come le cartelle di salvataggio,
le impostazioni del modello AI e i formati supportati.
"""

import os

# ──────────────────────────────────────────────
#  PATH PRINCIPALI
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Storage file multimediali
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
IMG_DIR     = os.path.join(UPLOAD_DIR, "immagini")
VIDEO_DIR   = os.path.join(UPLOAD_DIR, "video")

# Database
DB_DIR      = os.path.join(BASE_DIR, "Database")
DB_PATH     = os.path.join(DB_DIR, "deepsight.db")          # DuckDB
CHROMA_DIR  = os.path.join(DB_DIR, "chroma_vectors")         # ChromaDB

# UI assets
DOCS_DIR    = os.path.join(BASE_DIR, "UI", "documents")

# ──────────────────────────────────────────────
#  PARAMETRI AI
# ──────────────────────────────────────────────
CLIP_MODEL_NAME         = "openai/clip-vit-base-patch32"
# EasyOCR config
OCR_LANGUAGES           = ['it', 'en']
CLIP_EMBEDDING_DIM      = 512       # dimensione embedding CLIP

# ──────────────────────────────────────────────
#  PARAMETRI STORAGE
# ──────────────────────────────────────────────
TOTAL_STORAGE_GB        = 500.0
MAX_UPLOAD_MB           = 200

# ──────────────────────────────────────────────
#  ESTENSIONI SUPPORTATE
# ──────────────────────────────────────────────
ESTENSIONI_IMMAGINI = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
ESTENSIONI_VIDEO    = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv')

# ──────────────────────────────────────────────
#  CREA CARTELLE SE NON ESISTONO
# ──────────────────────────────────────────────
for _d in [IMG_DIR, VIDEO_DIR, DB_DIR, CHROMA_DIR]:
    os.makedirs(_d, exist_ok=True)