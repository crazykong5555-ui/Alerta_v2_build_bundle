#!/usr/bin/env python3
"""
app_unificada_moderno.py
Aplicación unificada: analiza feeds RSS, genera alerts.geojson/alerts.csv y las muestra
en una UI moderna (ttkbootstrap cuando esté disponible). Los iconos son generados
dinámicamente (colores) para no requerir archivos adicionales.
"""

import os
import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import feedparser
import requests
import pandas as pd

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import re

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

@dataclass
class Location:
    """Ubicaci\u00f3n normalizada asociada a una alerta de inteligencia."""

    name: str
    type: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    department: Optional[str] = None
    municipality: Optional[str] = None
    continent: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: Optional[str] = None
    geohash: Optional[str] = None
    timezone: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Diccionario local: evita una consulta remota para los lugares frecuentes y
# conserva el contexto administrativo que no exist\u00eda en la versi\u00f3n anterior.
GEO_LOCATIONS = {
    "venezuela": {"name": "Venezuela", "type": "country", "country": "Venezuela", "continent": "South America", "longitude": -66.5897, "latitude": 6.4238, "precision": "country", "timezone": "America/Caracas"},
    "colombia": {"name": "Colombia", "type": "country", "country": "Colombia", "continent": "South America", "longitude": -74.2973, "latitude": 4.5709, "precision": "country", "timezone": "America/Bogota"},
    "bogot\u00e1": {"name": "Bogot\u00e1", "type": "city", "country": "Colombia", "region": "Bogot\u00e1 D.C.", "department": "Bogot\u00e1 D.C.", "municipality": "Bogot\u00e1", "continent": "South America", "longitude": -74.0721, "latitude": 4.7110, "precision": "city", "timezone": "America/Bogota"},
    "bogota": {"name": "Bogot\u00e1", "type": "city", "country": "Colombia", "region": "Bogot\u00e1 D.C.", "department": "Bogot\u00e1 D.C.", "municipality": "Bogot\u00e1", "continent": "South America", "longitude": -74.0721, "latitude": 4.7110, "precision": "city", "timezone": "America/Bogota"},
    "c\u00facuta": {"name": "C\u00facuta", "type": "city", "country": "Colombia", "region": "Norte de Santander", "department": "Norte de Santander", "municipality": "C\u00facuta", "continent": "South America", "longitude": -72.5078, "latitude": 7.8939, "precision": "city", "timezone": "America/Bogota"},
    "cucuta": {"name": "C\u00facuta", "type": "city", "country": "Colombia", "region": "Norte de Santander", "department": "Norte de Santander", "municipality": "C\u00facuta", "continent": "South America", "longitude": -72.5078, "latitude": 7.8939, "precision": "city", "timezone": "America/Bogota"},
    "usa": {"name": "United States", "type": "country", "country": "United States", "continent": "North America", "longitude": -98.5795, "latitude": 39.8283, "precision": "country"},
    "russia": {"name": "Russia", "type": "country", "country": "Russia", "continent": "Europe/Asia", "longitude": 105.3188, "latitude": 61.5240, "precision": "country"},
    "ukraine": {"name": "Ukraine", "type": "country", "country": "Ukraine", "continent": "Europe", "longitude": 31.1656, "latitude": 48.3794, "precision": "country"},
    "china": {"name": "China", "type": "country", "country": "China", "continent": "Asia", "longitude": 104.1954, "latitude": 35.8617, "precision": "country"},
    "iran": {"name": "Iran", "type": "country", "country": "Iran", "continent": "Asia", "longitude": 53.6880, "latitude": 32.4279, "precision": "country"},
    "israel": {"name": "Israel", "type": "country", "country": "Israel", "continent": "Asia", "longitude": 34.8516, "latitude": 31.0461, "precision": "country"},
    "gaza": {"name": "Gaza", "type": "region", "country": "Palestine", "continent": "Asia", "longitude": 34.3088, "latitude": 31.3547, "precision": "region"},
    "mexico": {"name": "Mexico", "type": "country", "country": "Mexico", "continent": "North America", "longitude": -102.5528, "latitude": 23.6345, "precision": "country"},
    "ecuador": {"name": "Ecuador", "type": "country", "country": "Ecuador", "continent": "South America", "longitude": -78.1834, "latitude": -1.8312, "precision": "country"},
    "peru": {"name": "Peru", "type": "country", "country": "Peru", "continent": "South America", "longitude": -75.0152, "latitude": -9.19, "precision": "country"},
    "brazil": {"name": "Brazil", "type": "country", "country": "Brazil", "continent": "South America", "longitude": -51.9253, "latitude": -14.2350, "precision": "country"},
}


