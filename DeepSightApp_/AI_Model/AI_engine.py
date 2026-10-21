"""
DeepSight - AI Engine (Lazy Loading)
Fornisce:
  - Embedding CLIP per immagini e testo (ricerca semantica)
  - OCR con EasyOCR (estrazione testo da immagini)
  - Estrazione metadata EXIF (data, GPS)
  - Elaborazione video (estrazione frame campionati)
  - Riconoscimento facciale con FaceNet (MTCNN + InceptionResnetV1):
      * Rilevamento facce e conteggio (num_facce)
      * Generazione embedding facciale normalizzato (512 float) per ricerca per identità
I modelli vengono caricati solo al primo utilizzo per non bloccare l'avvio.
"""

import os
import sys
import cv2
import torch
import tempfile
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Permette import dalla radice del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import Config_Start.config as config

# ──────────────────────────────────────────────────────────────────────
#  LAZY LOADING DEI MODELLI
# ──────────────────────────────────────────────────────────────────────
_clip_model     = None
_clip_processor = None
_ocr_reader     = None
_mtcnn          = None
_facenet        = None


def _carica_clip():
    """
    Carica i modelli CLIP di HuggingFace (una sola volta) al primo utilizzo.
    Questa tecnica (Lazy Loading) evita che l'applicazione si blocchi o impieghi
    troppo tempo ad avviarsi all'apertura iniziale.

    NOTA sulla cache: per default `from_pretrained` contatta comunque
    huggingface.co ad ogni caricamento per verificare se ci sono aggiornamenti
    dei file (anche se il modello è già scaricato in cache). Con una
    connessione assente/lenta questo causa lunghi timeout e ritentativi
    (fino a ~30s) ad ogni "Salva e Analizza". Per evitarlo, se il modello è
    già presente in cache locale lo carichiamo subito in modalità
    "local_files_only" (nessuna chiamata di rete); solo se non è ancora stato
    scaricato (primo utilizzo in assoluto) ricadiamo sul caricamento online
    standard, che richiede la connessione una tantum per il download.
    """
    global _clip_model, _clip_processor
    if _clip_model is None:
        from transformers import CLIPModel, CLIPProcessor
        print("[AI] Caricamento CLIP in corso...")
        try:
            _clip_processor = CLIPProcessor.from_pretrained(
                config.CLIP_MODEL_NAME, local_files_only=True
            )
            _clip_model = CLIPModel.from_pretrained(
                config.CLIP_MODEL_NAME, local_files_only=True
            )
            print("[AI] CLIP caricato dalla cache locale (nessuna richiesta di rete).")
        except Exception:
            print("[AI] CLIP non ancora in cache locale: scaricamento da HuggingFace Hub "
                  "in corso (richiede connessione, solo la prima volta)...")
            _clip_processor = CLIPProcessor.from_pretrained(config.CLIP_MODEL_NAME)
            _clip_model     = CLIPModel.from_pretrained(config.CLIP_MODEL_NAME)
        _clip_model.eval()
        print("[AI] CLIP caricato.")
    return _clip_model, _clip_processor


def _carica_ocr():
    """
    Carica la libreria EasyOCR per l'estrazione di testo dalle immagini (una sola volta).
    Utilizza l'accelerazione GPU (CUDA) se disponibile.
    """
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("[AI] Caricamento EasyOCR in corso...")
        _ocr_reader = easyocr.Reader(config.OCR_LANGUAGES, gpu=torch.cuda.is_available())
        print("[AI] EasyOCR caricato.")
    return _ocr_reader


def _carica_facenet():
    """
    Carica i modelli MTCNN e InceptionResnetV1 per il riconoscimento facciale (una sola volta) al primo utilizzo.
    """
    global _mtcnn, _facenet
    if _mtcnn is None or _facenet is None:
        from facenet_pytorch import MTCNN, InceptionResnetV1
        print("[AI] Caricamento FaceNet (MTCNN + InceptionResnetV1) in corso...")
        _mtcnn = MTCNN(keep_all=True, device='cuda' if torch.cuda.is_available() else 'cpu')
        _facenet = InceptionResnetV1(pretrained='vggface2').eval()
        print("[AI] FaceNet caricato.")
    return _mtcnn, _facenet


