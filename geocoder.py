"""
Servicio de georreferenciacion para GeoZonas.

Combina tres capas:
  1. Normalizador de direcciones colombianas (normalizador.py)
  2. Tabla DANE local en Supabase (gz_dane) para codigos DIVIPOLA
  3. Nominatim self-hosted para direcciones exactas -> lat/lon

La URL de Nominatim se configura por variable de entorno NOMINATIM_URL.
En desarrollo apunta a http://localhost:8080; en produccion a tu servidor.
"""

import os
import requests as http_requests
from normalizador import normalizar_direccion, es_codigo_dane

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://localhost:8080")
NOMINATIM_TIMEOUT = 10


def geocodificar_por_dane(codigo, supabase):
    """
    Busca un codigo DANE en la tabla gz_dane y devuelve sus coordenadas.
    Precision a nivel municipio o centro poblado.
    """
    res = supabase.table("gz_dane").select("*").eq("codigo_dane", codigo).execute()
    if not res.data:
        return None
    fila = res.data[0]
    return {
        "lat": fila.get("lat"),
        "lon": fila.get("lon"),
        "precision": "municipio",
        "fuente": "dane",
        "municipio": fila.get("municipio"),
        "departamento": fila.get("departamento"),
        "codigo_dane": codigo,
    }


def geocodificar_por_direccion(direccion, ciudad=None):
    """
    Normaliza una direccion y la geocodifica con Nominatim self-hosted.
    Precision a nivel de direccion exacta.
    """
    norm = normalizar_direccion(direccion, ciudad=ciudad)
    query = norm["query_geocoder"]

    try:
        resp = http_requests.get(
            NOMINATIM_URL.rstrip("/") + "/search",
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "co",
                "addressdetails": 1,
            },
            headers={"User-Agent": "GeoZonas/1.0 (geocoding service)"},
            timeout=NOMINATIM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {
            "lat": None,
            "lon": None,
            "precision": "error",
            "fuente": "nominatim",
            "error": str(e),
            "normalizada": norm["normalizada"],
        }

    if not data:
        return {
            "lat": None,
            "lon": None,
            "precision": "no_encontrado",
            "fuente": "nominatim",
            "normalizada": norm["normalizada"],
        }

    r = data[0]
    return {
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "precision": "exacto",
        "fuente": "nominatim",
        "normalizada": norm["normalizada"],
        "display_name": r.get("display_name"),
        "via_principal": norm["via_principal"],
    }


def geocodificar(entrada, ciudad=None, supabase=None):
    """
    Punto de entrada unico. Detecta automaticamente si la entrada es
    un codigo DANE o una direccion y enruta a la capa correcta.
    """
    if not entrada or not str(entrada).strip():
        return {"lat": None, "lon": None, "precision": "vacio", "fuente": None}

    entrada = str(entrada).strip()

    if es_codigo_dane(entrada):
        if supabase is None:
            return {
                "lat": None, "lon": None,
                "precision": "error",
                "fuente": "dane",
                "error": "supabase requerido para lookup DANE",
            }
        resultado = geocodificar_por_dane(entrada, supabase)
        if resultado is None:
            return {
                "lat": None, "lon": None,
                "precision": "no_encontrado",
                "fuente": "dane",
                "codigo_dane": entrada,
            }
        return resultado

    return geocodificar_por_direccion(entrada, ciudad=ciudad)
