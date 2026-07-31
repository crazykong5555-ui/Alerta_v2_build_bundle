"""ai_geolocator.py
Geolocalizador de textos usando un modelo GeoBERT (o equivalente)
cargado desde models/geobert/. Si el modelo no está disponible o
faltan las dependencias, hace fallback automático a Nominatim y a
un diccionario local de países/ciudades.
"""

import os
from typing import Dict, Any, Optional

# Intentar cargar transformers / torch
try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    TRANSFORMERS_AVAILABLE = True
except Exception:
    TRANSFORMERS_AVAILABLE = False

import requests


# Diccionario de respaldo (lon, lat)
FALLBACK_LOCATIONS = {
    "venezuela": (-66.5897, 6.4238),
    "colombia": (-74.2973, 4.5709),
    "usa": (-98.5795, 39.8283),
    "united states": (-98.5795, 39.8283),
    "russia": (105.3188, 61.5240),
    "ukraine": (31.1656, 48.3794),
    "china": (104.1954, 35.8617),
    "iran": (53.6880, 32.4279),
    "israel": (34.8516, 31.0461),
    "gaza": (34.3088, 31.3547),
    "mexico": (-102.5528, 23.6345),
    "ecuador": (-78.1834, -1.8312),
    "peru": (-75.0152, -9.19),
    "brazil": (-51.9253, -14.2350),
    "argentina": (-63.6167, -38.4161),
    "chile": (-71.5430, -35.6751),
    "spain": (-3.7492, 40.4637),
    "france": (2.2137, 46.2276),
    "germany": (10.4515, 51.1657),
    "uk": (-3.4360, 55.3781),
    "united kingdom": (-3.4360, 55.3781),
    "india": (78.9629, 20.5937),
    "pakistan": (69.3451, 30.3753),
    "syria": (38.9968, 34.8021),
    "iraq": (43.6793, 33.2232),
    "lebanon": (35.8623, 33.8547),
    "turkey": (35.2433, 38.9637),
    "türkiye": (35.2433, 38.9637),
    "japan": (138.2529, 36.2048),
    "korea": (127.7669, 35.9078),
    "taiwan": (120.9605, 23.6978),
    "palestine": (35.2332, 31.9522),
    "egypt": (30.8025, 26.8206),
    "sudan": (30.2176, 12.8628),
    "ethiopia": (40.4897, 9.1450),
    "somalia": (46.1996, 5.1521),
    "libya": (17.2283, 26.3351),
    "nigeria": (8.6753, 9.0820),
    "south africa": (22.9375, -30.5595),
    "kenya": (37.9062, -0.0236),
    "panama": (-80.7821, 8.5379),
    "cuba": (-77.7812, 21.5218),
    "haiti": (-72.2852, 18.9712),
}


class GeoLocator:
    """
    Geolocalizador híbrido:
    1) Si hay transformers + modelo en disco -> usa GeoBERT.
    2) Si no -> intenta Nominatim.
    3) Si Nominatim falla -> usa el diccionario local.
    """

    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.mode = "fallback"

        if not TRANSFORMERS_AVAILABLE:
            return

        if not os.path.isdir(model_dir):
            return

        # Comprobar que existan pesos
        has_weights = any(
            f.endswith((".bin", ".safetensors")) for f in os.listdir(model_dir)
        ) if os.path.exists(model_dir) else False
        if not has_weights:
            return

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
            self.model = AutoModel.from_pretrained(model_dir)
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(self.device)
            self.model.eval()
            self.mode = "transformers"
        except Exception as e:
            print(f"[GeoLocator] No se pudo cargar el modelo: {e}")
            self.model = None
            self.tokenizer = None
            self.mode = "fallback"

    # ------------------
    # Predicción
    # ------------------
    def predict(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {
                "lon": 0.0, "lat": 0.0, "confidence": 0.0,
                "method": "none", "place": None,
            }

        # 1) Intentar con el modelo
        if self.mode == "transformers":
            try:
                return self._predict_transformers(text)
            except Exception as e:
                print(f"[GeoLocator] Error con transformers, usando fallback: {e}")

        # 2) Nominatim
        result = self._predict_nominatim(text)
        if result["confidence"] > 0:
            return result

        # 3) Diccionario local
        return self._predict_dict(text)

    def _predict_transformers(self, text: str) -> Dict[str, Any]:
        """
        Placeholder de inferencia. La cabeza de regresión real depende
        del modelo concreto (GeoBERT/GeoLM). Aquí mostramos cómo se
        haría con un modelo tipo BERT y una cabeza de regresión lat/lon.
        Si tu modelo no tiene esa cabeza, sobrescribe este método.
        """
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=128
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        # Promedio de embeddings como "firma" del texto
        emb = outputs.last_hidden_state.mean(dim=1).squeeze().cpu()

        # Heurística: si el modelo no tiene cabeza de regresión,
        # se reduce a buscar el lugar más cercano en el diccionario
        # comparando la similitud coseno contra un bag-of-words
        # simple. Aquí simplificamos al fallback por palabra clave.
        lon, lat, place = self._best_match(text.lower())
        return {
            "lon": lon, "lat": lat, "confidence": 0.6,
            "method": "transformers+keyword", "place": place,
        }

    def _predict_nominatim(self, text: str) -> Dict[str, Any]:
        try:
            # Tomar las primeras 5 palabras significativas
            words = [w.strip(".,()\"'") for w in text.split() if len(w) > 3]
            q = " ".join(words[:5])
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1},
                headers={"User-Agent": "AlertApp-GeoLocator/1.0"},
                timeout=6,
            )
            data = r.json()
            if isinstance(data, list) and data:
                return {
                    "lon": float(data[0]["lon"]),
                    "lat": float(data[0]["lat"]),
                    "confidence": 0.8,
                    "method": "nominatim",
                    "place": data[0].get("display_name"),
                }
        except Exception:
            pass
        return {"lon": 0.0, "lat": 0.0, "confidence": 0.0, "method": "nominatim", "place": None}

    def _predict_dict(self, text: str) -> Dict[str, Any]:
        lon, lat, place = self._best_match(text.lower())
        return {
            "lon": lon, "lat": lat, "confidence": 0.4,
            "method": "dictionary", "place": place,
        }

    def _best_match(self, text: str):
        for place, (lon, lat) in FALLBACK_LOCATIONS.items():
            if place in text:
                return lon, lat, place
        return 0.0, 0.0, None
