"""
DeepSight - Database Layer
Livello di interazione e persistenza dei dati.
Gestisce in modo trasparente l'uso congiunto di due database locali:
  - DuckDB (Relazionale): salva i metadati (tipo, percorso, luogo, data, OCR, tag) in tabelle SQL classiche.
  - ChromaDB (Vettoriale): salva gli embedding generati dall'AI (CLIP) per permettere ricerche rapide per similarità visiva o semantica.
"""

import os
import sys
from datetime import datetime

import duckdb
import chromadb

# Permette l'import sia dalla radice che dalla cartella Database
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import Config_Start.config as config


class Database:
    _instance = None  # Singleton

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._inizializzato = False
        return cls._instance

    def __init__(self):
        if self._inizializzato:
            return
        self._inizializzato = True

        # ── DuckDB ──────────────────────────────────────────────────────
        self.conn = duckdb.connect(config.DB_PATH)
        self._crea_tabelle_duckdb()

        # ── ChromaDB ─────────────────────────────────────────────────────
        self.chroma_client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        self.chroma_collection = self.chroma_client.get_or_create_collection(
            name="multimedia_clip",
            metadata={"hnsw:space": "cosine"}
        )
        print("[DB] Database inizializzato correttamente.")

    # ═══════════════════════════════════════════════════════════════════
    #  SCHEMA
    # ═══════════════════════════════════════════════════════════════════
    def _crea_tabelle_duckdb(self):
        """Crea le tabelle se non esistono già."""
        # Sequenza per gli ID
        try:
            self.conn.execute("CREATE SEQUENCE id_multimedia_seq START 1")
        except Exception:
            pass  # Esiste già

        # Tabella principale file multimediali
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS file_multimediali (
                id               INTEGER PRIMARY KEY DEFAULT nextval('id_multimedia_seq'),
                tipo             VARCHAR,
                percorso_file    VARCHAR UNIQUE,
                nome_file        VARCHAR,
                luogo            VARCHAR DEFAULT 'Sconosciuto',
                gps              VARCHAR DEFAULT NULL,
                data_creazione   VARCHAR DEFAULT 'Sconosciuta',
                data_inserimento VARCHAR,
                testo_ocr        VARCHAR DEFAULT '',
                num_facce        INTEGER DEFAULT 0,
                dimensione_mb    DOUBLE  DEFAULT 0.0
            )
        """)

        # Aggiunge la colonna gps se manca (tabelle create prima di questa versione)
        try:
            self.conn.execute("ALTER TABLE file_multimediali ADD COLUMN gps VARCHAR DEFAULT NULL")
        except Exception:
            pass

        # Tabella tag
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tag_assegnati (
                id_file INTEGER,
                tag     VARCHAR,
                PRIMARY KEY (id_file, tag)
            )
        """)
        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════════
    #  INSERT
    # ═══════════════════════════════════════════════════════════════════
    def insert_multimedia(
        self,
        tipo,
        percorso_file,
        tag_list=None,
        luogo="Sconosciuto",
        gps=None,
        data_creazione="Sconosciuta",
        embedding_clip=None,
        frame_embeddings=None,
        testo_ocr="",
        num_facce=0,
    ):
        """
        Salva i dati estratti di un file nel sistema.
        1. Esegue una query SQL INSERT su DuckDB per registrare il percorso, la data, il luogo ecc.
        2. Inserisce ciascun tag in una tabella separata `tag_assegnati` legandoli tramite ID.
        3. Se vengono forniti gli embedding CLIP (singolo per immagini, multipli per video), 
           li salva su ChromaDB usando l'ID generato da DuckDB come chiave esterna.
           Per i video, frame_embeddings è una lista di dict con: embedding, timestamp_sec, frame_idx.
           
        Restituisce l'ID (int) univoco assegnato al file, oppure None in caso di duplicato o errore.
        """
        nome_file = os.path.basename(percorso_file)
        data_inserimento = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Dimensione in MB
        try:
            dim_mb = os.path.getsize(percorso_file) / (1024 * 1024)
        except Exception:
            dim_mb = 0.0

        # Controlla duplicati sul percorso
        esistente = self.conn.execute(
            "SELECT id FROM file_multimediali WHERE percorso_file = ?",
            [percorso_file]
        ).fetchone()
        if esistente:
            print(f"[DB] File già presente: {nome_file}")
            return None

        try:
            res = self.conn.execute("""
                INSERT INTO file_multimediali
                    (tipo, percorso_file, nome_file, luogo, gps, data_creazione,
                     data_inserimento, testo_ocr, num_facce, dimensione_mb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                tipo, percorso_file, nome_file, luogo, gps, data_creazione,
                data_inserimento, testo_ocr, num_facce, dim_mb
            )).fetchone()
            self.conn.commit()
        except Exception as e:
            print(f"[DB] Errore INSERT: {e}")
            return None

        id_assegnato = res[0]

        # Inserisci tag
        if tag_list:
            for tag in tag_list:
                tag = tag.strip().lower()
                if tag:
                    try:
                        self.conn.execute(
                            "INSERT INTO tag_assegnati VALUES (?, ?)",
                            (id_assegnato, tag)
                        )
                    except Exception:
                        pass  # Tag duplicato, ignora
            self.conn.commit()

        # Inserisci embedding in ChromaDB
        # Per immagini: usa embedding_clip (singolo)
        # Per video: usa frame_embeddings (lista di frame con timestamp)
        if embedding_clip is not None:
            # Immagine singola (backward compatibility) OPPURE primo frame del video
            try:
                is_video = (tipo == "video")
                self.chroma_collection.add(
                    ids=[f"{id_assegnato}_frame_0"],
                    embeddings=[embedding_clip],
                    metadatas=[{
                        "file_id":       id_assegnato,
                        "nome_file":     nome_file,
                        "percorso":      percorso_file,
                        "tipo":          tipo,
                        "frame_idx":     0,
                        "timestamp_sec": 0.0,
                        "is_video":      is_video
                    }]
                )
            except Exception as e:
                print(f"[ChromaDB] Errore add embedding immagine: {e}")

        if frame_embeddings:
            # Video: inserisci un embedding per ogni frame
            try:
                ids = []
                embeddings = []
                metadatas = []
                for fe in frame_embeddings:
                    frame_idx = fe.get("frame_idx", 0)
                    timestamp = fe.get("timestamp_sec", 0.0)
                    emb = fe.get("embedding")
                    if emb is None:
                        continue
                    ids.append(f"{id_assegnato}_frame_{frame_idx}")
                    embeddings.append(emb)
                    metadatas.append({
                        "file_id":       id_assegnato,
                        "nome_file":     nome_file,
                        "percorso":      percorso_file,
                        "tipo":          tipo,
                        "frame_idx":     frame_idx,
                        "timestamp_sec": timestamp,
                        "is_video":      True
                    })
                
                if ids:
                    self.chroma_collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        metadatas=metadatas
                    )
                    print(f"[ChromaDB] Inseriti {len(ids)} frame embedding per video ID={id_assegnato}")
            except Exception as e:
                print(f"[ChromaDB] Errore add frame embeddings video: {e}")

        print(f"[DB] File inserito con ID={id_assegnato}: {nome_file}")
        return id_assegnato

    # ═══════════════════════════════════════════════════════════════════
    #  RICERCA
    # ═══════════════════════════════════════════════════════════════════
    def cerca_per_embedding(self, embedding_query, top_n=20):
        """
        Utilizza ChromaDB per confrontare un embedding di query (che può derivare 
        da un testo o da un'immagine) con tutti gli embedding salvati nel database.
        Restituisce i `top_n` file più simili (distanza Coseno più bassa), ordinati 
        per punteggio di similarità (score).
        Per i video, restituisce il miglior frame match per ogni video.
        """
        if self.chroma_collection.count() == 0:
            return []
        try:
            risultati = self.chroma_collection.query(
                query_embeddings=[embedding_query],
                n_results=min(top_n * 3, self.chroma_collection.count())  # richiedi più risultati per deduplicare per file
            )
        except Exception as e:
            print(f"[ChromaDB] Errore query: {e}")
            return []

        output = []
        ids     = risultati["ids"][0]
        metas   = risultati["metadatas"][0]
        dists   = risultati["distances"][0]

        # Per video: raggruppa per file_id e prendi il miglior frame
        best_per_file = {}
        
        for id_str, meta, dist in zip(ids, metas, dists):
            score = round((1 - dist) * 100, 1)
            file_id = meta.get("file_id")
            is_video = meta.get("is_video", False)
            frame_idx = meta.get("frame_idx", 0)
            timestamp = meta.get("timestamp_sec", 0.0)
            
            if file_id is None:
                # Vecchio formato (immagini senza frame_id) - id_str è l'ID del file
                try:
                    file_id = int(id_str)
                except:
                    continue
            
            if file_id not in best_per_file or score > best_per_file[file_id]["score"]:
                best_per_file[file_id] = {
                    "id":            file_id,
                    "percorso_file": meta.get("percorso", ""),
                    "nome_file":     meta.get("nome_file", ""),
                    "tipo":          meta.get("tipo", ""),
                    "score":         score,
                    "is_video":      is_video,
                    "frame_idx":     frame_idx,
                    "timestamp_sec": timestamp
                }

        # Ordina per score decrescente e limita a top_n
        sorted_results = sorted(best_per_file.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:top_n]

    def cerca_per_filtri(self, tipo=None, data_inizio=None, data_fine=None, luogo=None, ids_vettoriali=None):
        """
        Genera ed esegue una query SQL dinamica su DuckDB in base ai filtri compilati dall'utente.
        - tipo, luogo, date: filtrano le rispettive colonne della tabella `file_multimediali`.
        - ids_vettoriali: se presente (risultato di `cerca_per_embedding`), impone una clausola "IN (id1, id2...)" 
          in modo da restringere i risultati di DuckDB esclusivamente a quelli trovati precedentemente 
          dalla ricerca semantica di ChromaDB.
        Ritorna una lista di dizionari, ognuno contenente tutte le informazioni del media.
        """
        condizioni = []
        params = []

        if tipo and tipo != "Tutto":
            tipo_db = "immagine" if tipo == "Immagini" else "video"
            condizioni.append("fm.tipo = ?")
            params.append(tipo_db)

        if luogo:
            condizioni.append("LOWER(fm.luogo) LIKE ?")
            params.append(f"%{luogo.lower()}%")

        if data_inizio:
            condizioni.append("fm.data_inserimento >= ?")
            params.append(data_inizio)

        if data_fine:
            condizioni.append("fm.data_inserimento <= ?")
            params.append(data_fine)

        if ids_vettoriali is not None:
            if not ids_vettoriali:
                return []
            placeholders = ",".join(["?"] * len(ids_vettoriali))
            condizioni.append(f"fm.id IN ({placeholders})")
            params.extend(ids_vettoriali)

        where_clause = ("WHERE " + " AND ".join(condizioni)) if condizioni else ""

        query = f"""
            SELECT fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                   fm.luogo, fm.data_creazione, fm.data_inserimento,
                   fm.testo_ocr, fm.num_facce, fm.dimensione_mb,
                   STRING_AGG(ta.tag, ', ') AS tags
            FROM file_multimediali fm
            LEFT JOIN tag_assegnati ta ON ta.id_file = fm.id
            {where_clause}
            GROUP BY fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                     fm.luogo, fm.data_creazione, fm.data_inserimento,
                     fm.testo_ocr, fm.num_facce, fm.dimensione_mb
            ORDER BY fm.id DESC
            LIMIT 50
        """
        try:
            rows = self.conn.execute(query, params).fetchall()
        except Exception as e:
            print(f"[DB] Errore SELECT: {e}")
            return []

        colonne = ["id", "tipo", "percorso_file", "nome_file", "luogo",
                   "data_creazione", "data_inserimento", "testo_ocr",
                   "num_facce", "dimensione_mb", "tags"]
        return [dict(zip(colonne, row)) for row in rows]

    def cerca_per_testo_tag(self, testo, tipo=None, luogo=None):
        """
        Metodo di ricerca fallback tradizionale (esatta/SQL LIKE).
        Cerca la parola o stringa inserita all'interno del nome del file,
        nel testo estratto dall'OCR e nella tabella dei Tag.
        I parametri opzionali 'tipo' (es. 'Immagini' o 'Video') e 'luogo'
        aggiungono rispettivamente un filtro sulla colonna tipo e sulla
        colonna luogo (es. "Torino"), così da poter combinare contenuto + luogo.
        """
        testo_lower = f"%{testo.lower()}%"
        params = [testo_lower, testo_lower, testo_lower]

        extra_clause = ""
        if tipo and tipo != "Tutto":
            tipo_db = "immagine" if tipo == "Immagini" else "video"
            extra_clause += " AND fm.tipo = ?"
            params.append(tipo_db)

        if luogo:
            extra_clause += " AND LOWER(fm.luogo) LIKE ?"
            params.append(f"%{luogo.lower()}%")

        query = f"""
            SELECT DISTINCT fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                   fm.luogo, fm.data_creazione, fm.data_inserimento,
                   fm.testo_ocr, fm.num_facce, fm.dimensione_mb,
                   STRING_AGG(ta.tag, ', ') AS tags
            FROM file_multimediali fm
            LEFT JOIN tag_assegnati ta ON ta.id_file = fm.id
            WHERE (LOWER(fm.nome_file) LIKE ?
               OR LOWER(fm.testo_ocr)  LIKE ?
               OR LOWER(ta.tag)        LIKE ?)
            {extra_clause}
            GROUP BY fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                     fm.luogo, fm.data_creazione, fm.data_inserimento,
                     fm.testo_ocr, fm.num_facce, fm.dimensione_mb
            ORDER BY fm.id DESC
            LIMIT 50
        """
        try:
            rows = self.conn.execute(query, params).fetchall()
        except Exception as e:
            print(f"[DB] Errore ricerca testo: {e}")
            return []
        colonne = ["id", "tipo", "percorso_file", "nome_file", "luogo",
                   "data_creazione", "data_inserimento", "testo_ocr",
                   "num_facce", "dimensione_mb", "tags"]
        return [dict(zip(colonne, row)) for row in rows]

    def cerca_per_coordinate(self, lat, lon, raggio_lat=1.0, raggio_lon=1.0, tipo=None):
        """
        Ricerca di prossimita' geografica: restituisce i file la cui colonna `gps`
        (formato "lat, lon") cade nel bounding box [lat±raggio_lat, lon±raggio_lon]
        attorno al punto di query. Il punto di query tipicamente deriva dal
        geocoding del luogo digitato dall'utente nella barra di ricerca.
        Ritorna una lista di dizionari (stesso formato di cerca_per_filtri).
        """
        try:
            lat_min, lat_max = lat - raggio_lat, lat + raggio_lat
            lon_min, lon_max = lon - raggio_lon, lon + raggio_lon

            condizioni = [
                "fm.gps IS NOT NULL",
                "CAST(trim(split_part(fm.gps, ',', 1)) AS DOUBLE) BETWEEN ? AND ?",
                "CAST(trim(split_part(fm.gps, ',', 2)) AS DOUBLE) BETWEEN ? AND ?",
            ]
            params = [lat_min, lat_max, lon_min, lon_max]

            if tipo and tipo != "Tutto":
                tipo_db = "immagine" if tipo == "Immagini" else "video"
                condizioni.append("fm.tipo = ?")
                params.append(tipo_db)

            where_clause = "WHERE " + " AND ".join(condizioni)

            query = f"""
                SELECT fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                       fm.luogo, fm.gps, fm.data_creazione, fm.data_inserimento,
                       fm.testo_ocr, fm.num_facce, fm.dimensione_mb,
                       STRING_AGG(ta.tag, ', ') AS tags
                FROM file_multimediali fm
                LEFT JOIN tag_assegnati ta ON ta.id_file = fm.id
                {where_clause}
                GROUP BY fm.id, fm.tipo, fm.percorso_file, fm.nome_file,
                         fm.luogo, fm.gps, fm.data_creazione, fm.data_inserimento,
                         fm.testo_ocr, fm.num_facce, fm.dimensione_mb
                ORDER BY fm.id DESC
                LIMIT 200
            """
            rows = self.conn.execute(query, params).fetchall()
        except Exception as e:
            print(f"[DB] Errore ricerca per coordinate: {e}")
            return []

        colonne = ["id", "tipo", "percorso_file", "nome_file", "luogo", "gps",
                   "data_creazione", "data_inserimento", "testo_ocr",
                   "num_facce", "dimensione_mb", "tags"]
        return [dict(zip(colonne, row)) for row in rows]

    # ═══════════════════════════════════════════════════════════════════
    #  STATISTICHE (per la Dashboard Home)
    # ═══════════════════════════════════════════════════════════════════
    def get_statistiche(self):
        """
        Aggrega ed estrae le metriche globali per popolare la dashboard Home:
          - Conteggio totale per Immagini e Video, e il loro peso totale in MB.
          - I 10 Tag più usati in assoluto (`tag_frequenze`).
          - L'andamento temporale dei caricamenti degli ultimi giorni (`caricamenti_per_giorno`).
        Esegue 3 diverse query raggruppate in DuckDB per estrarre tali statistiche rapidamente.
        """
        stats = {
            "count_img": 0,
            "count_vid": 0,
            "size_totale_mb": 0.0,
            "tag_frequenze": [],
            "caricamenti_per_giorno": []
        }
        try:
            row = self.conn.execute("""
                SELECT
                    SUM(CASE WHEN tipo='immagine' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN tipo='video'    THEN 1 ELSE 0 END),
                    SUM(dimensione_mb)
                FROM file_multimediali
            """).fetchone()
            if row:
                stats["count_img"]       = int(row[0] or 0)
                stats["count_vid"]       = int(row[1] or 0)
                stats["size_totale_mb"]  = float(row[2] or 0.0)

            tags = self.conn.execute("""
                SELECT tag, COUNT(*) as cnt
                FROM tag_assegnati
                GROUP BY tag
                ORDER BY cnt DESC
                LIMIT 10
            """).fetchall()
            stats["tag_frequenze"] = [(r[0], r[1]) for r in tags]

            giorni = self.conn.execute("""
                SELECT SUBSTRING(data_inserimento, 1, 10) AS giorno, COUNT(*) as cnt
                FROM file_multimediali
                GROUP BY giorno
                ORDER BY giorno ASC
                LIMIT 30
            """).fetchall()
            stats["caricamenti_per_giorno"] = [(r[0], r[1]) for r in giorni]

        except Exception as e:
            print(f"[DB] Errore statistiche: {e}")
        return stats

    def get_percorso_da_id(self, id_file):
        """Ritorna il percorso del file dato l'ID."""
        row = self.conn.execute(
            "SELECT percorso_file FROM file_multimediali WHERE id = ?", [id_file]
        ).fetchone()
        return row[0] if row else None

    # ═══════════════════════════════════════════════════════════════════
    #  ELIMINAZIONE
    # ═══════════════════════════════════════════════════════════════════
    def elimina_file(self, id_file):
        """
        Elimina definitivamente un file multimediale dal sistema. Operazione
        irreversibile, invocata dalla schermata di Ricerca dopo conferma
        esplicita dell'utente. Esegue in sequenza:
          1. Rimozione del file fisico dalla cartella uploads (se presente).
          2. Rimozione del record e dei tag associati da DuckDB.
          3. Rimozione degli embedding vettoriali associati da ChromaDB
             (tutti i frame, nel caso di un video).
        Ritorna una tupla (ok: bool, errore: str | None).
        """
        try:
            row = self.conn.execute(
                "SELECT percorso_file FROM file_multimediali WHERE id = ?", [id_file]
            ).fetchone()
            if not row:
                return False, "File non trovato nel database."
            percorso_file = row[0]

            # 1. Rimuovi il file fisico dalla cartella uploads
            if percorso_file and os.path.exists(percorso_file):
                try:
                    os.remove(percorso_file)
                except Exception as e:
                    print(f"[DB] Impossibile rimuovere il file fisico '{percorso_file}': {e}")

            # 2. Rimuovi record e tag dal database relazionale
            self.conn.execute("DELETE FROM tag_assegnati WHERE id_file = ?", [id_file])
            self.conn.execute("DELETE FROM file_multimediali WHERE id = ?", [id_file])
            self.conn.commit()

            # 3. Rimuovi tutti gli embedding vettoriali associati (video: piu' frame)
            try:
                self.chroma_collection.delete(where={"file_id": id_file})
            except Exception as e:
                print(f"[ChromaDB] Errore rimozione embedding per file_id={id_file}: {e}")

            print(f"[DB] File eliminato con ID={id_file}: {percorso_file}")
            return True, None
        except Exception as e:
            print(f"[DB] Errore eliminazione file ID={id_file}: {e}")
            return False, str(e)

    def chiudi_connessione(self):
        if self.conn:
            self.conn.close()