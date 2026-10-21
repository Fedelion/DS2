"""
DeepSight - Applicazione Principale (Home Dashboard)
Entry point dell'applicazione customtkinter.
Include:
  - Navbar con navigazione Upload / Home / Ricerca
  - Dashboard home con grafici matplotlib reali
  - Statistiche storage live
"""

import os
import sys
import customtkinter as ctk
from PIL import Image

# Permette import dalla radice del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import Config_Start.config as config

# Importa i frame dalle altre pagine
try:
    from upload  import UploadFrame
    from ricerca import RicercaFrame
except ImportError:
    class UploadFrame(ctk.CTkFrame):
        def __init__(self, master, app=None):
            super().__init__(master, fg_color="transparent")
            self.app = app
            ctk.CTkLabel(self, text="[ Schermata Upload - Placeholder ]", font=("Inter", 18)).pack(expand=True)

    class RicercaFrame(ctk.CTkFrame):
        def __init__(self, master, app=None):
            super().__init__(master, fg_color="transparent")
            self.app = app
            ctk.CTkLabel(self, text="[ Schermata Ricerca - Placeholder ]", font=("Inter", 18)).pack(expand=True)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

try:
    from tkinterdnd2 import TkinterDnD
    class DeepSightAppBase(ctk.CTk, TkinterDnD.DnDWrapper):
        pass
    HAS_DND = True
except ImportError:
    class DeepSightAppBase(ctk.CTk):
        pass
    HAS_DND = False


