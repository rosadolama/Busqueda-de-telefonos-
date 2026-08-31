"""Desktop app: pick a CSV of URLs, scrape them, see results, export a CSV.

Packaged into a Windows .exe via PyInstaller (see .github/workflows). The
scrape itself runs on a background thread -- Tkinter is not thread-safe, so
the worker only ever *posts* to a queue.Queue and the main thread is the only
one that ever touches a widget, polling that queue via root.after().

Errors are always shown in a messagebox, never left to print to a console:
the packaged app is built with --windowed (no console window at all), so an
uncaught exception would otherwise vanish silently instead of telling the
user what went wrong.
"""
from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from contact_scraper.models import ContactInfo
from contact_scraper.results_io import result_to_csv_row, write_csv
from contact_scraper.scraper import scrape
from contact_scraper.url_sources import read_urls_from_file

APP_TITLE = "Búsqueda de Teléfonos"
APP_SUBTITLE = "Extracción de datos de contacto"

# A restrained navy/gray palette rather than anything colorful, and a native
# Windows UI font where it's available -- the two things that read as
# "corporate app" instead of "default Tk gray box".
_INK = "#132238"          # header background, primary text
_INK_LIGHT = "#24405f"    # header bottom border / hover
_ACCENT = "#2f6fb3"       # primary action (Buscar)
_ACCENT_HOVER = "#255a92"
_DANGER = "#b3492f"       # Detener, only meaningful once a batch is running
_DANGER_HOVER = "#92401f"
_BG = "#eef1f5"           # window background
_SURFACE = "#ffffff"      # panels, table
_BORDER = "#d3dae3"
_TEXT = "#1c2530"
_MUTED = "#6b7684"
_ROW_ALT = "#f4f7fb"      # zebra stripe

_COLUMNS = [
    ("source_url", "URL", 200),
    ("names", "Nombres", 160),
    ("phones", "Teléfonos", 140),
    ("hours", "Horario", 160),
    ("city", "Ciudad", 100),
    ("country", "País", 50),
    ("contact_page_url", "Página de contacto", 160),
    ("team_page_url", "Página de equipo", 160),
    ("warnings", "Avisos", 220),
]


