#!/usr/bin/env python3
"""
alerta_v2
La Fabrica Del Software.
Aplicación unificada: analiza feeds RSS, genera alerts.geojson/alerts.csv y las muestra
en una UI moderna (ttkbootstrap cuando esté disponible). Los iconos son generados
dinámicamente (colores) para no requerir archivos adicionales.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any

import feedparser
import requests
import pandas as pd

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

# Intentar usar ttkbootstrap para interfaz moderna; si no está, caerá a ttk estándar.
try:
    import ttkbootstrap as tb
    from ttkbootstrap.constants import *
    TB_AVAILABLE = True
except Exception:
    TB_AVAILABLE = False

# -----------------------------
# CONFIG / FEEDS / KEYWORDS
# -----------------------------
FEEDS = [
    "https://feeds.reuters.com/reuters/worldNews",
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "http://rss.cnn.com/rss/edition_world.rss",
    "https://apnews.com/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/rss",
    "https://www.france24.com/en/rss",
    "https://www.dw.com/atom/rss-en-all",
    "https://www.hrw.org/rss.xml",
    "https://reliefweb.int/updates?format=rss",
    # Colombia
    "https://www.eltiempo.com/rss/colombia.xml",
    "https://www.elespectador.com/feed/",
    "https://www.semana.com/rss/",
    "https://caracol.com.co/rss/colombia/",
    "https://www.rcnradio.com/rss/colombia",
    "https://www.elcolombiano.com/rss",
    "https://www.lafm.com.co/rss.xml",
    "https://www.vanguardia.com/rss",
    "https://www.elheraldo.co/rss",
    "https://www.publimetro.co/rss/colombia",
]

KEYWORDS = [
    "conflict", "war", "attack", "strike", "explosion", "border",
    "tension", "military", "missile", "drone", "nuclear",
    "venezuela", "colombia", "usa", "russia", "ukraine", "middle east",
    "migration", "refugees", "displaced", "guerrilla", "eln", "farc",
    "narcotrafico", "tren de aragua", "gaitanistas", "epl",
    "terroristas", "cartel de los soles", "lanza del sur", "south spears"
]
KEYWORDS = [k.lower() for k in KEYWORDS]

SEVERITY_KEYWORDS = [
    "attack", "explosion", "killed", "strike", "war",
    "invasion", "massacre", "terrorist"
]

OUT_CSV = "alerts.csv"
OUT_GEOJSON = "alerts.geojson"
DUP_HASH_FILE = ".seen_unified_hashes"

GEO_LOCATIONS = {
    "venezuela": [-66.5897, 6.4238],
    "colombia": [-74.2973, 4.5709],
    "usa": [-98.5795, 39.8283],
    "russia": [105.3188, 61.5240],
    "ukraine": [31.1656, 48.3794],
    "china": [104.1954, 35.8617],
    "iran": [53.6880, 32.4279],
    "israel": [34.8516, 31.0461],
    "gaza": [34.3088, 31.3547],
    "mexico": [-102.5528, 23.6345],
    "ecuador": [-78.1834, -1.8312],
    "peru": [-75.0152, -9.19],
    "brazil": [-51.9253, -14.2350],
}


# -----------------------------
# LÓGICA DE PROCESAMIENTO
# -----------------------------
def hash_item(title: str, link: str) -> str:
    return hashlib.sha256((title + link).encode("utf-8")).hexdigest()


def matches_keywords(text: str, keywords: List[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def severity_from_text(text: str) -> int:
    t = text.lower()
    score = sum(2 for k in SEVERITY_KEYWORDS if k in t)
    return min(score, 10)


def geocode_place(place: str):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": "AlertApp"},
            timeout=6
        )
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return [float(data[0]["lon"]), float(data[0]["lat"])]
    except Exception:
        return None
    return None


def extract_coords_from_text(text: str):
    t = text.lower()
    for place, coords in GEO_LOCATIONS.items():
        if place in t:
            return coords
    # Buscar nombres propios capitalizados
    words = [w.strip(".,()\"'") for w in text.split() if w.istitle()]
    blacklist = {"Breaking", "Updated", "News", "World"}
    for w in words:
        if w in blacklist:
            continue
        c = geocode_place(w)
        if c:
            return c
    return [0.0, 0.0]


def load_seen_hashes():
    if not os.path.exists(DUP_HASH_FILE):
        return set()
    try:
        with open(DUP_HASH_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f}
    except Exception:
        return set()


def save_seen_hashes(hashes: set):
    try:
        with open(DUP_HASH_FILE, "w", encoding="utf-8") as f:
            f.writelines(h + "\n" for h in hashes)
    except Exception:
        pass


def poll_once() -> List[Dict[str, Any]]:
    new_alerts = []
    seen = load_seen_hashes()

    for feed in FEEDS:
        try:
            d = feedparser.parse(feed)
        except Exception:
            # No interrumpir toda la ejecución si un feed falla
            continue

        for entry in getattr(d, "entries", []):
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            content = f"{title}\n{summary}"

            if not matches_keywords(content, KEYWORDS):
                continue

            h = hash_item(title, link)
            if h in seen:
                continue

            seen.add(h)
            coords = extract_coords_from_text(content)
            lon, lat = coords[0], coords[1]
            sev = severity_from_text(content)

            new_alerts.append({
                "id_hash": h,
                "title": title,
                "summary": summary,
                "link": link,
                "severity": sev,
                "longitude": lon,
                "latitude": lat,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })

    save_seen_hashes(seen)
    return new_alerts


def append_to_csv(alerts: List[Dict[str, Any]]):
    if not alerts:
        return
    df = pd.DataFrame(alerts)
    if os.path.exists(OUT_CSV):
        try:
            df_old = pd.read_csv(OUT_CSV)
            df = pd.concat([df_old, df], ignore_index=True)
        except Exception:
            pass
    df.to_csv(OUT_CSV, index=False)


def append_to_geojson(alerts: List[Dict[str, Any]]):
    features = []
    for a in alerts:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a["longitude"], a["latitude"]]},
            "properties": {k: v for k, v in a.items() if k not in ("longitude", "latitude")},
        })
    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)


# -----------------------------
# UTIL: iconos dinámicos (cuadrados color)
# -----------------------------
def make_color_icon(root, color: str, size: int = 20) -> tk.PhotoImage:
    """
    Crea un ícono cuadrado simple coloreado usando PhotoImage.put().
    Esto evita traer archivos externos o depender de PIL.
    """
    img = tk.PhotoImage(width=size, height=size)
    # Rellenar todo
    img.put(("{" + " ".join([color]*size) + "} ") * size)
    return img


# -----------------------------
# UI: Aplicación moderna con ttkbootstrap cuando esté disponible
# -----------------------------
class AppUI:
    def __init__(self, root):
        self.root = root
        self.current_geojson_data = None

        if TB_AVAILABLE:
            # Estilo y tema por defecto
            style = tb.Style(theme="flatly")
            # Re-assign root to tb.Frame parent if needed (we use the given root)
        else:
            # Aplicar un título y tamaño mínimo
            root.option_add("*Font", "SegoeUI 10")

        root.title("APP UNIFICADA — Alertas RSS + Visor GeoJSON")
        root.geometry("1200x650")

        # Toolbar superior
        self.toolbar = ttk.Frame(root)
        self.toolbar.pack(fill="x", padx=10, pady=8)

        # Iconos (color style B — color full)
        self.icon_rss = make_color_icon(root, "#f39c12", size=20)     # naranja
        self.icon_folder = make_color_icon(root, "#f1c40f", size=20)  # amarillo
        self.icon_save = make_color_icon(root, "#3498db", size=20)    # azul
        self.icon_map = make_color_icon(root, "#e74c3c", size=20)     # rojo
        self.icon_link = make_color_icon(root, "#2ecc71", size=20)    # verde

        # Large buttons in toolbar
        btn_style = {}
        if TB_AVAILABLE:
            btn_style["bootstyle"] = "primary-outline"
        self.btn_rss = ttk.Button(self.toolbar, text="  Ejecutar RSS  ",
                                  image=self.icon_rss, compound="left",
                                  command=self.run_alert_process, **btn_style)
        self.btn_rss.pack(side="left", padx=6)

        self.btn_load = ttk.Button(self.toolbar, text="  Cargar GeoJSON  ",
                                   image=self.icon_folder, compound="left",
                                   command=self.load_alerts_geojson, **btn_style)
        self.btn_load.pack(side="left", padx=6)

        self.btn_save = ttk.Button(self.toolbar, text="  Guardar copia  ",
                                   image=self.icon_save, compound="left",
                                   command=self.save_geojson_timestamped, **btn_style)
        self.btn_save.pack(side="left", padx=6)

        # Spacer
        ttk.Label(self.toolbar, text="   ").pack(side="left", padx=6)

        # Search / filter by severity
        ttk.Label(self.toolbar, text="Filtrar severidad ≥").pack(side="left", padx=(6, 2))
        self.sev_var = tk.IntVar(value=0)
        self.sev_spin = ttk.Spinbox(self.toolbar, from_=0, to=10, width=3, textvariable=self.sev_var)
        self.sev_spin.pack(side="left", padx=(0, 10))

        ttk.Button(self.toolbar, text="Aplicar filtro",
                   command=self.apply_severity_filter).pack(side="left")

        # Treeview (tabla)
        columns = ("title", "map", "lat", "lon", "link", "severity", "time")
        self.tree = ttk.Treeview(root, columns=columns, show="headings")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree.heading("title", text="Título")
        self.tree.heading("map", text="Mapa")
        self.tree.heading("lat", text="Lat")
        self.tree.heading("lon", text="Lon")
        self.tree.heading("link", text="Link")
        self.tree.heading("severity", text="Sev")
        self.tree.heading("time", text="Scraped at")

        self.tree.column("title", width=400, anchor="w")
        self.tree.column("map", width=100, anchor="center")
        self.tree.column("lat", width=80, anchor="center")
        self.tree.column("lon", width=80, anchor="center")
        self.tree.column("link", width=300, anchor="w")
        self.tree.column("severity", width=50, anchor="center")
        self.tree.column("time", width=160, anchor="center")

        # Bind events
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_single_click)

        # Statusbar
        self.status = ttk.Label(root, text="Listo", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

    # -------------------------
    # Funciones primarias
    # -------------------------
    def set_status(self, text: str):
        try:
            self.status.config(text=text)
        except Exception:
            pass

    def run_alert_process(self):
        self.set_status("Revisando feeds...")
        self.root.update_idletasks()
        try:
            alerts = poll_once()
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al consultar feeds: {e}")
            self.set_status("Error en feeds")
            return

        if alerts:
            append_to_csv(alerts)
            append_to_geojson(alerts)
            self.set_status(f"{len(alerts)} alertas nuevas — archivo actualizado.")
            messagebox.showinfo("Completado", f"Se generaron {len(alerts)} alertas.\nSe actualizó {OUT_GEOJSON}")
            # Auto-cargar el geojson generado
            if os.path.exists(OUT_GEOJSON):
                try:
                    self.load_geojson(OUT_GEOJSON)
                except Exception:
                    pass
        else:
            self.set_status("No se encontraron nuevas alertas.")
            messagebox.showinfo("Sin novedades", "No se encontraron nuevas alertas.")

    def load_alerts_geojson(self):
        """
            Permite cargar cualquier archivo .geojson o .json desde el PC.
        """
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo GeoJSON",
            filetypes=[
                ("Archivos GeoJSON", "*.geojson"),
                ("Archivos JSON", "*.json"),
                ("Todos los archivos", "*.*")
            ]
        )

        # Usuario canceló
        if not filepath:
            return

        # Cargar archivo seleccionado
        self.load_geojson(filepath)



    def load_geojson(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error lectura", str(e))
            return

        self.current_geojson_data = data
        self.tree.delete(*self.tree.get_children())

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [None, None])
            # GeoJSON uses [lon, lat]
            lon, lat = coords[0] if len(coords) > 0 else None, coords[1] if len(coords) > 1 else None

            title = props.get("title", props.get("headline", props.get("name", "")))
            link = props.get("link", props.get("url", ""))
            sev = props.get("severity", "")

            self.tree.insert("", "end", values=(
                title,
                "[ Ver mapa ]",
                lat,
                lon,
                link,
                sev,
                props.get("scraped_at", "")
            ))

        self.set_status(f"Cargado: {os.path.basename(filepath)}")

    def save_geojson_timestamped(self):
        if not self.current_geojson_data:
            messagebox.showwarning("Sin datos", "Primero carga un archivo GeoJSON o ejecuta el análisis.")
            return
        folder = filedialog.askdirectory(title="Selecciona carpeta para guardar")
        if not folder:
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = f"alerts_{ts}.geojson"
        path = os.path.join(folder, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.current_geojson_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Guardado", f"Guardado: {name}")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    # -------------------------
    # Filtrado
    # -------------------------
    def apply_severity_filter(self):
        try:
            minsev = int(self.sev_var.get())
        except Exception:
            minsev = 0

        # Reload rows applying filter
        if not self.current_geojson_data:
            messagebox.showinfo("No hay datos", "Primero carga un GeoJSON")
            return
        self.tree.delete(*self.tree.get_children())
        for feature in self.current_geojson_data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [None, None])
            lon, lat = (coords[0] if len(coords) > 0 else None, coords[1] if len(coords) > 1 else None)
            title = props.get("title", "")
            link = props.get("link", "")
            sev = props.get("severity", 0)
            try:
                sev_val = int(sev)
            except Exception:
                try:
                    sev_val = int(float(sev))
                except Exception:
                    sev_val = 0
            if sev_val >= minsev:
                self.tree.insert("", "end", values=(title, "[ Ver mapa ]", lat, lon, link, sev, props.get("scraped_at", "")))
        self.set_status(f"Filtro aplicado: severidad ≥ {minsev}")

    # -------------------------
    # Events: abrir link / mapa
    # -------------------------
    def on_double_click(self, event):
        # Doble clic abre link
        item = self.tree.focus()
        if not item:
            return
        vals = self.tree.item(item, "values")
        if not vals or len(vals) < 5:
            return
        link = vals[4]
        if isinstance(link, str) and link.startswith("http"):
            webbrowser.open(link)

    def on_single_click(self, event):
        # Si se hace clic en la columna "map" (col #2), abrir maps
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row:
            return
        # columna map es la segunda => "#2"
        if col == "#2":
            vals = self.tree.item(row, "values")
            if not vals or len(vals) < 4:
                return
            lat, lon = vals[2], vals[3]
            # Si lat/lon están invertidos o None, manejar gracefully
            if lat and lon:
                try:
                    # Intentar formatear como float
                    _ = float(lat)
                    _ = float(lon)
                    webbrowser.open(f"https://maps.google.com/?q={lat},{lon}")
                except Exception:
                    messagebox.showwarning("Coordenadas inválidas", "El registro no contiene coordenadas válidas.")
            else:
                messagebox.showwarning("Sin coordenadas", "El registro no incluye coordenadas.")

# -----------------------------
# MAIN
# -----------------------------
def main():
    if TB_AVAILABLE:
        root = tb.Window(themename="flatly")
    else:
        root = tk.Tk()

    app = AppUI(root)
    # Mensaje si faltar librerías para UI moderna
    if not TB_AVAILABLE:
        # Mostrar un pequeño aviso no intrusivo en status
        app.set_status("ttkbootstrap no instalado — usando ttk estándar. Para mejor UI: pip install ttkbootstrap")
    root.mainloop()


if __name__ == "__main__":
    main()