# ──────────────────────────────────────────────────────────────────────
#  EMBEDDING CLIP
# ──────────────────────────────────────────────────────────────────────
def _extract_tensor(output):
    """
    Normalizza l'output di get_image_features / get_text_features per renderlo
    compatibile con versioni diverse di transformers.
    - Versioni recenti restituiscono un oggetto BaseModelOutputWithPooling
      al posto di un tensore grezzo: in quel caso si usa .pooler_output.
    - Versioni precedenti restituiscono direttamente il tensore.
    """
    if isinstance(output, torch.Tensor):
        return output
    # Oggetto strutturato (es. BaseModelOutputWithPooling)
    if hasattr(output, "pooler_output") and output.pooler_output is not None:
        return output.pooler_output
    if hasattr(output, "last_hidden_state"):
        # Usa il token [CLS] (primo token)
        return output.last_hidden_state[:, 0, :]
    raise ValueError(f"[AI] Formato output CLIP non riconosciuto: {type(output)}")

def genera_embedding_immagine(percorso_img):
    """
    Legge un'immagine e utilizza il modello CLIP per generare un vettore di 
    caratteristiche visive (embedding di dimensione 512). 
    Questo vettore viene normalizzato per permettere il calcolo della similarità
    coseno durante la ricerca visiva inversa.
    Restituisce una lista di float (dim 512) o None in caso di errore.
    """
    try:
        model, processor = _carica_clip()
        img = Image.open(percorso_img).convert("RGB")
        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            raw = model.get_image_features(**inputs)
        embedding = _extract_tensor(raw).squeeze()
        # Normalizza il vettore (cosine similarity)
        embedding = embedding / embedding.norm()
        return embedding.tolist()
    except Exception as e:
        print(f"[AI] Errore embedding immagine ({percorso_img}): {e}")
        return None


def genera_embedding_testo(testo):
    """
    Questa funzione è molto simile a quella precedente, ma invece di generare un embedding per un'immagine, genera un embedding per una stringa di testo.
    Poiché il modello CLIP ha prestazioni notevolmente superiori con l'inglese,
    traduce prima la stringa in inglese.
    Restituisce una lista di float (512 elementi) o None in caso di errore.
    """
    try:
        from deep_translator import GoogleTranslator
        
        # Dizionario per correggere le traduzioni ambigue più comuni in italiano
        ambiguita = {
            "macchina": "car",
            "macchine": "cars"
        }
        testo_pulito = testo.strip().lower()
        
        if testo_pulito in ambiguita:
            testo_en = ambiguita[testo_pulito]
            print(f"[AI] Correzione ambiguità italiana: '{testo}' -> '{testo_en}'")
        else:
            testo_en = GoogleTranslator(source='it', target='en').translate(testo)
            print(f"[AI] Traduzione query per CLIP: '{testo}' -> '{testo_en}'")
            
        # Prompt ensembling: per uniformare lo score tra foto naturali, render in studio e primi piani.
        prompts = [
            f"a photo of a {testo_en}",
            f"a clean studio photo of a {testo_en}",
            f"a close-up of a {testo_en}",
            f"a rendering of a {testo_en}",
            testo_en
        ]
        print(f"[AI] Query ottimizzata con {len(prompts)} contesti visivi (Prompt Ensembling)")
    except Exception as e:
        print(f"[AI] Errore traduzione (uso originale): {e}")
        prompts = [testo]

    try:
        model, processor = _carica_clip()
        inputs = processor(text=prompts, return_tensors="pt", padding=True)
        with torch.no_grad():
            raw = model.get_text_features(**inputs)
        
        # Media vettoriale di tutti i prompt (Ensembling)
        features = _extract_tensor(raw)
        if len(features.shape) > 1 and features.shape[0] > 1:
            embedding = features.mean(dim=0).squeeze()
        else:
            embedding = features.squeeze()
            
        embedding = embedding / embedding.norm()
        return embedding.tolist()
    except Exception as e:
        print(f"[AI] Errore embedding testo: {e}")
        return None

