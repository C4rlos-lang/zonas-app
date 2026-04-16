from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# --- Modelos ---
class Zona(BaseModel):
    nombre: str
    coordenadas: list

class Punto(BaseModel):
    lat: float
    lon: float

# --- Utilidad: punto en polígono (ray casting) ---
def punto_en_poligono(punto, poligono):
    lat, lon = punto
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if ((yi > lon) != (yj > lon)) and (lat < (xj - xi) * (lon - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro

# --- Endpoints ---
@app.post("/zonas")
def crear_zona(zona: Zona):
    res = supabase.table("zonas").insert({
        "nombre": zona.nombre,
        "coordenadas": zona.coordenadas
    }).execute()
    return res.data[0]

@app.get("/zonas")
def listar_zonas():
    res = supabase.table("zonas").select("*").execute()
    return res.data

@app.delete("/zonas/{id}")
def eliminar_zona(id: str):
    supabase.table("zonas").delete().eq("id", id).execute()
    return {"mensaje": "Zona eliminada"}

@app.post("/zonas/verificar")
def verificar_punto(punto: Punto):
    res = supabase.table("zonas").select("*").execute()
    zonas = res.data
    encontradas = []
    for zona in zonas:
        coords = zona["coordenadas"]
        if punto_en_poligono([punto.lat, punto.lon], coords):
            encontradas.append({"id": zona["id"], "nombre": zona["nombre"]})
    if not encontradas:
        return {"zona": None, "mensaje": "El punto no pertenece a ninguna zona"}
    return {"zona": encontradas[0]["nombre"], "todas": encontradas}