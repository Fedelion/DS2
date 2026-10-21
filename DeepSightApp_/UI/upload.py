"""
DeepSight - Schermata Upload
Gestisce il caricamento di immagini e video:
  1. Coda di file (possibilità di selezionarne/trascinarne diversi contemporaneamente)
  2. Copia nello storage locale
  3. Analisi AI in thread separato (non blocca la UI)
  4. Salvataggio nel database
La pipeline elabora i file della coda uno alla volta, mostrando lo stato
di avanzamento di ciascun elemento (in attesa / elaborazione / completato / errore).
"""

import os
import sys
import shutil
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

# Permette import dalla radice del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import Config_Start.config as config
from AI_Model.AI_engine import elabora_file
from Database.database   import Database

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False


class UploadFrame(ctk.CTkFrame):
    """
    Interfaccia grafica per l'upload di file multimediali (immagini e video).
    Consente di accodare più file contemporaneamente (selezione multipla o drag & drop),
    impostare metadati manuali condivisi (luogo, tag) e avviare l'elaborazione
    dell'intera coda in un thread separato, così da non bloccare la UI.
    """
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.coda = []                   # lista di dict: {path, nome, dim_mb, ext, tipo, stato, row, status_label, remove_btn}
        self._elaborazione_in_corso = False

        self.grid_columnconfigure(0, weight=6)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(1, weight=2)   # drop zone + pannello destro
        self.grid_rowconfigure(2, weight=3)   # coda

        # ── Titolo ───────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Multimedia Upload",
            font=("Inter", 24, "bold"), text_color=self.app.color_text_main
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))

        # ── Area Drop / Click ─────────────────────────────────────────
        self.drop_zone = ctk.CTkFrame(
            self, fg_color=self.app.color_card,
            border_color=self.app.color_border, border_width=1, corner_radius=20,
            cursor="hand2"
        )
        self.drop_zone.grid(row=1, column=0, sticky="nsew", padx=(0, 25), pady=(0, 10))

        self.drop_zone.bind("<Enter>", lambda e: self.drop_zone.configure(fg_color="#243249"))
        self.drop_zone.bind("<Leave>", lambda e: self.drop_zone.configure(fg_color=self.app.color_card))
        self.drop_zone.bind("<Button-1>", lambda e: self.seleziona_file())

        self.up_icon = ctk.CTkLabel(
            self.drop_zone, text="☁️", font=("Arial", 50),
            text_color=self.app.color_accent
        )
        self.up_icon.place(relx=0.5, rely=0.28, anchor="center")

        self.drop_text = ctk.CTkLabel(
            self.drop_zone, text="Trascina qui o clicca per aggiungere",
            font=("Inter", 16, "bold"), text_color=self.app.color_text_main
        )
        self.drop_text.place(relx=0.5, rely=0.48, anchor="center")

        self.limits_text = ctk.CTkLabel(
            self.drop_zone, text="Più immagini o video (Max 200MB cad.)",
            font=("Inter", 12), text_color=self.app.color_text_sec
        )
        self.limits_text.place(relx=0.5, rely=0.62, anchor="center")

        # Barra di avanzamento (nascosta di default)
        self.progress_bar = ctk.CTkProgressBar(
            self.drop_zone, mode="determinate",
            fg_color=self.app.color_border, progress_color=self.app.color_accent,
            height=6, corner_radius=3
        )
        self.progress_bar.place(relx=0.5, rely=0.84, anchor="center", relwidth=0.7)
        self.progress_bar.set(0)
        self.progress_bar.place_forget()

        self.status_label = ctk.CTkLabel(
            self.drop_zone, text="", font=("Inter", 11, "italic"),
            text_color=self.app.color_text_sec
        )
        self.status_label.place(relx=0.5, rely=0.92, anchor="center")
        self.status_label.place_forget()

        for widget in [self.up_icon, self.drop_text, self.limits_text]:
            widget.bind("<Button-1>", lambda e: self.seleziona_file())

        # Registrazione dei widget per il Drag & Drop
        if HAS_DND:
            try:
                for widget in [self.drop_zone, self.up_icon, self.drop_text, self.limits_text]:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self.gestisci_drop)
            except Exception as e:
                print(f"[Upload] Errore durante la registrazione del Drag & Drop: {e}")

        # ── Pannello Destro ───────────────────────────────────────────
        # NOTA: il luogo viene ricavato automaticamente dai metadata GPS
        # dell'immagine (reverse geocoding), non più inserito manualmente.
        self.right_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.right_panel.grid(row=1, column=1, sticky="nsew")
        self.right_panel.grid_rowconfigure(2, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.right_panel, text="🏷️ TAG (separati da virgola)",
            font=("Inter", 12, "bold"), text_color=self.app.color_text_sec
        ).grid(row=0, column=0, sticky="w", pady=(5, 0))

        ctk.CTkLabel(
            self.right_panel,
            text="Seleziona uno o più file in coda (clic sulla riga), poi applica il tag solo a loro.",
            font=("Inter", 12, "italic"), text_color=self.app.color_text_sec,
            anchor="w", justify="left", wraplength=450
        ).grid(row=1, column=0, sticky="w", pady=(0, 5))

        self.placeholder_text = "Esempio: cane, gatto, natura..."
        self.tag_entry = ctk.CTkTextbox(
            self.right_panel, fg_color=self.app.color_card, text_color="#475569",
            border_color=self.app.color_border, border_width=1,
            corner_radius=12, font=("Inter", 14)
        )
        self.tag_entry.grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        self.tag_entry.insert("0.0", self.placeholder_text)
        self.tag_entry.bind("<FocusIn>",  self._rimuovi_placeholder)
        self.tag_entry.bind("<FocusOut>", self._inserisci_placeholder)

        self.btn_applica_tag = ctk.CTkButton(
            self.right_panel, text="🏷️  Applica Tag ai file selezionati",
            fg_color="transparent", hover_color="#243249",
            text_color=self.app.color_accent, border_width=1,
            border_color=self.app.color_accent, corner_radius=12,
            font=("Inter", 12, "bold"), height=36,
            command=self._applica_tag_selezionati
        )
        self.btn_applica_tag.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.process_btn = ctk.CTkButton(
            self.right_panel, text="💾  Salva e Analizza",
            fg_color=self.app.color_accent, hover_color="#0EA5E9",
            text_color="#0F172A", corner_radius=12,
            font=("Inter", 14, "bold"), height=45,
            command=self.avvia_pipeline_upload
        )
        self.process_btn.grid(row=4, column=0, sticky="ew")

        # ── Sezione Coda ──────────────────────────────────────────────
        self.coda_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.coda_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        self.coda_frame.grid_columnconfigure(0, weight=1)
        self.coda_frame.grid_rowconfigure(1, weight=1)

        header_coda = ctk.CTkFrame(self.coda_frame, fg_color="transparent")
        header_coda.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header_coda.grid_columnconfigure(0, weight=1)

        self.lbl_titolo_coda = ctk.CTkLabel(
            header_coda, text="📋  CODA DI CARICAMENTO",
            font=("Inter", 13, "bold"), text_color=self.app.color_text_sec
        )
        self.lbl_titolo_coda.grid(row=0, column=0, sticky="w")

        self.btn_svuota = ctk.CTkButton(
            header_coda, text="Svuota", width=80, height=28,
            font=("Inter", 11), fg_color="transparent",
            border_width=1, border_color=self.app.color_border,
            text_color=self.app.color_text_sec, corner_radius=8,
            command=self._svuota_coda
        )
        self.btn_svuota.grid(row=0, column=1, sticky="e")

        self.scroll_coda = ctk.CTkScrollableFrame(
            self.coda_frame, fg_color=self.app.color_card,
            border_color=self.app.color_border, border_width=1, corner_radius=12
        )
        self.scroll_coda.grid(row=1, column=0, sticky="nsew")

        self._mostra_coda_vuota()

    def re_layout(self, is_mobile, width):
        """Ricalcola il layout della pagina Upload in base alla larghezza della finestra."""
        if is_mobile:
            self.drop_zone.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 10))
            self.right_panel.grid(row=2, column=0, sticky="nsew")
            self.coda_frame.grid(row=3, column=0, columnspan=1, sticky="nsew", pady=(5, 0))
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)
            self.grid_rowconfigure(1, weight=1)
            self.grid_rowconfigure(2, weight=0) # right panel
            self.grid_rowconfigure(3, weight=2) # coda
        else:
            self.drop_zone.grid(row=1, column=0, sticky="nsew", padx=(0, 25), pady=(0, 10))
            self.right_panel.grid(row=1, column=1, sticky="nsew")
            self.coda_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
            self.grid_columnconfigure(0, weight=6)
            self.grid_columnconfigure(1, weight=4)
            self.grid_rowconfigure(1, weight=2)
            self.grid_rowconfigure(2, weight=3) # coda
            self.grid_rowconfigure(3, weight=0)

    # ──────────────────────────────────────────────────────────────────
    #  PLACEHOLDER TAG
    # ──────────────────────────────────────────────────────────────────
    def _rimuovi_placeholder(self, event):
        if self.tag_entry.get("0.0", "end-1c") == self.placeholder_text:
            self.tag_entry.delete("0.0", "end")
            self.tag_entry.configure(text_color=self.app.color_text_main)

    def _inserisci_placeholder(self, event):
        if not self.tag_entry.get("0.0", "end-1c").strip():
            self.tag_entry.insert("0.0", self.placeholder_text)
            self.tag_entry.configure(text_color="#475569")

    # ──────────────────────────────────────────────────────────────────
    #  SELEZIONE / AGGIUNTA FILE ALLA CODA
    # ──────────────────────────────────────────────────────────────────
    def seleziona_file(self):
        """Apre il dialog di sistema in modalità multiselezione e accoda i file validi."""
        if self._elaborazione_in_corso:
            return
        files = filedialog.askopenfilenames(
            title="Seleziona file multimediali",
            filetypes=[(
                "File Multimediali",
                " ".join(f"*{e}" for e in config.ESTENSIONI_IMMAGINI + config.ESTENSIONI_VIDEO)
            )]
        )
        if files:
            self._aggiungi_piu_files(list(files))

    def gestisci_drop(self, event):
        """Gestisce il rilascio (drop) di uno o più file sull'area di upload."""
        if self._elaborazione_in_corso:
            return
        if not event.data:
            return
        files = self.tk.splitlist(event.data)
        if files:
            self._aggiungi_piu_files(list(files))

    def _aggiungi_piu_files(self, files):
        """Valida e accoda tutti i file passati, mostrando un riepilogo."""
        aggiunti, saltati = 0, 0
        for f in files:
            if self._aggiungi_alla_coda(f):
                aggiunti += 1
            else:
                saltati += 1
        if aggiunti:
            self._aggiorna_testo_drop(aggiunti)
        if saltati:
            messagebox.showwarning(
                "Alcuni file ignorati",
                f"{saltati} file non sono stati aggiunti (estensione non supportata, "
                f"superano i {config.MAX_UPLOAD_MB}MB o sono già in coda)."
            )

    def _aggiungi_alla_coda(self, percorso):
        """Valida un singolo file e lo aggiunge alla coda. Ritorna True se accodato."""
        if not os.path.exists(percorso):
            return False

        # Evita duplicati nella stessa coda
        if any(item["path"] == percorso for item in self.coda):
            return False

        nome = os.path.basename(percorso)
        ext = os.path.splitext(nome)[1].lower()

        if ext not in config.ESTENSIONI_IMMAGINI and ext not in config.ESTENSIONI_VIDEO:
            return False

        try:
            dim_mb = os.path.getsize(percorso) / (1024 * 1024)
        except Exception:
            dim_mb = 0.0

        if dim_mb > config.MAX_UPLOAD_MB:
            return False

        tipo = "immagine" if ext in config.ESTENSIONI_IMMAGINI else "video"

        item = {
            "path": percorso, "nome": nome, "dim_mb": dim_mb,
            "ext": ext, "tipo": tipo, "stato": "in_attesa",
            "selezionato": False, "tag_extra": []
        }
        self.coda.append(item)
        self._crea_riga_coda(item)
        self._aggiorna_conteggio_coda()
        return True

    # ──────────────────────────────────────────────────────────────────
    #  RENDER CODA
    # ──────────────────────────────────────────────────────────────────
    def _genera_thumbnail_coda(self, item):
        """
        Genera una miniatura reale (CTkImage) per l'elemento della coda:
        per le immagini ridimensiona il file stesso, per i video estrae ed
        usa il primo frame. Ritorna None (fallback all'emoji) se il file
        non e' leggibile o in caso di qualunque errore.
        """
        percorso = item.get("path", "")
        try:
            if item["tipo"] == "immagine":
                img = Image.open(percorso).convert("RGB")
            else:
                import cv2
                cap = cv2.VideoCapture(percorso)
                ok, frame = cap.read()
                cap.release()
                if not ok or frame is None:
                    return None
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # thumbnail() rispetta le proporzioni originali: usiamo poi
            # size=img.size (le dimensioni reali post-resize) invece di un
            # valore fisso, cosi' l'anteprima non risulta mai distorta.
            img.thumbnail((40, 40))
            return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception as e:
            print(f"[Upload] Errore generazione miniatura coda ({percorso}): {e}")
            return None

    def _mostra_coda_vuota(self):
        self.lbl_coda_vuota = ctk.CTkLabel(
            self.scroll_coda,
            text="Nessun file in coda.\nAggiungi immagini o video per iniziare.",
            font=("Inter", 13, "italic"), text_color=self.app.color_text_sec
        )
        self.lbl_coda_vuota.pack(expand=True, pady=30)

    def _crea_riga_coda(self, item):
        """Crea la riga UI per un elemento della coda."""
        # Rimuovi il placeholder "coda vuota" alla prima aggiunta
        if hasattr(self, "lbl_coda_vuota"):
            self.lbl_coda_vuota.destroy()
            delattr(self, "lbl_coda_vuota")

        # border_width impostato fin da subito (colore = sfondo, quindi invisibile)
        # cosi' evidenziare/deselezionare la riga cambia solo il colore del
        # bordo e non causa scatti di layout.
        row = ctk.CTkFrame(
            self.scroll_coda, fg_color=self.app.color_bg, corner_radius=10,
            border_width=2, border_color=self.app.color_bg, cursor="hand2"
        )
        row.pack(fill="x", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=0)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=0)
        row.grid_columnconfigure(3, weight=0)

        # Riquadro miniatura: mostra l'anteprima reale del file (frame del
        # video o immagine ridimensionata) al posto della sola emoji quando
        # possibile; dimensione fissa cosi' la riga non "salta" a seconda
        # che la miniatura sia disponibile o meno.
        thumb_box = ctk.CTkFrame(
            row, fg_color=self.app.color_card, corner_radius=8,
            width=44, height=44
        )
        thumb_box.grid(row=0, column=0, padx=(8, 10), pady=8)
        thumb_box.pack_propagate(False)

        ctk_thumb = self._genera_thumbnail_coda(item)
        if ctk_thumb is not None:
            item["_thumb_img"] = ctk_thumb  # mantiene il riferimento (evita GC)
            icon_lbl = ctk.CTkLabel(thumb_box, image=ctk_thumb, text="")
        else:
            icon = "🖼️" if item["tipo"] == "immagine" else "🎥"
            icon_lbl = ctk.CTkLabel(thumb_box, text=icon, font=("Arial", 20))
        icon_lbl.pack(expand=True)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=6)
        nome_lbl = ctk.CTkLabel(
            info, text=item["nome"], font=("Inter", 12, "bold"),
            text_color=self.app.color_text_main, anchor="w"
        )
        nome_lbl.pack(anchor="w")
        size_lbl = ctk.CTkLabel(
            info, text=f"{item['dim_mb']:.1f} MB  •  {item['tipo'].capitalize()}",
            font=("Inter", 10), text_color=self.app.color_text_sec, anchor="w"
        )
        size_lbl.pack(anchor="w")
        tag_lbl = ctk.CTkLabel(
            info, text="", font=("Inter", 10, "italic"),
            text_color=self.app.color_accent, anchor="w"
        )
        tag_lbl.pack(anchor="w")

        status_label = ctk.CTkLabel(
            row, text="⏳ In attesa", font=("Inter", 11),
            text_color="#94A3B8"
        )
        status_label.grid(row=0, column=2, padx=10, pady=8)

        remove_btn = ctk.CTkButton(
            row, text="✖", width=30, height=30,
            fg_color="transparent", hover_color="#334155",
            border_width=1, border_color=self.app.color_border,
            text_color=self.app.color_text_sec, corner_radius=8,
            command=lambda it=item: self._rimuovi_dalla_coda(it)
        )
        remove_btn.grid(row=0, column=3, padx=(0, 8), pady=8)

        # Clic su riga/miniatura/info/nome/dimensione -> seleziona/deseleziona
        # il file per l'applicazione mirata del tag (il pulsante "rimuovi"
        # resta escluso per non interferire con la sua azione).
        for widget in (row, thumb_box, icon_lbl, info, nome_lbl, size_lbl):
            widget.bind("<Button-1>", lambda e, it=item: self._toggle_selezione(it))

        item["tag_label"] = tag_lbl

        item["row"] = row
        item["status_label"] = status_label
        item["remove_btn"] = remove_btn

    # ──────────────────────────────────────────────────────────────────
    #  SELEZIONE FILE IN CODA + TAG MIRATO
    # ──────────────────────────────────────────────────────────────────
    def _toggle_selezione(self, item):
        """Seleziona/deseleziona un elemento della coda cliccando sulla sua riga."""
        if self._elaborazione_in_corso:
            return
        item["selezionato"] = not item.get("selezionato", False)
        self._aggiorna_evidenza_riga(item)

    def _aggiorna_evidenza_riga(self, item):
        """Aggiorna il colore del bordo della riga per riflettere lo stato di selezione."""
        row = item.get("row")
        if not row:
            return
        row.configure(
            border_color=self.app.color_accent if item.get("selezionato") else self.app.color_bg
        )

    def _applica_tag_selezionati(self):
        """
        Applica i tag scritti nella casella TAG (in alto a destra) solo ai file
        attualmente selezionati nella coda, invece che a tutta la coda.
        I tag vengono aggiunti a quelli eventualmente già assegnati al singolo
        file (senza duplicati), e usati poi in fase di elaborazione insieme
        agli eventuali tag "di base".
        """
        if self._elaborazione_in_corso:
            return

        selezionati = [it for it in self.coda if it.get("selezionato")]
        if not selezionati:
            messagebox.showwarning(
                "Nessun file selezionato",
                "Seleziona almeno un file nella coda (clicca sulla riga) prima di applicare il tag."
            )
            return

        tag_raw = self.tag_entry.get("0.0", "end-1c").strip()
        if tag_raw == self.placeholder_text:
            tag_raw = ""
        nuovi_tag = [t.strip() for t in tag_raw.split(",") if t.strip()]
        if not nuovi_tag:
            messagebox.showwarning(
                "Tag mancante",
                "Inserisci almeno un tag nella casella TAG prima di applicarlo."
            )
            return

        for item in selezionati:
            esistenti = item.get("tag_extra", [])
            esistenti_lower = {t.lower() for t in esistenti}
            for t in nuovi_tag:
                if t.lower() not in esistenti_lower:
                    esistenti.append(t)
                    esistenti_lower.add(t.lower())
            item["tag_extra"] = esistenti

            if item.get("tag_label"):
                item["tag_label"].configure(text=f"🏷️ {', '.join(esistenti)}")

            # Deseleziona dopo l'applicazione, cosi' e' chiaro cosa e' stato taggato
            item["selezionato"] = False
            self._aggiorna_evidenza_riga(item)

        messagebox.showinfo(
            "Tag applicati",
            f"Tag \"{', '.join(nuovi_tag)}\" applicati a {len(selezionati)} file selezionati."
        )

    def _rimuovi_dalla_coda(self, item):
        if self._elaborazione_in_corso:
            return
        if item["row"]:
            item["row"].destroy()
        if item in self.coda:
            self.coda.remove(item)
        self._aggiorna_conteggio_coda()
        if not self.coda and not hasattr(self, "lbl_coda_vuota"):
            self._mostra_coda_vuota()

    def _svuota_coda(self):
        if self._elaborazione_in_corso:
            return
        for item in list(self.coda):
            if item.get("row"):
                item["row"].destroy()
        self.coda.clear()
        self._aggiorna_conteggio_coda()
        self._mostra_coda_vuota()

    def _aggiorna_conteggio_coda(self):
        n = len(self.coda)
        self.lbl_titolo_coda.configure(
            text=f"📋  CODA DI CARICAMENTO  ({n} file)" if n else "📋  CODA DI CARICAMENTO"
        )
        if n:
            self.process_btn.configure(text=f"💾  Salva e Analizza ({n})")
        else:
            self.process_btn.configure(text="💾  Salva e Analizza")

    def _aggiorna_testo_drop(self, n):
        self.drop_text.configure(
            text=f"✅ {n} file in coda",
            text_color=self.app.color_accent
        )

    # ──────────────────────────────────────────────────────────────────
    #  PIPELINE CODA → AI → DB (thread separato)
    # ──────────────────────────────────────────────────────────────────
    def avvia_pipeline_upload(self):
        """
        Avvia l'elaborazione dell'intera coda. I file vengono processati uno
        alla volta in un thread separato; lo stato di ciascun elemento viene
        aggiornato nella UI man mano che procede.
        """
        if self._elaborazione_in_corso:
            return
        if not self.coda:
            messagebox.showwarning("Attenzione", "La coda è vuota: aggiungi dei file!")
            return

        # Metadati condivisi (letti una volta sola).
        # Il luogo NON è più inserito manualmente: viene ricavato in automatico
        # dai metadata GPS dell'immagine/video (reverse geocoding).
        tag_raw = self.tag_entry.get("0.0", "end-1c").strip()
        if tag_raw == self.placeholder_text:
            tag_raw = ""
        tag_base = [t.strip() for t in tag_raw.split(",") if t.strip()]

        self._imposta_stato_elaborazione(True)
        totale = len(self.coda)

        def _thread_coda():
            completati, saltati, errori = 0, 0, 0
            for idx, item in enumerate(self.coda):
                self.app.after(0, self._set_stato_item, item, "elaborazione",
                               "⚙️  Elaborazione...")
                self.app.after(0, self._set_progress, (idx) / totale)

                try:
                    ok = self._processa_file_singolo(item, tag_base, "")
                    if ok is True:
                        completati += 1
                        self.app.after(0, self._set_stato_item, item, "completato",
                                       "✅  Completato")
                    elif ok == "dup":
                        saltati += 1
                        self.app.after(0, self._set_stato_item, item, "saltato",
                                       "⚠️  Già presente")
                    else:
                        errori += 1
                        self.app.after(0, self._set_stato_item, item, "errore",
                                       "❌  Errore")
                except Exception as e:
                    errori += 1
                    self.app.after(0, self._set_stato_item, item, "errore",
                                   "❌  Errore")
                    print(f"[Upload] Errore file {item['nome']}: {e}")

                self.app.after(0, self._set_progress, (idx + 1) / totale)

            self.app.after(0, self._on_coda_completata, completati, saltati, errori)

        threading.Thread(target=_thread_coda, daemon=True).start()

    def _processa_file_singolo(self, item, tag_base, luogo_manuale):
        """
        Elabora un singolo file della coda:
        copia su storage, analisi AI, salvataggio DB.
        Ritorna True (ok), "dup" (duplicato), False (errore generico).
        """
        percorso_src = item["path"]
        nome_file = item["nome"]
        ext = item["ext"]

        cartella_dest = config.IMG_DIR if ext in config.ESTENSIONI_IMMAGINI else config.VIDEO_DIR
        percorso_finale = os.path.join(cartella_dest, nome_file)

        # Controllo duplicati: ci basiamo sul record nel DB, NON sulla presenza
        # del file su disco. In questo modo, dopo un reset del database (file
        # cancellati) i media gia' presenti nella cartella uploads vengono
        # regolarmente re-indicizzati invece di essere scartati come "gia' presenti".
        db = Database()
        esistente = db.conn.execute(
            "SELECT id FROM file_multimediali WHERE nome_file = ? OR percorso_file = ?",
            [nome_file, percorso_finale]
        ).fetchone()
        if esistente:
            return "dup"

        # 1. Copia nello storage
        shutil.copy2(percorso_src, percorso_finale)

        # 2. Analisi AI
        risultato_ai = elabora_file(percorso_finale, lambda m: None)

        # Tag di base (condivisi) + tag mirati applicati alla selezione in coda
        # + parole OCR (specifiche del singolo file)
        tag_list = list(tag_base)
        tag_list_lower = {t.lower() for t in tag_list}
        for t in item.get("tag_extra", []):
            if t.lower() not in tag_list_lower:
                tag_list.append(t)
                tag_list_lower.add(t.lower())
        embedding = None
        frame_embeddings = None
        testo_ocr = ""
        data_creazione = "Sconosciuta"
        gps_finale = None
        luogo_finale = luogo_manuale or "Sconosciuto"
        num_facce = 0
        tipo_file = "immagine" if ext in config.ESTENSIONI_IMMAGINI else "video"

        if risultato_ai:
            embedding = risultato_ai.get("embedding_clip")
            frame_embeddings = risultato_ai.get("frame_embeddings")
            testo_ocr = risultato_ai.get("testo_ocr", "")
            data_creazione = risultato_ai.get("data_creazione", "Sconosciuta")
            gps_finale = risultato_ai.get("gps")
            num_facce = risultato_ai.get("num_facce", 0)
            if not luogo_manuale:
                luogo_finale = risultato_ai.get("luogo", "Sconosciuto")
            if testo_ocr:
                parole_ocr = [w for w in testo_ocr.split()[:5] if len(w) > 3]
                tag_list.extend(parole_ocr)

        db.insert_multimedia(
            tipo=tipo_file,
            percorso_file=percorso_finale,
            tag_list=tag_list,
            luogo=luogo_finale,
            gps=gps_finale,
            data_creazione=data_creazione,
            embedding_clip=embedding,
            frame_embeddings=frame_embeddings,
            testo_ocr=testo_ocr,
            num_facce=num_facce,
        )
        return True

    # ──────────────────────────────────────────────────────────────────
    #  AGGIORNAMENTI UI (thread-safe)
    # ──────────────────────────────────────────────────────────────────
    def _set_stato_item(self, item, stato, testo):
        if item.get("status_label"):
            colori = {
                "in_attesa": "#94A3B8",
                "elaborazione": "#38BDF8",
                "completato": "#16A34A",
                "saltato": "#D97706",
                "errore": "#EF4444",
            }
            item["status_label"].configure(
                text=testo, text_color=colori.get(stato, "#94A3B8")
            )
        # Disabilita il pulsante di rimozione durante l'elaborazione
        if item.get("remove_btn") and stato == "elaborazione":
            item["remove_btn"].configure(state="disabled")
        elif item.get("remove_btn") and stato in ("completato", "saltato", "errore"):
            item["remove_btn"].configure(state="disabled")

    def _set_progress(self, valore):
        self.progress_bar.set(max(0.0, min(1.0, valore)))

    # ──────────────────────────────────────────────────────────────────
    #  CALLBACK UI
    # ──────────────────────────────────────────────────────────────────
    def _aggiorna_status(self, messaggio):
        self.app.after(0, lambda: self.status_label.configure(text=messaggio))

    def _imposta_stato_elaborazione(self, attivo: bool):
        self._elaborazione_in_corso = attivo
        if attivo:
            self.process_btn.configure(state="disabled", text="⏳  Elaborazione...")
            self.btn_svuota.configure(state="disabled")
            self.btn_applica_tag.configure(state="disabled")
            self.progress_bar.place(relx=0.5, rely=0.84, anchor="center", relwidth=0.7)
            self.status_label.place(relx=0.5, rely=0.92, anchor="center")
            self.progress_bar.set(0)
        else:
            self.progress_bar.place_forget()
            self.status_label.place_forget()
            self.process_btn.configure(state="normal")
            self.btn_svuota.configure(state="normal")
            self.btn_applica_tag.configure(state="normal")

    def _on_coda_completata(self, completati, saltati, errori):
        self._imposta_stato_elaborazione(False)
        self.progress_bar.set(1.0)

        # Reset form (il luogo è automatico da GPS, non serve reset manuale)
        self.tag_entry.delete("0.0", "end")
        self._inserisci_placeholder(None)
        self.drop_text.configure(
            text="Trascina qui o clicca per aggiungere",
            text_color=self.app.color_text_main
        )
        self.limits_text.configure(text="Più immagini o video (Max 200MB cad.)")

        # Svuota la coda (lascia le righe come storico, ma rimuovibili)
        self._svuota_coda()

        # Aggiorna statistiche home
        self.app.aggiorna_statistiche_storage()

        # Riepilogo
        msg = (f"Elaborazione coda completata!\n\n"
               f"✅ Completati: {completati}\n"
               f"⚠️ Già presenti (saltati): {saltati}\n"
               f"❌ Errori: {errori}")
        messagebox.showinfo("✅ Coda Elaborata", msg)