# ──────────────────────────────────────────────────────────────────────
#  RICONOSCIMENTO FACCIALE
# ──────────────────────────────────────────────────────────────────────
def genera_embedding_facciale(percorso_img):
    """
    Rileva le facce all'interno del file immagine fornito e restituisce l'embedding
    della prima faccia rilevata come lista di float (512 elementi).
    Ritorna None se non viene trovata alcuna faccia o in caso di errore.
    """
    try:
        mtcnn, facenet = _carica_facenet()
        img = Image.open(percorso_img).convert("RGB")
        faces = mtcnn(img)
        if faces is None or len(faces) == 0:
            return None
        face = faces[0]
        with torch.no_grad():
            embedding = facenet(face.unsqueeze(0)).squeeze()
        embedding = embedding / embedding.norm()
        return embedding.tolist()
    except Exception as e:
        print(f"[AI] Errore embedding facciale ({percorso_img}): {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
#  OCR
# ──────────────────────────────────────────────────────────────────────
def estrai_testo_ocr(percorso_img):
    """
    Esegue il Riconoscimento Ottico dei Caratteri (OCR) sull'immagine fornita
    usando EasyOCR. Riconosce il testo stampato all'interno dell'immagine e 
    lo unisce in un'unica stringa, utile per consentire la ricerca per parola chiave.
    """
    try:
        reader = _carica_ocr()
        risultati = reader.readtext(percorso_img, detail=0)
        return " ".join(risultati).strip()
    except Exception as e:
        print(f"[AI] Errore OCR ({percorso_img}): {e}")
        return ""


# ──────────────────────────────────────────────────────────────────────
#  METADATA EXIF
# ──────────────────────────────────────────────────────────────────────
# Cache dei reverse-geocoding per evitare chiamate ripetute alle stesse coordinate
_GEOCODING_CACHE = {}


def _converti_gps(gps_info):
    """Converte i dati GPS EXIF in coordinate decimali (lat, lon) o None."""
    try:
        gps_dati = {}
        for key, val in gps_info.items():
            nome = GPSTAGS.get(key, key)
            gps_dati[nome] = val

        lat_ref = gps_dati.get("GPSLatitudeRef", "N")
        lon_ref = gps_dati.get("GPSLongitudeRef", "E")
        lat     = gps_dati.get("GPSLatitude")
        lon     = gps_dati.get("GPSLongitude")

        if lat and lon:
            # Le componenti GPS possono essere IFDRational (Pillow) o float:
            # forziamo tutto a float per evitare che la somma resti una
            # frazione (es. 901633/20000) che romperebbe la chiamata di
            # reverse geocoding.
            lat_dec = float(lat[0]) + float(lat[1]) / 60 + float(lat[2]) / 3600
            lon_dec = float(lon[0]) + float(lon[1]) / 60 + float(lon[2]) / 3600
            if lat_ref == "S": lat_dec = -lat_dec
            if lon_ref == "W": lon_dec = -lon_dec
            return lat_dec, lon_dec
    except Exception:
        pass
    return None


def riconosci_luogo_da_gps(lat, lon):
    """
    Reverse geocoding: converte coordinate decimali (lat, lon) in un nome di
    luogo leggibile (es. "Roma, Italia") tramite Nominatim (OpenStreetMap).
    Usa una cache in memoria per non ripetere chiamate alle stesse coordinate.
    Ritorna una stringa leggibile oppure None in caso di errore/assenza rete.
    """
    try:
        chiave = f"{lat:.3f},{lon:.3f}"
        if chiave in _GEOCODING_CACHE:
            return _GEOCODING_CACHE[chiave]

        import requests
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat}&lon={lon}&zoom=14&accept-language=it"
        )
        resp = requests.get(url, headers={"User-Agent": "DeepSight/1.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        addr = data.get("address", {})
        # Priorità: città/town/village → contea/provincia → stato/regione → paese
        parti = []
        for key in ("city", "town", "village", "municipality",
                    "county", "state", "country"):
            val = addr.get(key)
            if val and val not in parti:
                parti.append(val)

        risultato = ", ".join(parti) if parti else data.get("display_name", "")
        _GEOCODING_CACHE[chiave] = risultato or None
        return risultato or None
    except Exception as e:
        print(f"[AI] Errore reverse geocoding GPS ({lat},{lon}): {e}")
        _GEOCODING_CACHE[chiave] = None
        return None


def riconosci_coordinate_da_testo(testo):
    """
    Forward geocoding: converte un nome di luogo (es. "Torino") nelle coordinate
    decimali (lat, lon) tramite Nominatim (OpenStreetMap). Usa una cache in
    memoria per non ripetere chiamate alla stessa località.
    Ritorna (lat, lon) come float oppure None in caso di errore/assenza rete.
    """
    try:
        chiave = testo.strip().lower()
        if not chiave:
            return None
        # Cache condivisa con il reverse geocoding ma con prefisso dedicato
        cache_key = f"txt:{chiave}"
        if cache_key in _GEOCODING_CACHE:
            return _GEOCODING_CACHE[cache_key]

        import requests
        url = (
            "https://nominatim.openstreetmap.org/search"
            f"?format=jsonv2&q={requests.utils.quote(testo)}&limit=1&accept-language=it"
        )
        resp = requests.get(url, headers={"User-Agent": "DeepSight/1.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            _GEOCODING_CACHE[cache_key] = (lat, lon)
            return lat, lon
        _GEOCODING_CACHE[cache_key] = None
        return None
    except Exception as e:
        print(f"[AI] Errore forward geocoding ('{testo}'): {e}")
        _GEOCODING_CACHE[cache_key] = None
        return None


def estrai_metadata_exif(percorso_img):
    """
    Estrae data di creazione e luogo (GPS) dai metadati EXIF.
    Se presenti, le coordinate vengono convertite in un nome di luogo leggibile
    tramite reverse geocoding (es. "Roma, Italia"). In assenza di rete o di
    match, resta comunque salvata la stringa "GPS: lat, lon".
    Ritorna dict: {"data": str, "luogo": str, "gps": str|None}
    """
    info = {"data": "Sconosciuta", "luogo": "Sconosciuto", "gps": None}
    try:
        img = Image.open(percorso_img)
        exif_raw = img._getexif()
        if not exif_raw:
            return info
        for tag_id, value in exif_raw.items():
            nome = TAGS.get(tag_id, tag_id)
            if nome == "DateTimeOriginal":
                # Formato EXIF: "YYYY:MM:DD HH:MM:SS"
                try:
                    info["data"] = value[:10].replace(":", "/")
                except Exception:
                    info["data"] = str(value)
            elif nome == "GPSInfo":
                coord = _converti_gps(value)
                if coord:
                    lat_dec, lon_dec = coord
                    info["gps"] = f"{lat_dec:.4f}, {lon_dec:.4f}"
                    # Prova a riconoscere il luogo reale dalle coordinate
                    luogo = riconosci_luogo_da_gps(lat_dec, lon_dec)
                    if luogo:
                        info["luogo"] = luogo
                    else:
                        info["luogo"] = f"GPS: {info['gps']}"
    except Exception:
        pass
    return info


# ──────────────────────────────────────────────────────────────────────
#  ELABORAZIONE SINGOLA IMMAGINE
# ──────────────────────────────────────────────────────────────────────
def elabora_immagine(percorso_file):
    """
    Funzione principale per l'analisi di una singola immagine.
    Esegue in sequenza quattro operazioni fondamentali:
      1. Calcolo dell'embedding vettoriale dell'immagine (CLIP).
      2. Estrazione di testo contenuto nell'immagine tramite OCR.
      3. Estrazione dei metadati nascosti del file (data di scatto e coordinate GPS da EXIF).
      4. Rilevamento delle facce per determinare il numero totale presente.
    
    Ritorna un dizionario strutturato con tutte le informazioni raccolte o None in caso di errore.
    Queste informazioni verranno poi salvate nel database (DuckDB e ChromaDB).
    """
    if not os.path.exists(percorso_file):
        print(f"[AI] File non trovato: {percorso_file}")
        return None
    try:
        embedding  = genera_embedding_immagine(percorso_file)
        testo_ocr  = estrai_testo_ocr(percorso_file)
        meta_exif  = estrai_metadata_exif(percorso_file)

        # Rileva il numero di facce nell'immagine
        num_facce = 0
        try:
            mtcnn, _ = _carica_facenet()
            img = Image.open(percorso_file).convert("RGB")
            boxes, _ = mtcnn.detect(img)
            if boxes is not None:
                num_facce = len(boxes)
        except Exception as fe:
            print(f"[AI] Errore rilevamento facce ({percorso_file}): {fe}")

        return {
            "tipo":           "immagine",
            "percorso_file":  percorso_file,
            "embedding_clip": embedding,
            "testo_ocr":      testo_ocr,
            "data_creazione": meta_exif["data"],
            "luogo":          meta_exif["luogo"],
            "gps":            meta_exif.get("gps"),
            "num_facce":      num_facce,
        }
    except Exception as e:
        print(f"[AI] Errore elaborazione immagine: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
#  ELABORAZIONE VIDEO (campionamento adattivo – target 30 frame totali)
# ──────────────────────────────────────────────────────────────────────
def elabora_video(percorso_file, callback_progresso=None):
    """
    Elabora un file video campionando esattamente TARGET_FRAMES frame distribuiti
    uniformemente sull'intera durata del video, indipendentemente dalla sua lunghezza.

    Logica di campionamento adattivo:
      - Si calcola la durata totale del video (secondi).
      - L'intervallo di campionamento viene impostato a durata / TARGET_FRAMES,
        così da ottenere sempre e solo 30 frame sull'intero filmato.
      - Per video molto brevi (< TARGET_FRAMES secondi) si campiona 1 frame/sec.

    OGNI frame campionato viene analizzato (embedding CLIP + OCR) per permettere
    la ricerca semantica su tutto il contenuto del video, non solo sul primo frame.
    Restituisce una lista di dizionari, uno per frame, con timestamp e embedding.
    """
    TARGET_FRAMES = 30  # numero fisso di frame da estrarre sull'intera durata

    if not os.path.exists(percorso_file):
        print(f"[AI] Video non trovato: {percorso_file}")
        return None

    frame_results = []
    temp_frames = []

    try:
        video = cv2.VideoCapture(percorso_file)
        fps          = video.get(cv2.CAP_PROP_FPS) or 25
        totale_frame = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        durata_sec   = totale_frame / fps if fps > 0 else 0

        # Calcola intervallo in frame per distribuire TARGET_FRAMES sull'intera durata
        if durata_sec >= TARGET_FRAMES:
            intervallo_sec = durata_sec / TARGET_FRAMES
        else:
            intervallo_sec = 1.0  # fallback: 1 frame/sec per video molto corti

        intervallo_frame = max(int(fps * intervallo_sec), 1)

        print(
            f"[AI] Video: {durata_sec:.1f}s | fps: {fps:.1f} | "
            f"target: {TARGET_FRAMES} frame | intervallo: {intervallo_sec:.2f}s "
            f"({intervallo_frame} frame)"
        )

        if callback_progresso:
            callback_progresso(
                f"Video {durata_sec:.0f}s – campionamento {TARGET_FRAMES} frame..."
            )

        contatore = 0
        id_frame  = 0

        while True:
            success, frame = video.read()
            if not success:
                break

            if contatore % intervallo_frame == 0:
                # Salva frame temporaneo su disco
                nome_temp = os.path.join(
                    tempfile.gettempdir(),
                    f"ds_frame_{os.path.basename(percorso_file)}_{id_frame}.jpg"
                )
                cv2.imwrite(nome_temp, frame)
                temp_frames.append(nome_temp)

                # Analizza OGNI frame campionato (embedding CLIP + OCR + facce)
                res = elabora_immagine(nome_temp)
                if res:
                    res["tipo"]           = "video"
                    res["percorso_file"]  = percorso_file
                    res["timestamp_sec"]  = round(contatore / fps, 2)
                    res["frame_index"]    = id_frame
                    frame_results.append(res)

                if callback_progresso:
                    timestamp = round(contatore / fps, 1)
                    callback_progresso(
                        f"Analisi frame {id_frame + 1}/{TARGET_FRAMES} "
                        f"(t={timestamp}s)..."
                    )

                id_frame += 1
                # Interrompi se abbiamo già raggiunto il numero target
                if id_frame >= TARGET_FRAMES:
                    break

            contatore += 1

        video.release()

    except Exception as e:
        print(f"[AI] Errore elaborazione video: {e}")
    finally:
        # Rimuovi tutti i frame temporanei
        for f in temp_frames:
            try:
                os.remove(f)
            except Exception:
                pass

    if not frame_results:
        return None

    # Il primo frame diventa il "rappresentativo" principale per compatibilità
    principale = frame_results[0].copy()
    # Converte frame_results nel formato atteso dal DB: lista di dict con embedding, timestamp, frame_idx
    principale["frame_embeddings"] = [
        {
            "embedding":     fr.get("embedding_clip"),
            "timestamp_sec": fr.get("timestamp_sec", 0.0),
            "frame_idx":     fr.get("frame_index", 0),
            "testo_ocr":     fr.get("testo_ocr", ""),
            "num_facce":     fr.get("num_facce", 0)
        }
        for fr in frame_results
    ]
    return principale

# ──────────────────────────────────────────────────────────────────────
#  ENTRY POINT PRINCIPALE
# ──────────────────────────────────────────────────────────────────────
def elabora_file(percorso_file, callback_progresso=None):
    """
    Entry point generale del modulo di AI. Riceve il percorso di un file appena
    salvato nello storage. In base all'estensione del file (immagine o video),
    delega il compito alla rispettiva funzione di elaborazione.
    La funzione di callback (opzionale) viene chiamata per aggiornare l'interfaccia 
    utente (ad es. la barra di caricamento) sullo stato dell'operazione.
    """
    ext = os.path.splitext(percorso_file)[1].lower()

    if ext in config.ESTENSIONI_IMMAGINI:
        if callback_progresso:
            callback_progresso("Analisi immagine in corso...")
        return elabora_immagine(percorso_file)

    elif ext in config.ESTENSIONI_VIDEO:
        if callback_progresso:
            callback_progresso("Analisi video in corso (campionamento frame)...")
        return elabora_video(percorso_file, callback_progresso)

    else:
        print(f"[AI] Formato non supportato: {ext}")
        return None