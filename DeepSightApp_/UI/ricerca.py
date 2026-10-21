"""
DeepSight - Schermata Ricerca
Ricerca avanzata su immagini e video tramite:
  - Testo semantico (CLIP embedding → ChromaDB) con score coseno
  - Filtri relazionali: tipo, data, luogo
  - Immagine di reference (CLIP embedding → ChromaDB)
I risultati vengono filtrati per SOGLIA_ACCURATEZZA:
  - Query vettoriale: score = similarità coseno ChromaDB (0–100%)
  - Query testuale:   score = % parole query trovate nei metadati
  - Solo filtri:      score non applicato (filtro esatto → sempre mostrato)
Mostra i risultati reali con thumbnail, badge accuratezza e pulsante download.
"""

import os
import sys
import subprocess
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

# Permette import dalla radice del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Database.database import Database

# ──────────────────────────────────────────────────────────────────────
#  CONFIGURAZIONE ACCURATEZZA
# ──────────────────────────────────────────────────────────────────────
# I due tipi di ricerca hanno range di score molto diversi alla base:
#   - VETTORE (CLIP): il raw score (similarità coseno) va tipicamente dal 21% (rumore puro) al 26% (match evidente).
#     Per evitare confusione, lo "calibriamo" su scala 0-100%, dove <21% diventa 0% e >25.5% diventa 100%.
#   - TESTO  (keyword): 0-100% basato sulle parole trovate.
SOGLIA_VETTORE   = 27.0   # % minima calibrata per CLIP (testo -> immagine)
SOGLIA_IMMAGINE  = 70.0   # % minima calibrata per CLIP (immagine -> immagine)
SOGLIA_TESTO     = 85.0   # % minima copertura keyword



def _supera_soglia(score, score_tipo):
    """Restituisce True se il risultato supera la soglia appropriata per il suo tipo."""
    if score_tipo == "immagine":
        return score >= SOGLIA_IMMAGINE
    if score_tipo == "vettore":
        return score >= SOGLIA_VETTORE
    if score_tipo == "testo":
        return score >= SOGLIA_TESTO
    return True   # "filtro" -> filtro esatto, sempre incluso


# def _calibra_score_vettore(score_grezzo):
#     """
#     Trasforma la similarita' coseno grezza di CLIP in una percentuale utente da 0 a 100%.
#     Calibrazione per ricerca TESTO -> IMMAGINE (cross-modal).
#     I match visivi chiari generano raw score intorno al 24-26%.
#     """
#     min_clip = 21.0
#     max_clip = 25.5
#     calibrato = ((score_grezzo - min_clip) / (max_clip - min_clip)) * 100.0
#     return round(max(0.0, min(100.0, calibrato)), 1)


# def _calibra_score_immagine(score_grezzo):
#     """
#     Calibrazione per ricerca IMMAGINE -> IMMAGINE (same-modal).
#     Gli score grezzi di CLIP per confronto immagine-immagine sono molto piu' alti
#     rispetto al cross-modal (tipicamente 50-95%), quindi usiamo un range piu' ampio.
#     """
#     min_clip = 50.0
#     max_clip = 95.0
#     calibrato = ((score_grezzo - min_clip) / (max_clip - min_clip)) * 100.0
#     return round(max(0.0, min(100.0, calibrato)), 1)


def _calcola_score_testo(testo_query, nome_file, testo_ocr, tags):
    """
    Calcola lo score di accuratezza per i risultati della ricerca testuale.
    Misura la percentuale di parole della query presenti nei metadati del file.
    Restituisce una tupla: (score_0_100, trovato_in_tag, trovato_in_ocr).
    """
    if not testo_query:
        return 100.0, False, False
        
    parole = testo_query.lower().split()
    
    nf_lower = (nome_file or "").lower()
    ocr_lower = (testo_ocr or "").lower()
    tag_lower = (tags or "").lower()
    
    campo = nf_lower + " " + ocr_lower + " " + tag_lower
    trovate = sum(1 for p in parole if p in campo)
    score = round(trovate / len(parole) * 100.0, 1) if parole else 100.0
    
    in_tag = any(p in tag_lower for p in parole)
    in_ocr = any(p in ocr_lower for p in parole)
    
    return score, in_tag, in_ocr