def _pick_font(root: tk.Misc, *candidates: str) -> str:
    """First installed font from `candidates`, else Tk's own default."""
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x640")
        self.root.minsize(820, 460)
        self.root.configure(bg=_BG)
        self.root.report_callback_exception = self._on_tk_error

        self.csv_path: Optional[str] = None
        self.results: List[ContactInfo] = []
        self.worker: Optional[threading.Thread] = None
        self.stop_requested = False
        self.event_queue: "queue.Queue" = queue.Queue()

        self.font_family = _pick_font(root, "Segoe UI", "Helvetica Neue", "Helvetica", "Arial")
        self._setup_style()
        self._build_widgets()
        self.root.after(100, self._poll_queue)

    # -- look & feel ------------------------------------------------------

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        # "clam" is the theme ttk can actually recolor consistently; the
        # native Windows theme ignores most background/foreground overrides.
        style.theme_use("clam")

        base_font = (self.font_family, 10)
        style.configure(".", font=base_font, background=_BG, foreground=_TEXT)

        style.configure("Toolbar.TFrame", background=_SURFACE)
        style.configure("Header.TFrame", background=_INK)
        style.configure(
            "Header.TLabel", background=_INK, foreground="#ffffff",
            font=(self.font_family, 15, "bold"),
        )
        style.configure(
            "Subheader.TLabel", background=_INK, foreground="#b7c6da",
            font=(self.font_family, 9),
        )
        style.configure("Status.TFrame", background=_SURFACE)
        style.configure("Status.TLabel", background=_SURFACE, foreground=_MUTED, font=base_font)
        style.configure("Path.TLabel", background=_SURFACE, foreground=_MUTED, font=(self.font_family, 9))

        style.configure(
            "Primary.TButton", font=(self.font_family, 10, "bold"),
            background=_ACCENT, foreground="#ffffff", borderwidth=0, padding=(14, 7),
        )
        style.map("Primary.TButton",
                  background=[("disabled", "#a7bcd4"), ("active", _ACCENT_HOVER)],
                  foreground=[("disabled", "#eef1f5")])

        style.configure(
            "Secondary.TButton", font=base_font,
            background=_SURFACE, foreground=_TEXT, borderwidth=1, padding=(12, 6),
        )
        style.map("Secondary.TButton",
                  background=[("disabled", _SURFACE), ("active", _ROW_ALT)],
                  foreground=[("disabled", _MUTED)],
                  bordercolor=[("!disabled", _BORDER)])

        style.configure(
            "Danger.TButton", font=(self.font_family, 10, "bold"),
            background=_DANGER, foreground="#ffffff", borderwidth=0, padding=(12, 6),
        )
        style.map("Danger.TButton",
                  background=[("disabled", "#d9b8ae"), ("active", _DANGER_HOVER)],
                  foreground=[("disabled", "#f7ece9")])

        style.configure(
            "Corporate.Horizontal.TProgressbar",
            background=_ACCENT, troughcolor=_ROW_ALT, borderwidth=0, thickness=8,
        )

        style.configure(
            "Treeview", background=_SURFACE, fieldbackground=_SURFACE, foreground=_TEXT,
            rowheight=26, borderwidth=0,
        )
        style.configure(
            "Treeview.Heading", background=_INK, foreground="#ffffff",
            font=(self.font_family, 9, "bold"), relief="flat", padding=(6, 6),
        )
        style.map("Treeview.Heading", background=[("active", _INK_LIGHT)])
        style.map("Treeview", background=[("selected", _ACCENT)], foreground=[("selected", "#ffffff")])

    # -- UI construction -----------------------------------------------

    def _build_widgets(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        inner = ttk.Frame(header, style="Header.TFrame")
        inner.pack(fill="x", padx=18, pady=(14, 12))
        ttk.Label(inner, text=APP_TITLE, style="Header.TLabel").pack(anchor="w")
        ttk.Label(inner, text=APP_SUBTITLE, style="Subheader.TLabel").pack(anchor="w")

        body = tk.Frame(self.root, bg=_BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        toolbar = ttk.Frame(body, style="Toolbar.TFrame", padding=12)
        toolbar.pack(fill="x")

        row1 = ttk.Frame(toolbar, style="Toolbar.TFrame")
        row1.pack(fill="x")
        ttk.Button(row1, text="Seleccionar CSV...", style="Secondary.TButton", command=self._choose_csv).pack(side="left")
        self.start_button = ttk.Button(row1, text="Buscar", style="Primary.TButton", command=self._start, state="disabled")
        self.start_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(row1, text="Detener", style="Danger.TButton", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.save_button = ttk.Button(row1, text="Guardar CSV...", style="Secondary.TButton", command=self._save_csv, state="disabled")
        self.save_button.pack(side="left", padx=(8, 0))

        self.path_label = ttk.Label(toolbar, text="Ningún archivo seleccionado", style="Path.TLabel")
        self.path_label.pack(fill="x", anchor="w", pady=(10, 0))

        status_frame = ttk.Frame(body, style="Status.TFrame", padding=(12, 10))
        status_frame.pack(fill="x", pady=(10, 0))
        self.status_var = tk.StringVar(value="Selecciona un CSV con las URLs para empezar.")
        ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel").pack(fill="x", anchor="w")
        self.progress = ttk.Progressbar(status_frame, mode="determinate", style="Corporate.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(8, 0))

        tree_frame = tk.Frame(body, bg=_BORDER, highlightthickness=0)
        tree_frame.pack(fill="both", expand=True, pady=(12, 0))

        columns = [key for key, _label, _width in _COLUMNS]
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        for key, label, width in _COLUMNS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.tag_configure("odd", background=_ROW_ALT)
        self.tree.tag_configure("even", background=_SURFACE)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

    # -- button handlers --------------------------------------------------

    def _choose_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecciona un CSV con las URLs",
            filetypes=[("CSV", "*.csv"), ("Texto", "*.txt"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        self.csv_path = path
        self.path_label.config(text=path)
        self.start_button.config(state="normal")
        self.status_var.set("Listo para buscar.")

    def _start(self) -> None:
        if not self.csv_path or (self.worker and self.worker.is_alive()):
            return
        try:
            urls = read_urls_from_file(self.csv_path)
        except Exception as exc:
            messagebox.showerror("Error al leer el archivo", str(exc))
            return
        if not urls:
            messagebox.showwarning("Sin URLs", "No se encontró ninguna URL en el archivo seleccionado.")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        self.stop_requested = False
        self.progress.config(maximum=len(urls), value=0)
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.save_button.config(state="disabled")
        self.status_var.set(f"Procesando 0/{len(urls)}...")

        self.worker = threading.Thread(target=self._run_scrape, args=(urls,), daemon=True)
        self.worker.start()

    def _stop(self) -> None:
        self.stop_requested = True
        self.stop_button.config(state="disabled")
        self.status_var.set("Deteniendo... (termina el sitio actual y para)")

    def _save_csv(self) -> None:
        if not self.results:
            messagebox.showinfo("Sin resultados", "Todavía no hay resultados para guardar.")
            return
        path = filedialog.asksaveasfilename(
            title="Guardar resultados como CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            write_csv(self.results, path)
        except Exception as exc:
            messagebox.showerror("Error al guardar", str(exc))
            return
        messagebox.showinfo("Guardado", f"Resultados guardados en:\n{path}")

    # -- background worker -------------------------------------------------

    def _run_scrape(self, urls: List[str]) -> None:
        total = len(urls)
        for i, url in enumerate(urls, start=1):
            if self.stop_requested:
                break
            self.event_queue.put(("status", f"Procesando {i}/{total}: {url}"))
            try:
                info = scrape(url)
            except ValueError as exc:
                info = ContactInfo(source_url=url, warnings=[f"URL inválida: {exc}"])
            except Exception as exc:
                # A single unexpected failure must not kill the whole batch;
                # record it as a warning on that row and keep going.
                info = ContactInfo(source_url=url, warnings=[f"Error inesperado: {exc}"])
            self.event_queue.put(("result", info))
        self.event_queue.put(("done", None))

    # -- queue polling (main thread only) ----------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "result":
                    self.results.append(payload)
                    self.progress.config(value=len(self.results))
                    self._add_row(payload)
                elif kind == "done":
                    self._on_batch_done()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_batch_done(self) -> None:
        note = " (detenido)" if self.stop_requested else ""
        self.status_var.set(f"Listo{note}. {len(self.results)} sitio(s) procesados.")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.save_button.config(state="normal" if self.results else "disabled")

    def _add_row(self, info: ContactInfo) -> None:
        row = result_to_csv_row(info)
        values = [row[key] for key, _label, _width in _COLUMNS]
        tag = "odd" if len(self.tree.get_children()) % 2 else "even"
        self.tree.insert("", "end", values=values, tags=(tag,))

    # -- safety net ---------------------------------------------------------

    def _on_tk_error(self, exc_type, exc_value, exc_tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        messagebox.showerror("Error inesperado", detail[-2000:])


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
