"""geojson_processor.py
Procesa en lote archivos .geojson de un directorio:
- Lista estadísticas
- Enriquece features sin coordenadas usando el GeoLocator
- Fusiona varios archivos en uno solo
- Exporta CSV de resumen
"""

import os
import json
import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Importar el geolocalizador (mismo paquete)
try:
    from ai_geolocator import GeoLocator
    GEOLOCATOR_AVAILABLE = True
except Exception:
    GEOLOCATOR_AVAILABLE = False


class BatchProcessor:
    """Procesa archivos .geojson de un directorio."""

    def __init__(self, path: str, output_dir: Optional[str] = None):
        self.path = Path(path)
        self.output_dir = Path(output_dir) if output_dir else self.path
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.locator = None
        if GEOLOCATOR_AVAILABLE:
            # models/geobert relativo a este archivo: .../alerta_v2/models/geobert
            model_dir = Path(__file__).resolve().parent / "models" / "geobert"
            self.locator = GeoLocator(model_dir=str(model_dir))

    # ----------------------------------------------------------------
    # Listado y estadísticas
    # ----------------------------------------------------------------
    def list_stats(self) -> List[Dict[str, Any]]:
        """Devuelve estadísticas por archivo."""
        archivos = sorted(self.path.glob("*.geojson"))
        stats = []
        for archivo in archivos:
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                feats = data.get("features", []) if isinstance(data, dict) else []
                stats.append({
                    "file": archivo.name,
                    "features": len(feats),
                    "size_kb": round(archivo.stat().st_size / 1024, 1),
                })
            except Exception as e:
                stats.append({
                    "file": archivo.name, "features": 0, "error": str(e),
                })
        return stats

    def process(self):
        """Método principal: muestra stats en consola y genera resumen."""
        stats = self.list_stats()
        if not stats:
            print(f"No se encontraron archivos .geojson en {self.path}")
            return

        total = 0
        for s in stats:
            total += s.get("features", 0)
            if "error" in s:
                print(f"  ✗ {s['file']}: {s['error']}")
            else:
                print(f"  • {s['file']}: {s['features']} features ({s['size_kb']} KB)")
        print(f"\nTotal: {total} features en {len(stats)} archivos")

        # Guardar CSV resumen
        self._export_summary_csv(stats)

    # ----------------------------------------------------------------
    # Enriquecer con IA
    # ----------------------------------------------------------------
    def enrich(self, filename: str) -> str:
        """
        Enriquece un .geojson cuyas features no tengan coordenadas
        válidas, usando GeoLocator. Devuelve la ruta del archivo nuevo.
        """
        src = self.path / filename
        if not src.exists():
            raise FileNotFoundError(f"No existe {src}")

        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "features" not in data:
            raise ValueError("GeoJSON inválido")

        if self.locator is None:
            print("[WARN] GeoLocator no disponible, no se puede enriquecer.")
            return str(src)

        enriched = 0
        for feature in data["features"]:
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None]
            lon, lat = (coords[0], coords[1]) if len(coords) >= 2 else (None, None)
            if lon in (None, 0) and lat in (None, 0):
                props = feature.get("properties", {})
                text = " ".join(str(v) for v in props.values() if isinstance(v, str))
                if not text.strip():
                    continue
                result = self.locator.predict(text)
                if result["lon"] != 0 or result["lat"] != 0:
                    feature["geometry"] = {
                        "type": "Point",
                        "coordinates": [result["lon"], result["lat"]],
                    }
                    feature.setdefault("properties", {})["geolocate_method"] = result["method"]
                    enriched += 1

        out = self.output_dir / f"enriched_{filename}"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Enriquecidas: {enriched} features. Guardado en {out}")
        return str(out)

    # ----------------------------------------------------------------
    # Fusionar varios .geojson
    # ----------------------------------------------------------------
    def merge(self, output_name: str = "merged.geojson") -> str:
        archivos = sorted(self.path.glob("*.geojson"))
        if not archivos:
            raise FileNotFoundError("No hay .geojson para fusionar")

        all_features = []
        for archivo in archivos:
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "features" in data:
                    all_features.extend(data["features"])
            except Exception as e:
                print(f"[WARN] Saltando {archivo.name}: {e}")

        merged = {"type": "FeatureCollection", "features": all_features}
        out = self.output_dir / output_name
        with open(out, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"Fusionado: {len(all_features)} features -> {out}")
        return str(out)

    # ----------------------------------------------------------------
    # Exportar CSV resumen
    # ----------------------------------------------------------------
    def _export_summary_csv(self, stats: List[Dict[str, Any]]):
        out = self.output_dir / "summary.csv"
        keys = ["file", "features", "size_kb", "error"]
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for s in stats:
                w.writerow({k: s.get(k, "") for k in keys})
        print(f"Resumen CSV: {out}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    action = sys.argv[2] if len(sys.argv) > 2 else "stats"

    bp = BatchProcessor(target)
    if action == "stats":
        bp.process()
    elif action == "merge":
        bp.merge()
    elif action == "enrich":
        if len(sys.argv) < 4:
            print("Uso: python geojson_processor.py <directorio> enrich <archivo.geojson>")
        else:
            bp.enrich(sys.argv[3])
    else:
        print(f"Acción desconocida: {action}")