# -----------------------------
# LÓGICA DE PROCESAMIENTO
# -----------------------------



def extract_place(text):
    """
    Intenta encontrar el lugar mencionado en la noticia.
    """
    # Lugares conocidos
    for place in GEO_LOCATIONS.keys():
        if place.lower() in text.lower():
            return place

    # Buscar entidades tipo:
    # "in Bogotá"
    # "near Cúcuta"
    # "at Medellín"
    patrones = [
        r"\bin\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)",
        r"\bat\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)",
        r"\bnear\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)",
    ]

    for patron in patrones:
        m = re.search(patron, text)
        if m:
            return m.group(1)

    # Buscar nombres propios consecutivos
    candidatos = re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})",
        text
    )

    blacklist = {
        "Breaking",
        "Reuters",
        "News",
        "World",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    }

    for c in candidatos:
        if c not in blacklist:
            return c

    return None


def hash_item(title: str, link: str) -> str:
    return hashlib.sha256((title + link).encode("utf-8")).hexdigest()


def matches_keywords(text: str, keywords: List[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def severity_from_text(text: str) -> int:
    t = text.lower()
    score = sum(2 for k in SEVERITY_KEYWORDS if k in t)
    return min(score, 10)


def geocode_place(place: str) -> Optional[Dict[str, Any]]:
    """Consulta Nominatim y devuelve su resultado completo, si existe."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": "AlertApp"},
            timeout=6
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
    except Exception:
        return None
    return None


def extract_location(text: str) -> Optional[Location]:
    """Extrae y geocodifica una ubicaci\u00f3n una sola vez por alerta."""
    place = extract_place(text)
    if not place:
        return None

    known_location = GEO_LOCATIONS.get(place.lower())
    if known_location:
        return Location(**known_location, source="Local Dictionary", confidence=1.0)

    result = geocode_place(place)
    if not result:
        # La entidad fue detectada en el texto, aunque no se pudiera geocodificar.
        return Location(name=place, source="Text extraction", confidence=0.5)

    address = result.get("address", {})
    location_type = result.get("type") or result.get("addresstype")
    region = address.get("state") or address.get("region") or address.get("province")
    country = address.get("country")
    return Location(
        name=result.get("name") or address.get(location_type) or place,
        type=location_type,
        country=country,
        region=region,
        # En Colombia, el campo estatal de OSM corresponde al departamento.
        department=region if country == "Colombia" else None,
        municipality=address.get("municipality") or address.get("city") or address.get("town"),
        latitude=float(result["lat"]),
        longitude=float(result["lon"]),
        precision=location_type,
        source="OpenStreetMap Nominatim",
        confidence=0.9,
    )


def extract_coords_from_text(text: str):
    """Compatibilidad para consumidores antiguos que solo requieren coordenadas."""
    location = extract_location(text)
    if location and location.longitude is not None and location.latitude is not None:
        return [location.longitude, location.latitude]

    return None

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
            location = extract_location(content)
            location_data = location.to_dict() if location else None
            # Se mantienen los campos planos para no romper los archivos y
            # consumidores existentes; ``location`` es la fuente can\u00f3nica.
            place = location.name if location else None
            lon = location.longitude if location else None
            lat = location.latitude if location else None

            sev = severity_from_text(content)

            new_alerts.append({
                "id_hash": h,
                "title": title,
                "summary": summary,
                "link": link,
                "place": place,
                "location": location_data,
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
    existing_features = []
    existing_hashes = set()

    if os.path.exists(OUT_GEOJSON):
        try:
            with open(OUT_GEOJSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_features = data.get("features", [])
            existing_hashes = {
                feature.get("properties", {}).get("id_hash")
                for feature in existing_features
            }
        except Exception:
            existing_features = []
            existing_hashes = set()

    features = list(existing_features)
    for a in alerts:
        if a.get("id_hash") in existing_hashes:
            continue

        lon = a.get("longitude")
        lat = a.get("latitude")
        geometry = None
        if lon is not None and lat is not None:
            geometry = {"type": "Point", "coordinates": [lon, lat]}

        features.append({
            "type": "Feature",
            "geometry": geometry,
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
            geom = feature.get("geometry") or {}
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
            geom = feature.get("geometry") or {}
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
                self.tree.insert("", "end", values=(
                    title,
                    "[ Ver mapa ]",
                    lat,
                    lon,
                    link,
                    sev,
                    props.get("scraped_at", "")
                ))
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