class DeepSightApp(DeepSightAppBase):
    """
    Classe principale dell'applicazione DeepSight.
    Gestisce la finestra base, il tema, i colori, l'inizializzazione della barra di navigazione
    (Navbar) e funge da controller centrale per passare da una schermata all'altra
    (Home, Upload, Ricerca).
    """
    def __init__(self):
        super().__init__()


        
        if HAS_DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                print(f"[DeepSight] TkinterDnD inizializzato. Versione: {self.TkdndVersion}")
            except Exception as e:
                print(f"[DeepSight] Avviso: errore inizializzazione TkinterDnD: {e}")

        # ── Design System ─────────────────────────────────────────────
        self.color_bg         = "#0F172A"
        self.color_navbar     = "#1E293B"
        self.color_card       = "#1E293B"
        self.color_accent     = "#38BDF8"
        self.color_text_main  = "#F8FAFC"
        self.color_text_sec   = "#94A3B8"
        self.color_border     = "#334155"
        self.color_chart_bg   = "#1E293B"  # sfondo matplotlib

        # ── Config Finestra ───────────────────────────────────────────
        self.title("DeepSight — Multimedia Intelligence System")
        self.BASE_WIDTH  = 1200
        self.BASE_HEIGHT = 720
        self.geometry(f"{self.BASE_WIDTH}x{self.BASE_HEIGHT}+250+130")
        self.configure(fg_color=self.color_bg)

        # ── Font Responsive ───────────────────────────────────────────
        # Ogni font creato con self._font(...) viene registrato qui insieme
        # alla sua dimensione base, così da poterlo riscalare in base alla
        # dimensione corrente della finestra rispetto a quella di partenza.
        self._responsive_fonts = []
        self._responsive_images = []  # (ctk_image, label, larghezza_base, altezza_base)
        self._resize_job = None
        self._resize_layout_job = None
        self.current_breakpoint = "desktop"
        self.current_page_name = "home"
        self._last_width = 0
        self.bind("<Configure>", self._on_resize_root)

        # ── Path (usa config centralizzato) ───────────────────────────
        self.ROOT_DIR         = config.BASE_DIR
        self.BASE_UPLOAD_DIR  = config.UPLOAD_DIR
        self.IMG_DIR          = config.IMG_DIR
        self.VIDEO_DIR        = config.VIDEO_DIR
        self.DOCS_DIR         = config.DOCS_DIR
        self.TOTAL_STORAGE_GB = config.TOTAL_STORAGE_GB
        self.ESTENSIONI_IMMAGINI = config.ESTENSIONI_IMMAGINI
        self.ESTENSIONI_VIDEO    = config.ESTENSIONI_VIDEO

        # ── Variabili di Stato ────────────────────────────────────────
        self.filtro_tipo = ctk.StringVar(value="Tutto")

        # ── Navbar ────────────────────────────────────────────────────
        self.navbar = ctk.CTkFrame(self, height=70, fg_color=self.color_navbar, corner_radius=0)
        self.navbar.pack(fill="x", side="top", pady=0)
        self.navbar.pack_propagate(False)

        ctk.CTkFrame(self, height=1, fg_color=self.color_border, corner_radius=0).pack(fill="x")

        navbar_center = ctk.CTkFrame(self.navbar, fg_color="transparent")
        navbar_center.pack(expand=True, pady=10)

        self.nav_btn_upload = ctk.CTkButton(
            navbar_center, text="Upload", font=self._font(14, "bold"),
            text_color=self.color_text_sec, fg_color="transparent", hover=False,
            width=90, command=lambda: self.mostra_pagina("upload")
        )
        self.nav_btn_upload.pack(side="left", padx=20, anchor="center")

        # Logo
        logo_path = os.path.join(self.DOCS_DIR, "logo.png")
        try:
            pil_img = Image.open(logo_path)
            w, h = pil_img.size
            nh = 50; nw = int((nh / h) * w)
            self.logo_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(nw, nh))
            btn_logo = ctk.CTkButton(
                navbar_center, image=self.logo_ctk, text="",
                fg_color="transparent", hover=False, width=nw,
                command=lambda: self.mostra_pagina("home")
            )
        except Exception:
            btn_logo = ctk.CTkButton(
                navbar_center, text="DEEPSIGHT 👁", font=self._font(17, "bold"),
                text_color=self.color_text_main, fg_color="transparent", hover=False,
                command=lambda: self.mostra_pagina("home")
            )
        btn_logo.pack(side="left", padx=10, anchor="center")

        self.nav_btn_ricerca = ctk.CTkButton(
            navbar_center, text="Ricerca", font=self._font(14, "bold"),
            text_color=self.color_text_sec, fg_color="transparent", hover=False,
            width=90, command=lambda: self.mostra_pagina("ricerca")
        )
        self.nav_btn_ricerca.pack(side="left", padx=20, anchor="center")

        # ── Contenitore Pagine ────────────────────────────────────────
        self.container_pagine = ctk.CTkFrame(self, fg_color="transparent")
        self.container_pagine.pack(fill="both", expand=True)

        # Crea i frame
        self.crea_pagina_home()
        self.frame_upload = UploadFrame(self.container_pagine, self)
        self.frame_ricerca = RicercaFrame(self.container_pagine, self)

        self.aggiorna_statistiche_storage()
        self.mostra_pagina("home")

    def trigger_re_layout(self):
        if not self.winfo_exists(): return
        w = self.winfo_width()
        is_mobile = w < 950
        if self.current_page_name == "home":
            if hasattr(self, "re_layout_home"):
                self.re_layout_home(is_mobile, w)
        elif self.current_page_name == "upload":
            if hasattr(self.frame_upload, "re_layout"):
                self.frame_upload.re_layout(is_mobile, w)
        elif self.current_page_name == "ricerca":
            if hasattr(self.frame_ricerca, "re_layout"):
                self.frame_ricerca.re_layout(is_mobile, w)

    # ═══════════════════════════════════════════════════════════════════
    #  FONT RESPONSIVE
    # ═══════════════════════════════════════════════════════════════════
    def _font(self, size, weight="normal", family="Inter"):
        """
        Crea un CTkFont "tracciato": viene salvato insieme alla sua dimensione
        base in self._responsive_fonts, in modo che _applica_scala_font possa
        ridimensionarlo automaticamente quando la finestra cambia dimensione.
        """
        font_obj = ctk.CTkFont(family=family, size=size, weight=weight)
        self._responsive_fonts.append((font_obj, size))
        return font_obj

    def _on_resize_root(self, event):
        """
        Intercetta il ridimensionamento della finestra principale.
        Usa un debounce (self.after) per non ricalcolare i font ad ogni
        singolo pixel durante il trascinamento, ma solo quando l'utente
        si ferma per un istante.
        """
        if event.widget is not self:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        larghezza, altezza = event.width, event.height
        
        def _do_resize():
            self._applica_scala_font(larghezza, altezza)
            new_breakpoint = "mobile" if larghezza < 950 else "desktop"
            if new_breakpoint != self.current_breakpoint or self._last_width != larghezza:
                self.current_breakpoint = new_breakpoint
                self._last_width = larghezza
                self.trigger_re_layout()
                
        self._resize_job = self.after(120, _do_resize)

    def _applica_scala_font(self, larghezza, altezza):
        """
        Calcola un fattore di scala confrontando la dimensione attuale della
        finestra con quella base (1200x720), poi lo applica a tutti i font
        registrati tramite self._font(...). Il fattore è limitato (clamp) tra
        0.85 e 1.4 per evitare testo illeggibile o esageratamente grande.
        """
        scala_w = larghezza / self.BASE_WIDTH
        scala_h = altezza / self.BASE_HEIGHT
        scala = min(scala_w, scala_h)
        scala = max(0.85, min(scala, 1.4))

        for font_obj, dimensione_base in self._responsive_fonts:
            nuova_dimensione = max(8, round(dimensione_base * scala))
            font_obj.configure(size=nuova_dimensione)



        # Le icone scalano con la finestra (non con l'altezza istantanea della
        # card, che può variare in modo poco prevedibile): a dimensione base
        # (1200x720) restano esattamente alla loro dimensione originale.
        for img_obj, lbl_obj, larghezza_base, altezza_base in self._responsive_images:
            nuova_larghezza = max(60, round(larghezza_base * scala))
            nuova_altezza   = max(45, round(altezza_base * scala))
            img_obj.configure(size=(nuova_larghezza, nuova_altezza))
            lbl_obj.configure(width=nuova_larghezza, height=nuova_altezza)

        # Aggiorna il riferimento alla larghezza icona corrente, usato dai
        # gestori del wraplength delle descrizioni (vedi crea_pagina_home)
        if hasattr(self, "img_card_upload"):
            self._icon_w_up = round(150 * scala)
        if hasattr(self, "img_card_search"):
            self._icon_w_sh = round(150 * scala)

    # ═══════════════════════════════════════════════════════════════════
    #  NAVIGAZIONE
    # ═══════════════════════════════════════════════════════════════════
    def mostra_pagina(self, nome_pagina):
        """
        Nasconde tutte le schermate attuali e mostra solo la schermata specificata.
        Aggiorna anche il colore del testo dei pulsanti nella navbar per indicare la pagina attiva.
        
        Args:
            nome_pagina (str): 'home', 'upload' o 'ricerca'
        """
        if hasattr(self, 'frame_home'):
            self.frame_home.pack_forget()
        self.frame_upload.pack_forget()
        self.frame_ricerca.pack_forget()

        self.nav_btn_upload.configure(text_color=self.color_text_sec)
        self.nav_btn_ricerca.configure(text_color=self.color_text_sec)

        if nome_pagina == "home":
            self.aggiorna_statistiche_storage()
            self.aggiorna_ultime_immagini()
            self.frame_home.pack(fill="both", expand=True, padx=30, pady=20)
        elif nome_pagina == "upload":
            self.frame_upload.pack(fill="both", expand=True, padx=40, pady=25)
            self.nav_btn_upload.configure(text_color=self.color_accent)
        elif nome_pagina == "ricerca":
            self.frame_ricerca.pack(fill="both", expand=True, padx=40, pady=25)
            self.nav_btn_ricerca.configure(text_color=self.color_accent)
            
        self.current_page_name = nome_pagina
        self.after(50, self.trigger_re_layout)

    # ═══════════════════════════════════════════════════════════════════
    #  PAGINA HOME
    # ═══════════════════════════════════════════════════════════════════
    def crea_pagina_home(self):
        """
        Costruisce l'interfaccia della pagina principale (Dashboard).
        """
        self.frame_home = ctk.CTkFrame(self.container_pagine, fg_color="transparent")

        # Configurazione righe e colonne della griglia principale
        self.frame_home.grid_columnconfigure((0, 1), weight=4, uniform="home_cols")
        self.frame_home.grid_columnconfigure(2, weight=3, uniform="home_cols")
        
        # Aggiustiamo i 'cuscinetti' per togliere lo spazio vuoto
        self.frame_home.grid_rowconfigure(0, weight=0) # Spacer Top
        self.frame_home.grid_rowconfigure(1, weight=1) # Contenuto alto (Cards accesso rapido)
        self.frame_home.grid_rowconfigure(2, weight=4) # Contenuto basso (Ultime Immagini + Sidebar)
        self.frame_home.grid_rowconfigure(3, weight=0) # Spacer Bottom

        # ── Riga Superiore: Cards accesso rapido ──────────────────────
        self.frame_top = ctk.CTkFrame(self.frame_home, fg_color="transparent")
        self.frame_top.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 15))
        self.frame_top.grid_columnconfigure((0, 2), weight=5, uniform="top_btns")
        self.frame_top.grid_columnconfigure(1, weight=4, uniform="top_btns")
        self.frame_top.grid_rowconfigure(0, weight=1)

        img_upload_path = os.path.join(self.DOCS_DIR, "upload1.png")
        img_ricerca_path = os.path.join(self.DOCS_DIR, "ricerca1.png")
        IMG_W, IMG_H = 150, 120

        # CARD Upload
        self.card_upload = ctk.CTkFrame(
            self.frame_top, fg_color=self.color_card,
            border_color=self.color_border, border_width=1,
            corner_radius=16, cursor="hand2"
        )
        self.card_upload.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)
        self.card_upload.grid_columnconfigure(0, weight=0)
        self.card_upload.grid_columnconfigure(1, weight=1)
        self.card_upload.grid_rowconfigure(0, weight=1)

        try:
            pil_up = Image.open(img_upload_path).resize((IMG_W, IMG_H), Image.LANCZOS)
            pil_up = self.immagine(pil_up)
            self.img_card_upload = ctk.CTkImage(light_image=pil_up, dark_image=pil_up, size=(IMG_W, IMG_H))
            
            lbl_icon_up = ctk.CTkLabel(self.card_upload, image=self.img_card_upload, text="")
            lbl_icon_up.grid(row=0, column=0, sticky="nsew", padx=(20, 10))
            self._responsive_images.append((self.img_card_upload, lbl_icon_up, IMG_W, IMG_H))
        except Exception:
            lbl_icon_up = ctk.CTkLabel(self.card_upload, text="🖼️⚡", font=self._font(30, family="Arial"))
            lbl_icon_up.grid(row=0, column=0, padx=(20, 15))

        lbl_desc_up = ctk.CTkLabel(
            self.card_upload,
            text="Carica immagini o video, il sistema le catalogherà in automatico in base al contenuto visivo.",
            font=self._font(16), text_color=self.color_text_sec, justify="left"
        )
        lbl_desc_up.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        lbl_arrow_up = ctk.CTkLabel(self.card_upload, text="➔", font=self._font(16, "bold"), text_color=self.color_accent)
        lbl_arrow_up.grid(row=0, column=2, sticky="e", padx=15)
        self.card_upload.grid_columnconfigure(2, weight=0)

        def _adatta_wrap_up(event):
            larghezza_icona = getattr(self, "_icon_w_up", IMG_W)
            nuova_larghezza = event.width - larghezza_icona - 100
            if nuova_larghezza > 40:
                lbl_desc_up.configure(wraplength=nuova_larghezza)
        self.card_upload.bind("<Configure>", _adatta_wrap_up)

        for w in (self.card_upload, lbl_icon_up, lbl_desc_up, lbl_arrow_up):
            w.bind("<Button-1>", lambda e: self.mostra_pagina("upload"))

        # Centro: Titolo
        self.frame_titoli = ctk.CTkFrame(self.frame_top, fg_color="transparent")
        self.frame_titoli.grid(row=0, column=1, sticky="nsew")
        
        container_titoli = ctk.CTkFrame(self.frame_titoli, fg_color="transparent")
        container_titoli.pack(expand=True)
        
        ctk.CTkLabel(
            container_titoli, text="DeepSight",
            font=self._font(32, "bold"), text_color=self.color_text_main
        ).pack()
        ctk.CTkLabel(
            container_titoli, text="Analisi e catalogazione multimediale intelligente",
            font=self._font(12), text_color=self.color_text_sec
        ).pack(pady=2)

        # CARD Ricerca
        self.card_search = ctk.CTkFrame(
            self.frame_top, fg_color=self.color_card,
            border_color=self.color_border, border_width=1,
            corner_radius=16, cursor="hand2"
        )
        self.card_search.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=5)
        self.card_search.grid_columnconfigure(0, weight=0)
        self.card_search.grid_columnconfigure(1, weight=1)
        self.card_search.grid_rowconfigure(0, weight=1)

        try:
            pil_sh = Image.open(img_ricerca_path).resize((IMG_W, IMG_H), Image.LANCZOS)
            pil_sh = self.immagine(pil_sh)
            self.img_card_search = ctk.CTkImage(light_image=pil_sh, dark_image=pil_sh, size=(IMG_W, IMG_H))
            
            lbl_icon_sh = ctk.CTkLabel(self.card_search, image=self.img_card_search, text="")
            lbl_icon_sh.grid(row=0, column=0, sticky="nsew", padx=(20, 10))
            self._responsive_images.append((self.img_card_search, lbl_icon_sh, IMG_W, IMG_H))
        except Exception:
            lbl_icon_sh = ctk.CTkLabel(self.card_search, text="🔍⚡", font=self._font(30, family="Arial"))
            lbl_icon_sh.grid(row=0, column=0, padx=(20, 15))

        lbl_desc_sh = ctk.CTkLabel(
            self.card_search,
            text="Ricerca avanzata di immagini e video in base a parole chiave, luogo e/o data, ottimizzata dall'AI.",
            font=self._font(16), text_color=self.color_text_sec, justify="left"
        )
        lbl_desc_sh.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        lbl_arrow_sh = ctk.CTkLabel(self.card_search, text="➔", font=self._font(16, "bold"), text_color=self.color_accent)
        lbl_arrow_sh.grid(row=0, column=2, sticky="e", padx=15)
        self.card_search.grid_columnconfigure(2, weight=0)

        def _adatta_wrap_sh(event):
            larghezza_icona = getattr(self, "_icon_w_sh", IMG_W)
            nuova_larghezza = event.width - larghezza_icona - 100
            if nuova_larghezza > 40:
                lbl_desc_sh.configure(wraplength=nuova_larghezza)
        self.card_search.bind("<Configure>", _adatta_wrap_sh)

        for w in (self.card_search, lbl_icon_sh, lbl_desc_sh, lbl_arrow_sh):
            w.bind("<Button-1>", lambda e: self.mostra_pagina("ricerca"))

        # ── Riga Inferiore: Ultime Immagini + Sidebar ──────────────────
        self.card_ultime_immagini = ctk.CTkFrame(
            self.frame_home, fg_color=self.color_card,
            border_color=self.color_border, border_width=1, corner_radius=16
        )
        self.card_ultime_immagini.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(0, 10), pady=(10, 0))
        ctk.CTkLabel(
            self.card_ultime_immagini, text="Ultime Immagini Caricate",
            font=self._font(15, "bold"), text_color=self.color_text_main
        ).pack(anchor="w", padx=20, pady=(12, 4))
        self.frame_immagini = ctk.CTkScrollableFrame(self.card_ultime_immagini, fg_color="transparent", orientation="vertical")
        self.frame_immagini.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Sidebar Destra: Storage + Contatori
        self.sidebar = ctk.CTkFrame(self.frame_home, fg_color="transparent")
        self.sidebar.grid(row=2, column=2, sticky="nsew", padx=(10, 0), pady=(10, 0))
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(0, weight=4, uniform="side_rows")
        self.sidebar.grid_rowconfigure(1, weight=5, uniform="side_rows")

        # Card Storage
        self.card_storage = ctk.CTkFrame(
            self.sidebar, fg_color=self.color_card,
            border_color=self.color_border, border_width=1, corner_radius=16
        )
        self.card_storage.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.card_storage.grid_rowconfigure(0, weight=1)
        self.card_storage.grid_columnconfigure(0, weight=1)
        contenuto_storage = ctk.CTkFrame(self.card_storage, fg_color="transparent")
        contenuto_storage.grid(row=0, column=0, sticky="")

        ctk.CTkLabel(
            contenuto_storage, text="💾 Spazio Occupato",
            font=self._font(19, "bold"), text_color=self.color_text_main
        ).pack(anchor="center", pady=(10, 0))
        
        self.lbl_storage_info = ctk.CTkLabel(
            contenuto_storage, text="Calcolo in corso...",
            font=self._font(15), text_color=self.color_text_sec
        )
        self.lbl_storage_info.pack(anchor="center", pady=(5, 10))
        
        self.progress_storage = ctk.CTkProgressBar(
            contenuto_storage, width=220, height=12,
            progress_color=self.color_accent, fg_color="#334155"
        )
        self.progress_storage.pack(anchor="center", pady=(0, 15))
        self.progress_storage.set(0)

        # ── Contatori
        card_counters = ctk.CTkFrame(
            self.sidebar, fg_color=self.color_card,
            border_color=self.color_border, border_width=1, corner_radius=16
        )
        card_counters.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        card_counters.grid_rowconfigure((0,1,2), weight=1)
        card_counters.grid_columnconfigure(0, weight=1)
        
        content_img = ctk.CTkFrame(card_counters, fg_color="transparent")
        content_img.grid(row=0, column=0)
        ctk.CTkLabel(content_img, text="Immagini totali:", font=self._font(16, "bold"), text_color=self.color_text_main).pack(side="left", padx=(0, 10))
        self.lbl_count_img = ctk.CTkLabel(content_img, text="0", font=self._font(16), text_color=self.color_text_sec)
        self.lbl_count_img.pack(side="left")

        content_vid = ctk.CTkFrame(card_counters, fg_color="transparent")
        content_vid.grid(row=1, column=0)
        ctk.CTkLabel(content_vid, text="Video totali:", font=self._font(16, "bold"), text_color=self.color_text_main).pack(side="left", padx=(0, 10))
        self.lbl_count_vid = ctk.CTkLabel(content_vid, text="0", font=self._font(16), text_color=self.color_text_sec)
        self.lbl_count_vid.pack(side="left")

        content_db = ctk.CTkFrame(card_counters, fg_color="transparent")
        content_db.grid(row=2, column=0)
        ctk.CTkLabel(content_db, text="Dim. Database:", font=self._font(16, "bold"), text_color=self.color_text_main).pack(side="left", padx=(0, 10))
        self.lbl_count_db = ctk.CTkLabel(content_db, text="0", font=self._font(16), text_color=self.color_text_sec)
        self.lbl_count_db.pack(side="left")

    def re_layout_home(self, is_mobile, width):
        """Riorganizza il layout della home in base alla larghezza."""
        if is_mobile:
            self.card_upload.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
            self.frame_titoli.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
            self.card_search.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
            self.frame_top.grid_columnconfigure((0, 1, 2), weight=0, uniform="")
            self.frame_top.grid_columnconfigure(0, weight=1)
            
            self.card_ultime_immagini.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=0, pady=(10, 0))
            self.sidebar.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=0, pady=(10, 0))
            self.frame_home.grid_columnconfigure((0, 1, 2), weight=0, uniform="")
            self.frame_home.grid_columnconfigure(0, weight=1)
        else:
            self.card_upload.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)
            self.frame_titoli.grid(row=0, column=1, sticky="nsew")
            self.card_search.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=5)
            self.frame_top.grid_columnconfigure((0, 2), weight=5, uniform="top_btns")
            self.frame_top.grid_columnconfigure(1, weight=4, uniform="top_btns")
            
            self.card_ultime_immagini.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(0, 10), pady=(10, 0))
            self.sidebar.grid(row=2, column=2, sticky="nsew", padx=(10, 0), pady=(10, 0))
            self.frame_home.grid_columnconfigure((0, 1), weight=4, uniform="home_cols")
            self.frame_home.grid_columnconfigure(2, weight=3, uniform="home_cols")
            
        # Ricalcola la griglia delle ultime immagini
        available_width = self.frame_immagini.winfo_width()
        if available_width < 10:
            available_width = width - (80 if is_mobile else 300)
            
        CARD_SIZE_APPROX = 220  # 180 (card) + paddings
        cols = max(1, available_width // CARD_SIZE_APPROX)
        if hasattr(self, '_last_img_cols') and self._last_img_cols == cols:
            return
            
        self._last_img_cols = cols
        for i in range(10): 
            self.frame_immagini.grid_columnconfigure(i, weight=0, uniform="")
        for i in range(cols): 
            self.frame_immagini.grid_columnconfigure(i, weight=1, uniform="col")
            
        valid_children = [c for c in self.frame_immagini.winfo_children() if isinstance(c, ctk.CTkFrame)]
        for idx, child in enumerate(valid_children):
            child.grid(row=idx // cols, column=idx % cols, padx=10, pady=10)

  # ═══════════════════════════════════════════════════════════════════
    #  UTILITÀ INTERFACCIA
    # ═══════════════════════════════════════════════════════════════════
    def immagine(self, pil_img):
        """
        Restituisce l'immagine originale in formato RGBA 
        """
        return pil_img.convert("RGBA")

    # ═══════════════════════════════════════════════════════════════════
    #  STATISTICHE STORAGE (filesystem)
    # ═══════════════════════════════════════════════════════════════════
    def get_dimensione_cartella_mb(self, cartella):
        """
        Calcola in megabyte la dimensione totale occupata dai file in una specifica cartella.
        Non è ricorsiva per le sottocartelle, analizza solo i file diretti.
        """
        totale = 0
        if os.path.exists(cartella):
            # scandir è molto più veloce ed efficiente di listdir per leggere i metadati (stat)
            for entry in os.scandir(cartella):
                if entry.is_file():
                    totale += entry.stat().st_size # Somma la dimensione in byte di ogni file
        return totale / (1024 * 1024) # Converte da byte a Megabyte

    def aggiorna_statistiche_storage(self):
        """
        Analizza le cartelle dei video e delle immagini per contare quanti file 
        sono presenti e calcolarne lo spazio totale occupato in GB. Aggiorna
        quindi le etichette di testo e la progress bar di spazio rimanente.
        """
        count_img = sum(
            1 for f in os.listdir(self.IMG_DIR)
            if f.lower().endswith(self.ESTENSIONI_IMMAGINI)
        ) if os.path.exists(self.IMG_DIR) else 0

        count_vid = sum(
            1 for f in os.listdir(self.VIDEO_DIR)
            if f.lower().endswith(self.ESTENSIONI_VIDEO)
        ) if os.path.exists(self.VIDEO_DIR) else 0

        self.lbl_count_img.configure(text=str(count_img))
        self.lbl_count_vid.configure(text=str(count_vid))

        size_img_mb = self.get_dimensione_cartella_mb(self.IMG_DIR)
        size_vid_mb = self.get_dimensione_cartella_mb(self.VIDEO_DIR)
        totale_gb   = (size_img_mb + size_vid_mb) / 1024.0

        percentuale = min(totale_gb / self.TOTAL_STORAGE_GB, 1.0)
        self.progress_storage.set(percentuale)
        self.lbl_storage_info.configure(text=f"{totale_gb:.4f} / {self.TOTAL_STORAGE_GB} GB")

        # Dimensione DB
        db_mb = self.get_dimensione_cartella_mb(config.DB_DIR)
        self.lbl_count_db.configure(text=f"{db_mb:.1f} MB")

    # ═══════════════════════════════════════════════════════════════════
    #  ULTIME IMMAGINI
    # ═══════════════════════════════════════════════════════════════════
    def aggiorna_ultime_immagini(self):
        """Carica le ultime immagini aggiunte alla cartella e le mostra."""
        try:
            for w in self.frame_immagini.winfo_children():
                w.destroy()

            if not os.path.exists(self.IMG_DIR):
                return

            # Ottieni i file
            files = [f for f in os.listdir(self.IMG_DIR) if f.lower().endswith(self.ESTENSIONI_IMMAGINI)]
            if not files:
                lbl = ctk.CTkLabel(
                    self.frame_immagini, 
                    text="Nessuna immagine caricata.", 
                    text_color=self.color_text_sec, 
                    font=self._font(12, "italic")
                )
                lbl.pack(expand=True)
                return

            # Ordina per data di modifica (dal più recente)
            files_completi = [os.path.join(self.IMG_DIR, f) for f in files]
            files_completi.sort(key=os.path.getmtime, reverse=True)
            ultimi_files = files_completi[:15] # Mostriamo fino a 15 immagini

            CARD_SIZE = 180
            from PIL import ImageOps, ImageDraw

            NUM_COLUMNS = 3
            for i in range(NUM_COLUMNS):
                self.frame_immagini.grid_columnconfigure(i, weight=1, uniform="col")

            for idx, img_path in enumerate(ultimi_files):
                try:
                    pil_img = Image.open(img_path)
                    # Forziamo tutte le immagini a dimensioni identiche tramite crop/resize
                    pil_img = ImageOps.fit(pil_img, (CARD_SIZE, CARD_SIZE), Image.LANCZOS)
                    pil_img = self.immagine(pil_img)
                    
                    # Applichiamo una maschera per smussare gli angoli dell'immagine stessa
                    radius = 15
                    mask = Image.new('L', pil_img.size, 0)
                    draw = ImageDraw.Draw(mask)
                    draw.rounded_rectangle((0, 0) + pil_img.size, radius=radius, fill=255)
                    pil_img.putalpha(mask)
                    
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(CARD_SIZE, CARD_SIZE))
                    
                    frame_singola = ctk.CTkFrame(
                        self.frame_immagini, 
                        fg_color=self.color_bg, 
                        border_color=self.color_border, 
                        border_width=1, 
                        corner_radius=12,
                        width=CARD_SIZE+20,
                        height=CARD_SIZE+60
                    )
                    frame_singola.pack_propagate(False)
                    
                    # Usa la proprietà di layout aggiornata o default a 3
                    cols = getattr(self, '_last_img_cols', 3)
                    row = idx // cols
                    col = idx % cols
                    frame_singola.grid(row=row, column=col, padx=10, pady=10)
                    
                    lbl_img = ctk.CTkLabel(frame_singola, image=ctk_img, text="")
                    lbl_img.pack(pady=(10, 5), padx=10)
                    
                    # Nome file sotto
                    nome_file = os.path.basename(img_path)
                    if len(nome_file) > 22:
                        nome_file = nome_file[:19] + "..."
                        
                    lbl_nome = ctk.CTkLabel(
                        frame_singola, 
                        text=nome_file, 
                        text_color=self.color_text_sec, 
                        font=self._font(11, "bold")
                    )
                    lbl_nome.pack(pady=(0, 10))
                except Exception as e:
                    print(f"Errore nel caricare {img_path}: {e}")

        except Exception as e:
            print(f"[HOME] Errore aggiornamento ultime immagini: {e}")

if __name__ == "__main__":
    app = DeepSightApp()
    app.mainloop()