class RicercaFrame(ctk.CTkFrame):
    """
    Interfaccia grafica per la ricerca avanzata.
    Consente agli utenti di filtrare i file caricati combinando una ricerca semantica
    (basata su testo naturale o su un'immagine di riferimento elaborata tramite CLIP)
    con filtri tradizionali e relazionali (tipo file, range di date, luogo manuale).
    """
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.ricerca_img_reference = None
        self._thumbnail_refs = []   # mantiene i riferimenti alle immagini (evita GC)
        self._dialog_reference_aperto = False  # guardia anti-doppia-apertura del file dialog

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=7)
        self.grid_rowconfigure(0, weight=1)

        # ── Pannello Filtri (sinistra) ────────────────────────────────
        self.pannello_filtri = ctk.CTkFrame(
            self, fg_color=self.app.color_card,
            border_color=self.app.color_border, border_width=1, corner_radius=20
        )
        self.pannello_filtri.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        # Query testo
        self.search_entry = ctk.CTkEntry( 
            self.pannello_filtri,
            placeholder_text=" Cerca per concetto, oggetto, testo... 🔍",
            fg_color=self.app.color_bg, border_color=self.app.color_border,
            text_color=self.app.color_text_main, placeholder_text_color="#475569",
            height=40, corner_radius=20, font=("Inter", 13)
        )
        self.search_entry.pack(fill="x", padx=20, pady=(25, 15))
        self.search_entry.bind("<Return>", lambda e: self.avvia_ricerca())
        self.search_entry.bind("<KeyRelease>", self._on_text_typing)

        # Sezione TIPO
        ctk.CTkLabel(
            self.pannello_filtri, text="📁  TIPO",
            font=("Inter", 12, "bold"), text_color=self.app.color_text_sec
        ).pack(anchor="w", padx=25, pady=(5, 5))

        frame_radio = ctk.CTkFrame(self.pannello_filtri, fg_color="transparent")
        frame_radio.pack(fill="x", padx=25, pady=(0, 15))
        for val in ["Tutto", "Immagini", "Video"]:
            ctk.CTkRadioButton(
                frame_radio, text=val, variable=self.app.filtro_tipo, value=val,
                text_color=self.app.color_text_main, font=("Inter", 12),
                border_color=self.app.color_accent, fg_color=self.app.color_accent
            ).pack(side="left", expand=True)

        # Sezione DATA
        ctk.CTkLabel(
            self.pannello_filtri, text="📅  DATA INSERIMENTO",
            font=("Inter", 12, "bold"), text_color=self.app.color_text_sec
        ).pack(anchor="w", padx=25, pady=(10, 2))

        frame_date = ctk.CTkFrame(self.pannello_filtri, fg_color="transparent")
        frame_date.pack(fill="x", padx=20, pady=(0, 15))
        frame_date.grid_columnconfigure((0, 2), weight=1)

        frame_inizio = ctk.CTkFrame(frame_date, fg_color="transparent")
        frame_inizio.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(frame_inizio, text="Da", font=("Inter", 11), text_color=self.app.color_text_sec).pack(anchor="w")
        self.date_inizio_entry = ctk.CTkEntry(
            frame_inizio, placeholder_text="gg/mm/aaaa",
            fg_color=self.app.color_bg, border_color=self.app.color_border,
            font=("Inter", 12), height=32, text_color=self.app.color_text_main
        )
        self.date_inizio_entry.pack(fill="x")

        ctk.CTkLabel(
            frame_date, text="→", font=("Inter", 13, "bold"),
            text_color=self.app.color_text_sec
        ).grid(row=0, column=1, padx=8, pady=(15, 0))

        frame_fine = ctk.CTkFrame(frame_date, fg_color="transparent")
        frame_fine.grid(row=0, column=2, sticky="ew")
        ctk.CTkLabel(frame_fine, text="A", font=("Inter", 11), text_color=self.app.color_text_sec).pack(anchor="w")
        self.date_fine_entry = ctk.CTkEntry(
            frame_fine, placeholder_text="gg/mm/aaaa",
            fg_color=self.app.color_bg, border_color=self.app.color_border,
            font=("Inter", 12), height=32, text_color=self.app.color_text_main
        )
        self.date_fine_entry.pack(fill="x")

        # Sezione LUOGO
        ctk.CTkLabel(
            self.pannello_filtri, text="📍  LUOGO",
            font=("Inter", 12, "bold"), text_color=self.app.color_text_sec
        ).pack(anchor="w", padx=25, pady=(10, 2))
        self.luogo_entry = ctk.CTkEntry(
            self.pannello_filtri, placeholder_text="Es. Roma",
            fg_color=self.app.color_bg, border_color=self.app.color_border,
            text_color=self.app.color_text_main, placeholder_text_color="#475569",
            height=35, font=("Inter", 13)
        )
        self.luogo_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Sezione REFERENCE IMAGE
        # Un unico riquadro, sempre nella stessa posizione (sopra "Avvia
        # Ricerca"): mostra un invito testuale quando non è selezionata
        # nessuna immagine, oppure la miniatura reale una volta selezionata
        # (al posto del solo nome file testuale).
        ctk.CTkLabel(
            self.pannello_filtri, text="🖼️  IMMAGINE DI REFERENCE",
            font=("Inter", 12, "bold"), text_color=self.app.color_text_sec
        ).pack(anchor="w", padx=25, pady=(5, 2))

        self.frame_img_reference = ctk.CTkFrame(
            self.pannello_filtri, fg_color=self.app.color_bg,
            border_color=self.app.color_border, border_width=1,
            corner_radius=12, height=90, cursor="hand2"
        )
        self.frame_img_reference.pack(fill="x", padx=20, pady=(0, 10))
        self.frame_img_reference.pack_propagate(False)
        self._ref_preview_img = None  # mantiene riferimento per GC

        self._mostra_prompt_reference()  # stato iniziale: nessuna immagine selezionata

        # Pulsante Avvia Ricerca
        self.btn_avvia = ctk.CTkButton(
            self.pannello_filtri, text="🔍  Avvia Ricerca",
            fg_color=self.app.color_accent, hover_color="#0EA5E9",
            text_color="#0F172A", corner_radius=10,
            font=("Inter", 13, "bold"), height=40,
            command=self.avvia_ricerca
        )
        self.btn_avvia.pack(fill="x", padx=20, pady=(0, 10))

        # Pulsante Reset
        self.btn_reset = ctk.CTkButton(
            self.pannello_filtri, text="✖  Azzera Filtri",
            fg_color="transparent", hover_color="#243249",
            text_color=self.app.color_text_sec, corner_radius=10,
            font=("Inter", 11), height=30, border_width=1,
            border_color=self.app.color_border,
            command=self.azzera_filtri
        )
        self.btn_reset.pack(fill="x", padx=20, pady=(0, 20))

        # ── Colonna Destra: Risultati ─────────────────────────────────
        self.container_destra = ctk.CTkFrame(self, fg_color="transparent")
        self.container_destra.grid(row=0, column=1, sticky="nsew")
        self.container_destra.grid_columnconfigure(0, weight=1)
        self.container_destra.grid_rowconfigure(1, weight=1)

        # Header risultati
        header_frame = ctk.CTkFrame(self.container_destra, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        header_frame.grid_columnconfigure(0, weight=1)

        self.lbl_titolo_risultati = ctk.CTkLabel(
            header_frame, text="RISULTATI",
            font=("Inter", 22, "bold"), text_color=self.app.color_text_main
        )
        self.lbl_titolo_risultati.grid(row=0, column=0, sticky="w")

        self.lbl_count_risultati = ctk.CTkLabel(
            header_frame, text="",
            font=("Inter", 13), text_color=self.app.color_text_sec
        )
        self.lbl_count_risultati.grid(row=0, column=1, sticky="e")

        # Spinner ricerca
        self.lbl_spinner = ctk.CTkLabel(
            header_frame, text="", font=("Inter", 12, "italic"),
            text_color=self.app.color_accent
        )
        self.lbl_spinner.grid(row=1, column=0, columnspan=2, sticky="w")

        # Area scrollabile risultati
        self.scroll_risultati = ctk.CTkScrollableFrame(
            self.container_destra, fg_color="transparent",
            scrollbar_button_color=self.app.color_border,
            scrollbar_button_hover_color=self.app.color_accent
        )
        self.scroll_risultati.grid(row=1, column=0, sticky="nsew")
        self.scroll_risultati.grid_columnconfigure((0, 1), weight=1, uniform="griglia")

        # Messaggio placeholder iniziale
        self._mostra_placeholder("Usa i filtri a sinistra e clicca 'Avvia Ricerca'")

    def re_layout(self, is_mobile, width):
        """Gestisce il ricalcolo del layout della pagina Ricerca."""
        if is_mobile:
            self.pannello_filtri.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 20))
            self.container_destra.grid(row=1, column=0, sticky="nsew")
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
        else:
            self.pannello_filtri.grid(row=0, column=0, sticky="nsew", padx=(0, 20), pady=0)
            self.container_destra.grid(row=0, column=1, sticky="nsew")
            self.grid_columnconfigure(0, weight=3)
            self.grid_columnconfigure(1, weight=7)
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)
            
        # Ricalcolo griglia risultati
        available_width = self.scroll_risultati.winfo_width()
        if available_width < 10:
            available_width = width - (40 if is_mobile else 350)
            
        CARD_SIZE_APPROX = 350
        cols = max(1, available_width // CARD_SIZE_APPROX)
        if hasattr(self, '_last_res_cols') and self._last_res_cols == cols:
            return
            
        self._last_res_cols = cols
        for i in range(5):
            self.scroll_risultati.grid_columnconfigure(i, weight=0, uniform="")
        for i in range(cols):
            self.scroll_risultati.grid_columnconfigure(i, weight=1, uniform="griglia")
            
        valid_children = [c for c in self.scroll_risultati.winfo_children() if isinstance(c, ctk.CTkFrame)]
        for idx, child in enumerate(valid_children):
            child.grid(row=idx // cols, column=idx % cols, padx=8, pady=8, sticky="ew")

    # ──────────────────────────────────────────────────────────────────
    #  RICERCA PRINCIPALE
    # ──────────────────────────────────────────────────────────────────
    def avvia_ricerca(self):
        """Avvia la ricerca in un thread separato per non bloccare la UI."""
        # Se l'utente avvia una ricerca testuale (c'è del testo nel campo)
        # mentre è ancora caricata un'immagine di reference, quest'ultima
        # viene rimossa automaticamente: le due modalità sono mutuamente
        # esclusive, e questo garantisce la coerenza anche nei casi in cui
        # il testo sia arrivato senza passare da un tasto (es. incollato dal
        # menu contestuale, che non genera l'evento di digitazione già
        # gestito da _on_text_typing).
        if self.search_entry.get().strip() and self.ricerca_img_reference:
            self.ricerca_img_reference = None
            self._mostra_prompt_reference()

        self.btn_avvia.configure(state="disabled", text="⏳  Ricerca...")
        self.lbl_spinner.configure(text="Elaborazione in corso...")
        self._svuota_risultati()

        def _thread_ricerca():
            try:
                risultati, esclusi = self._esegui_ricerca_reale()
                self.app.after(0, self._mostra_risultati, risultati, esclusi)
            except Exception as e:
                self.app.after(0, self._on_errore_ricerca, str(e))

        threading.Thread(target=_thread_ricerca, daemon=True).start()

    def _esegui_ricerca_reale(self):
        """
        Logica di ricerca con gestione accuratezza:
        1. Se c'è testo o immagine reference → CLIP embedding → ChromaDB
           (score = similarità coseno, 0–100%)
        2. Fallback testuale → score calcolato sulla % parole query presenti nei metadati
        3. Solo filtri relazionali → score=None (filtro esatto, sempre mostrato)
        4. Risultati con score < SOGLIA_ACCURATEZZA vengono esclusi dalla risposta.
        Restituisce (risultati_filtrati, n_esclusi).
        """
        from AI_Model.AI_engine import genera_embedding_testo, genera_embedding_immagine

        db           = Database()
        testo_query  = self.search_entry.get().strip()
        luogo        = self.luogo_entry.get().strip()
        data_inizio  = self.date_inizio_entry.get().strip() or None
        data_fine    = self.date_fine_entry.get().strip() or None
        tipo         = self.app.filtro_tipo.get()

        ids_vettoriali = None
        score_map      = {}   # { id_file: score_float }

        # ── Geocoding inverso del LUOGO digitato → coordinate ──────────
        # Invece di cercare il testo del luogo tra i metadati, trasformiamo
        # il luogo scritto in lat/lon e cerchiamo le foto i cui GPS cadono
        # entro un range di ±1 grado (prossimita' geografica).
        ids_coordinate = None
        if luogo:
            try:
                from AI_Model.AI_engine import riconosci_coordinate_da_testo
                coord = riconosci_coordinate_da_testo(luogo)
                if coord:
                    ids_coordinate = set(
                        r["id"] for r in db.cerca_per_coordinate(coord[0], coord[1])
                    )
                    self.app.after(0, lambda c=coord: self.lbl_spinner.configure(
                        text=f"Luogo '{luogo}' → {c[0]:.3f}, {c[1]:.3f} "
                              f"(raggio ±1°)"))
            except Exception as e:
                print(f"[Ricerca] Geocoding luogo fallito: {e}")

        # Se il geocoding ha prodotto coordinate usiamo la prossimita';
        # altrimenti (rete assente / luogo sconosciuto) resta il LIKE testuale.
        luogo_param = luogo if ids_coordinate is None else None

        # ── Ricerca vettoriale ──────────────────────────────────────
        ricerca_per_immagine = False   # flag per distinguere il tipo di calibrazione

        if self.ricerca_img_reference:
            ricerca_per_immagine = True
            self.app.after(0, lambda: self.lbl_spinner.configure(
                text="Generazione embedding immagine reference..."))
            emb = genera_embedding_immagine(self.ricerca_img_reference)
            if emb:
                for r in db.cerca_per_embedding(emb, top_n=50):
                    # score_map[r["id"]] = _calibra_score_immagine(r["score"])
                    score_map[r["id"]] = r["score"]
                ids_vettoriali = list(score_map.keys())

        elif testo_query:
            self.app.after(0, lambda: self.lbl_spinner.configure(
                text="Generazione embedding testo..."))
            emb = genera_embedding_testo(testo_query)
            if emb:
                for r in db.cerca_per_embedding(emb, top_n=30):
                    # score_map[r["id"]] = _calibra_score_vettore(r["score"])
                    score_map[r["id"]] = r["score"]
                ids_vettoriali = list(score_map.keys())

        # ── Ricerca relazionale + assegnazione score ───────────────
        self.app.after(0, lambda: self.lbl_spinner.configure(text="Query database..."))

        if testo_query and not ids_vettoriali:
            # CASO A – Fallback puro: nessun risultato vettoriale
            # Applica anche il filtro luogo (es. "Torino") per combinare
            # contenuto + località (prossimita' GPS o LIKE testuale di fallback).
            risultati_raw = db.cerca_per_testo_tag(testo_query, tipo=tipo, luogo=luogo_param)
            if ids_coordinate is not None:
                risultati_raw = [r for r in risultati_raw if r["id"] in ids_coordinate]
            for r in risultati_raw:
                st, in_tag, in_ocr = _calcola_score_testo(
                    testo_query, r["nome_file"],
                    r.get("testo_ocr", ""), r.get("tags", "")
                )
                r["score"] = st
                r["in_tag"] = in_tag
                r["in_ocr"] = in_ocr
                r["score_tipo"] = "testo"

        elif ids_vettoriali:
            # CASO B – Risultati vettoriali: attach score coseno
            # ids_vettoriali (contenuto CLIP) intersecati col filtro luogo
            # (prossimita' GPS o LIKE testuale di fallback).
            risultati_vettoriali = db.cerca_per_filtri(
                tipo=tipo, data_inizio=data_inizio, data_fine=data_fine,
                luogo=luogo_param, ids_vettoriali=ids_vettoriali
            )
            if ids_coordinate is not None:
                risultati_vettoriali = [
                    r for r in risultati_vettoriali if r["id"] in ids_coordinate
                ]
            for r in risultati_vettoriali:
                r["score"]      = score_map.get(r["id"], 0.0)
                r["score_tipo"] = "immagine" if ricerca_per_immagine else "vettore"

            if testo_query:
                # Unisci con fallback testuale (file senza embedding)
                risultati_testo = db.cerca_per_testo_tag(testo_query, tipo=tipo, luogo=luogo_param)
                if ids_coordinate is not None:
                    risultati_testo = [
                        r for r in risultati_testo if r["id"] in ids_coordinate
                    ]
                
                # Calcola score testuale per questi risultati
                for r in risultati_testo:
                    st, in_tag, in_ocr = _calcola_score_testo(
                        testo_query, r["nome_file"],
                        r.get("testo_ocr", ""), r.get("tags", "")
                    )
                    r["score_testuale"] = st
                    r["in_tag"] = in_tag
                    r["in_ocr"] = in_ocr

                map_testo = {r["id"]: r for r in risultati_testo}
                
                # Se il risultato vettoriale ha anche un ottimo match testuale, usa quello testuale
                for r in risultati_vettoriali:
                    if r["id"] in map_testo:
                        match = map_testo[r["id"]]
                        st = match["score_testuale"]
                        if st >= SOGLIA_TESTO:
                            # --- VETO AI ---
                            # Se l'immagine non c'entra visivamente NIENTE (score 0.0) 
                            # e il match è SOLO nel nome del file (non in tag manuali o testo OCR), 
                            # si tratta probabilmente di un nome fuorviante (es. "gatto2.jpg" che mostra una macchina).
                            if r["score"] == 0.0 and not match["in_tag"] and not match["in_ocr"]:
                                pass # Applica il VETO: mantieni lo score vettoriale (0.0) così verrà scartato
                            else:
                                r["score"] = st
                                r["score_tipo"] = "testo"

                id_vettoriali = {r["id"] for r in risultati_vettoriali}
                extra = []
                for r in risultati_testo:
                    if r["id"] not in id_vettoriali:
                        # Stesso VETO per i file extra che non sono rientrati nei top vettoriali
                        if r["tipo"] in ["immagine", "video"] and not r["in_tag"] and not r["in_ocr"]:
                            # Se è un media visivo e matchiamo solo il nome del file, assumiamo VETO 
                            # perché se fosse stato visivamente rilevante sarebbe rientrato nei risultati vettoriali.
                            pass
                        else:
                            r["score"] = r["score_testuale"]
                            r["score_tipo"] = "testo"
                            extra.append(r)
                
                risultati_raw = risultati_vettoriali + extra
            else:
                risultati_raw = risultati_vettoriali

        else:
            # CASO C – Solo filtri relazionali: nessun punteggio semantico applicabile
            risultati_raw = db.cerca_per_filtri(
                tipo=tipo, data_inizio=data_inizio, data_fine=data_fine,
                luogo=luogo_param, ids_vettoriali=None
            )
            if ids_coordinate is not None:
                risultati_raw = [r for r in risultati_raw if r["id"] in ids_coordinate]
            for r in risultati_raw:
                r["score"]      = None   # filtro esatto → sempre mostrato
                r["score_tipo"] = "filtro"

        # ── Filtro soglia ──────────────────────────────────────────
        # Applica la soglia specifica per tipo:
        #   immagine -> SOGLIA_IMMAGINE (20%) -- CLIP same-modal ha range 20-95%
        #   vettore  -> SOGLIA_VETTORE  (85%) -- CLIP cross-modal ha range 15-40%
        #   testo    -> SOGLIA_TESTO    (85%) -- keyword match, range 0-100%
        #   filtro   -> sempre incluso (nessun punteggio semantico)
        totale_raw = len(risultati_raw)
        risultati_filtrati = [
            r for r in risultati_raw
            if r.get("score") is None or _supera_soglia(r["score"], r.get("score_tipo", "filtro"))
        ]
        esclusi = totale_raw - len(risultati_filtrati)

        # ── Ordinamento esplicito per score decrescente ────────────
        # I risultati con score numerico vengono ordinati dalla percentuale
        # piu' alta alla piu' bassa; quelli senza score (filtro esatto) in fondo.
        risultati_filtrati.sort(
            key=lambda r: r["score"] if r.get("score") is not None else -1,
            reverse=True
        )

        return risultati_filtrati, esclusi

    # ──────────────────────────────────────────────────────────────────
    #  VISUALIZZAZIONE RISULTATI
    # ──────────────────────────────────────────────────────────────────
    def _mostra_risultati(self, risultati, esclusi=0):
        self.btn_avvia.configure(state="normal", text="🔍  Avvia Ricerca")
        self.lbl_spinner.configure(text="")
        self._svuota_risultati()
        self._thumbnail_refs.clear()

        if not risultati:
            msg = "Nessun risultato trovato per i filtri selezionati."
            # if esclusi > 0:
            #     plural = "i" if esclusi > 1 else "o"
            #     msg += f"\n({esclusi} risultat{plural} esclus{plural} perche' sotto soglia)"
            self._mostra_placeholder(msg)
            self.lbl_count_risultati.configure(text="0 risultati")
            return

        n = len(risultati)
        plural_r = "i" if n > 1 else "o"
        count_str = f"{n} risultat{plural_r} trovati"
        # if esclusi > 0:
        #     plural_e = "i" if esclusi > 1 else "o"
        #     count_str += f"  \u2022  \u26a0\ufe0f {esclusi} esclus{plural_e} (vettore < {SOGLIA_VETTORE:.0f}% | testo < {SOGLIA_TESTO:.0f}%)"
        self.lbl_count_risultati.configure(text=count_str)

        cols = getattr(self, '_last_res_cols', 2)
        for i, item in enumerate(risultati):
            row = i // cols
            col = i % cols
            self._crea_card_risultato(item, row, col)

        # Rimanda il reset dello scroll a dopo che il layout si e' stabilizzato,
        # cosi' i risultati appena creati partono sempre visibili dall'inizio.
        self.app.after(50, self._scroll_to_top)

    def _crea_card_risultato(self, item, row, col):
        """Crea una card risultato con thumbnail reale e badge di accuratezza."""
        card = ctk.CTkFrame(
            self.scroll_risultati,
            fg_color=self.app.color_card,
            border_color=self.app.color_border, border_width=1,
            corner_radius=15, height=250
        )
        card.grid(row=row, column=col, padx=8, pady=8, sticky="ew")
        card.grid_propagate(False)
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure((0, 1, 2, 3), weight=1)

        # Thumbnail
        box_thumb = ctk.CTkFrame(
            card, fg_color=self.app.color_bg,
            width=200, height=300, corner_radius=10
        )
        box_thumb.grid(row=0, column=0, rowspan=4, padx=10, pady=10, sticky="nsew")
        box_thumb.pack_propagate(False)
        self._carica_thumbnail(box_thumb, item)

        # Nome file
        ctk.CTkLabel(
            card, text=item["nome_file"],
            font=("Inter", 12, "bold"), text_color=self.app.color_text_main,
            anchor="w"
        ).grid(row=0, column=1, sticky="w", pady=(10, 0), padx=(5, 0))

        # Data e tipo
        tipo_icon = "🖼️" if item["tipo"] == "immagine" else "🎥"
        ctk.CTkLabel(
            card,
            text=f"{tipo_icon}  {item.get('data_inserimento', 'N/D')}",
            font=("Inter", 11), text_color=self.app.color_text_sec
        ).grid(row=1, column=1, sticky="w", padx=(5, 0))

        # Luogo e tag
        luogo_str = item.get("luogo", "") or "Sconosciuto"
        tags_str  = item.get("tags", "") or ""
        
        # Aggiungi timestamp frame per video
        timestamp_str = ""
        if item.get("tipo") == "video":
            ts = item.get("timestamp_sec")
            if ts is not None:
                mins = int(ts // 60)
                secs = int(ts % 60)
                timestamp_str = f"  ⏱ {mins:02d}:{secs:02d}"
        
        meta_text = f"📍 {luogo_str}"
        if tags_str:
            meta_text += f"  •  🏷️ {tags_str[:40]}"
        if timestamp_str:
            meta_text += timestamp_str
        
        ctk.CTkLabel(
            card, text=meta_text,
            font=("Inter", 10), text_color="#64748B",
            anchor="w", wraplength=220
        ).grid(row=2, column=1, sticky="w", padx=(5, 0))

        # # ── Badge accuratezza ──────────────────────────────────────
        # score      = item.get("score")
        # score_tipo = item.get("score_tipo", "filtro")
        # is_video   = item.get("tipo") == "video"
        # frame_idx  = item.get("frame_idx")
        # timestamp  = item.get("timestamp_sec")

        # if score is not None:
        #     # Soglia di riferimento per stabilire il colore del badge
        #     if score_tipo == "immagine":
        #         soglia_ref = SOGLIA_IMMAGINE
        #     elif score_tipo == "vettore":
        #         soglia_ref = SOGLIA_VETTORE
        #     else:
        #         soglia_ref = SOGLIA_TESTO
        #     margine      = score - soglia_ref          # quanto supera la soglia
        #     # Verde se supera la soglia di almeno 10 punti percentuali, altrimenti arancione
        #     badge_color  = "#16A34A" if margine >= 10.0 else "#D97706"

        #     if score_tipo == "immagine":
        #         tipo_icona = "\U0001f5bc"   # icona immagine
        #         tipo_label = "similarita'"
        #     elif score_tipo == "vettore":
        #         tipo_icona = "\U0001f537"
        #         tipo_label = "vettore"
        #     else:
        #         tipo_icona = "\U0001f524"
        #         tipo_label = "testo"
            
        #     # Aggiungi info frame per video
        #     frame_info = ""
        #     if is_video and timestamp is not None:
        #         mins = int(timestamp // 60)
        #         secs = int(timestamp % 60)
        #         frame_info = f"  t={mins:02d}:{secs:02d} (frame {frame_idx})"
            
        #     badge_text   = f"  {tipo_icona} {score:.1f}%  {tipo_label}{frame_info}  "

        #     badge_frame = ctk.CTkFrame(
        #         card, fg_color=badge_color, corner_radius=6
        #     )
        #     badge_frame.grid(row=3, column=1, sticky="w",
        #                      padx=(5, 0), pady=(0, 8))
        #     ctk.CTkLabel(
        #         badge_frame, text=badge_text,
        #         font=("Inter", 9, "bold"),
        #         text_color="#FFFFFF", fg_color="transparent"
        #     ).pack(padx=2, pady=1)
        # else:
        #     # Solo filtri relazionali → nessun punteggio semantico
        #     ctk.CTkLabel(
        #         card, text="\u2705  filtro esatto",
        #         font=("Inter", 9), text_color="#475569"
        #     ).grid(row=3, column=1, sticky="w", padx=(5, 0), pady=(0, 8))

        # Pulsante Download / Apri + Elimina (impilati nella stessa colonna)
        btn_col = ctk.CTkFrame(card, fg_color="transparent")
        btn_col.grid(row=0, column=2, rowspan=4, padx=8, pady=8, sticky="nsew")

        ctk.CTkButton(
            btn_col, text="APRI", anchor="center",
            font=("Inter", 10, "bold"),
            fg_color="transparent", text_color=self.app.color_text_main,
            hover_color="#334155", height=40, width=55,
            border_color=self.app.color_border, border_width=1, corner_radius=8,
            command=lambda p=item["percorso_file"]: self._apri_file(p)
        ).pack(expand=True)

        ctk.CTkButton(
            btn_col, text="🗑", anchor="center",
            font=("Inter", 16),
            fg_color="transparent", text_color="#EF4444",
            hover_color="#3F1D1D", border_width=1, border_color="#EF4444",
            height=32, width=55, corner_radius=8,
            command=lambda it=item: self._conferma_elimina(it)
        ).pack(expand=True)

    def _carica_thumbnail(self, container, item):
        """
        Carica la miniatura reale del file nella card.
        Se il file è un'immagine ed esiste sul disco, carica il file e lo ridimensiona;
        altrimenti, mostra un'emoji di fallback (es. video o file mancante).
        """
        percorso = item.get("percorso_file", "")
        tipo     = item.get("tipo", "")
        emoji    = "🖼️" if tipo == "immagine" else "🎥"

        if percorso and os.path.exists(percorso) and tipo == "immagine":
            try:
                img = Image.open(percorso)
                # NOTA: thumbnail() ridimensiona rispettando le proporzioni originali,
                # quindi le dimensioni finali NON sono necessariamente 80x90 (es. per
                # immagini molto larghe o molto strette). In precedenza CTkImage veniva
                # forzato a size=(80, 90) fisso, il che distorceva/"tagliava"
                # visivamente l'immagine quando le proporzioni non coincidevano.
                # Usando size=img.size (le dimensioni reali post-thumbnail) l'immagine
                # viene sempre mostrata per intero, non tagliata e senza distorsioni.
                img.thumbnail((200, 210))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                lbl = ctk.CTkLabel(container, image=ctk_img, text="")
                lbl.pack(expand=True)
                self._thumbnail_refs.append(ctk_img)
                return
            except Exception:
                pass

        # Fallback emoji
        ctk.CTkLabel(
            container, text=emoji, font=("Arial", 30)
        ).pack(expand=True)

    def _mostra_placeholder(self, testo):
        """Mostra un messaggio centrato nell'area risultati."""
        lbl = ctk.CTkLabel(
            self.scroll_risultati, text=testo,
            font=("Inter", 14, "italic"), text_color=self.app.color_text_sec
        )
        lbl.grid(row=0, column=0, columnspan=2, pady=60)

    def _svuota_risultati(self):
        for w in self.scroll_risultati.winfo_children():
            w.destroy()
        self._scroll_to_top()

    def _scroll_to_top(self):
        """
        Riporta lo scroll dell'area risultati in cima. Senza questo reset, dopo
        aver scorso in basso e avviato una nuova ricerca (tramite testo/filtri/
        immagine di reference), i nuovi risultati ereditavano la vecchia
        posizione di scorrimento: la prima riga appariva parzialmente fuori
        vista ("tagliata") finche' l'utente non scorreva manualmente in alto.
        """
        try:
            self.scroll_risultati._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    #  AZIONI
    # ──────────────────────────────────────────────────────────────────
    def _mostra_prompt_reference(self):
        """Stato iniziale/di reset del riquadro: nessuna immagine selezionata."""
        for w in self.frame_img_reference.winfo_children():
            w.destroy()
        self._ref_preview_img = None

        lbl_prompt = ctk.CTkLabel(
            self.frame_img_reference, text="Carica Immagine Reference",
            font=("Inter", 12), text_color=self.app.color_text_sec
        )
        lbl_prompt.place(relx=0.5, rely=0.5, anchor="center")

        # Bind su ButtonRelease (non Button-1/press): e' la semantica
        # standard di un "click" e riduce il rischio che eventi residui
        # generati alla chiusura del file dialog vengano interpretati come
        # un nuovo click (vedi nota in seleziona_reference).
        for w in (self.frame_img_reference, lbl_prompt):
            w.bind("<ButtonRelease-1>", lambda e: self.seleziona_reference())

    def _mostra_preview_reference(self, percorso):
        """
        Mostra la miniatura reale dell'immagine reference selezionata
        direttamente nel riquadro sopra "Avvia Ricerca" (al posto del solo
        nome file testuale).
        """
        for w in self.frame_img_reference.winfo_children():
            w.destroy()
        try:
            img = Image.open(percorso)
            img.thumbnail((70, 70))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._ref_preview_img = ctk_img  # mantieni riferimento per evitare GC

            # Container con layout orizzontale
            container_preview = ctk.CTkFrame(self.frame_img_reference, fg_color="transparent")
            container_preview.pack(fill="both", expand=True, padx=8, pady=8)
            container_preview.grid_columnconfigure(1, weight=1)

            # Thumbnail con bordo
            box_thumb = ctk.CTkFrame(
                container_preview, fg_color=self.app.color_card,
                border_color=self.app.color_accent, border_width=2,
                corner_radius=8, width=70, height=70
            )
            box_thumb.grid(row=0, column=0, padx=(0, 10))
            box_thumb.pack_propagate(False)

            lbl_img = ctk.CTkLabel(box_thumb, image=ctk_img, text="")
            lbl_img.pack(expand=True)

            # Info file (nome)
            nome_file = os.path.basename(percorso)
            lbl_nome = ctk.CTkLabel(
                container_preview, text=nome_file,
                font=("Inter", 11), text_color=self.app.color_text_main,
                anchor="w", wraplength=110, justify="left"
            )
            lbl_nome.grid(row=0, column=1, sticky="w")

            # Bottone Rimuovi (X)
            btn_rimuovi = ctk.CTkButton(
                container_preview, text="✕",
                font=("Inter", 11, "bold"), width=28, height=28,
                fg_color="transparent", text_color=self.app.color_text_sec,
                hover_color="#EF4444", corner_radius=6,
                command=self._rimuovi_reference
            )
            btn_rimuovi.grid(row=0, column=2, padx=(5, 0))

            # Clic sulla miniatura o sul nome -> permette di cambiare immagine
            for w in (box_thumb, lbl_img, lbl_nome):
                w.bind("<ButtonRelease-1>", lambda e: self.seleziona_reference())
        except Exception as e:
            print(f"[Ricerca] Errore anteprima reference: {e}")
            self._mostra_prompt_reference()

    def _on_text_typing(self, event=None):
        """Se l'utente digita del testo, azzera l'immagine reference selezionata per esclusione."""
        if self.search_entry.get().strip() and self.ricerca_img_reference:
            self.ricerca_img_reference = None
            self._mostra_prompt_reference()

    def _rimuovi_reference(self):
        """
        Rimuove l'immagine reference selezionata e ripristina l'interfaccia,
        senza riaprire subito il selettore file.
        """
        self.ricerca_img_reference = None
        # Blocca temporaneamente l'apertura del file dialog: il pulsante ✕
        # che ha appena innescato questa funzione viene distrutto e sostituito
        # da un nuovo widget cliccabile ("Carica Immagine Reference") nella
        # stessa posizione. Su alcune combinazioni Windows puo' capitare che
        # l'evento di click residuo raggiunga il nuovo widget e riapra subito
        # la finestra di selezione: la guardia + il rebuild rimandato al giro
        # successivo dell'event loop evitano l'effetto.
        self._dialog_reference_aperto = True
        self.app.after(1, self._mostra_prompt_reference)
        self.app.after(400, lambda: setattr(self, "_dialog_reference_aperto", False))

    def seleziona_reference(self):
        """
        Apre un file explorer per permettere all'utente di selezionare un'immagine.
        Questa immagine sara' convertita in un embedding e usata per cercare altri media
        visivamente simili (Reverse Image Search). Mostra un'anteprima nel pannello.

        NOTA: e' protetta da una guardia anti-riapertura. Il riquadro
        reference contiene piu' widget cliccabili sovrapposti (frame, label,
        thumbnail) che vengono distrutti e ricreati appena il file viene
        selezionato; su alcune combinazioni Windows/tema del file dialog puo'
        capitare che, chiudendo il dialog (specialmente con doppio click sul
        file), un secondo evento di click "residuo" arrivi al widget
        appena ricreato nella stessa posizione, riaprendo subito il dialog.
        La guardia impedisce che una seconda chiamata parta finche' la
        precedente non e' conclusa da un breve istante.
        """
        if self._dialog_reference_aperto:
            return
        self._dialog_reference_aperto = True
        try:
            file_sel = filedialog.askopenfilename(
                title="Seleziona Immagine di Reference",
                filetypes=[("Immagini", "*.png *.jpg *.jpeg *.webp *.bmp")]
            )
            if file_sel:
                self.ricerca_img_reference = file_sel

                # Azzera il campo di ricerca testuale per mutua esclusione
                self.search_entry.delete(0, "end")

                # Mostra anteprima (miniatura) nel riquadro
                self._mostra_preview_reference(file_sel)
        finally:
            # Riabilita con un piccolo ritardo, per assorbire eventuali click
            # residui generati alla chiusura del dialog.
            self.app.after(400, lambda: setattr(self, "_dialog_reference_aperto", False))

    def azzera_filtri(self):
        """
        Svuota tutti i campi di ricerca (testo, date, luogo, immagine reference)
        e reimposta l'interfaccia allo stato iniziale, pulendo i risultati.
        """
        self.search_entry.delete(0, "end")
        self.luogo_entry.delete(0, "end")
        self.date_inizio_entry.delete(0, "end")
        self.date_fine_entry.delete(0, "end")
        self.app.filtro_tipo.set("Tutto")
        self.ricerca_img_reference = None
        self._dialog_reference_aperto = True
        self.app.after(1, self._mostra_prompt_reference)
        self.app.after(400, lambda: setattr(self, "_dialog_reference_aperto", False))
        self._svuota_risultati()
        self.lbl_count_risultati.configure(text="")
        self._mostra_placeholder("Usa i filtri a sinistra e clicca 'Avvia Ricerca'")

    def _apri_file(self, percorso):
        """Apre il file o la sua cartella contenitore."""
        if not os.path.exists(percorso):
            messagebox.showerror("Errore", f"File non trovato:\n{percorso}")
            return
        try:
            # Su Windows: apre esplora risorse e seleziona il file
            subprocess.run(["explorer", "/select,", os.path.normpath(percorso)])
        except Exception:
            # Fallback: apre direttamente il file
            os.startfile(percorso)

    def _on_errore_ricerca(self, messaggio):
        self.btn_avvia.configure(state="normal", text="🔍  Avvia Ricerca")
        self.lbl_spinner.configure(text="")
        messagebox.showerror("Errore Ricerca", f"Si è verificato un errore:\n{messaggio}")

    def _conferma_elimina(self, item):
        """
        Chiede conferma esplicita prima di eliminare un file, trattandosi di
        un'operazione irreversibile. Se l'utente conferma, il file viene
        rimosso automaticamente sia dalla cartella uploads sia dal database
        (DuckDB + embedding ChromaDB), poi la ricerca corrente viene
        rieseguita per aggiornare la vista dei risultati.
        """
        nome = item.get("nome_file", "questo file")
        conferma = messagebox.askyesno(
            "Conferma eliminazione",
            f"Sei sicuro di voler eliminare \"{nome}\"?\n\n"
            "Il file verrà rimosso in modo permanente sia dalla cartella "
            "uploads sia dal database. L'operazione è irreversibile.",
            icon="warning"
        )
        if not conferma:
            return

        db = Database()
        ok, errore = db.elimina_file(item["id"])
        if ok:
            try:
                self.app.aggiorna_statistiche_storage()
            except Exception:
                pass
            # Rieffettua la ricerca corrente per rimuovere la card ed
            # eventualmente far scorrere su un risultato che era escluso.
            self.avvia_ricerca()
        else:
            messagebox.showerror(
                "Errore eliminazione",
                f"Impossibile eliminare \"{nome}\":\n{errore}"
            )