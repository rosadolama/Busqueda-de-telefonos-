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
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from contact_scraper.models import ContactInfo
from contact_scraper.results_io import result_to_csv_row, write_csv
from contact_scraper.scraper import scrape
from contact_scraper.url_sources import read_urls_from_file

APP_TITLE = "Búsqueda de Teléfonos"

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


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1150x620")
        self.root.report_callback_exception = self._on_tk_error

        self.csv_path: Optional[str] = None
        self.results: List[ContactInfo] = []
        self.worker: Optional[threading.Thread] = None
        self.stop_requested = False
        self.event_queue: "queue.Queue" = queue.Queue()

        self._build_widgets()
        self.root.after(100, self._poll_queue)

    # -- UI construction -----------------------------------------------

    def _build_widgets(self) -> None:
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill="x", padx=8, pady=8)

        self.path_label = tk.Label(toolbar, text="Ningún archivo seleccionado", anchor="w", fg="#555")
        self.path_label.pack(side="left", fill="x", expand=True)

        tk.Button(toolbar, text="Seleccionar CSV...", command=self._choose_csv).pack(side="left", padx=4)
        self.start_button = tk.Button(toolbar, text="Buscar", command=self._start, state="disabled")
        self.start_button.pack(side="left", padx=4)
        self.stop_button = tk.Button(toolbar, text="Detener", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        self.save_button = tk.Button(toolbar, text="Guardar CSV...", command=self._save_csv, state="disabled")
        self.save_button.pack(side="left", padx=4)

        status_frame = tk.Frame(self.root)
        status_frame.pack(fill="x", padx=8)
        self.status_var = tk.StringVar(value="Selecciona un CSV con las URLs para empezar.")
        tk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(fill="x")

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=8, pady=(4, 8))

        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        columns = [key for key, _label, _width in _COLUMNS]
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        for key, label, width in _COLUMNS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
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
        self.tree.insert("", "end", values=values)

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
