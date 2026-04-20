from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os
import uuid
import secrets

load_dotenv()

app = FastAPI(
    title="GeoZonas API",
    description="API para verificar zonas geograficas por coordenadas",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ADMIN_KEY = os.getenv("API_KEY")

# --- Modelos ---
class Zona(BaseModel):
    nombre: str
    coordenadas: list

class Punto(BaseModel):
    lat: float
    lon: float

class ClienteRegistro(BaseModel):
    nombre: str
    empresa: str
    email: str
    password: str

class ClienteLogin(BaseModel):
    email: str
    password: str

class ApiKeyCrear(BaseModel):
    nombre: str = "default"

# --- Utilidades ---
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

def generar_api_key():
    return "gz_" + secrets.token_hex(24)

def verificar_admin(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Admin API Key invalida")

def verificar_cliente_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API Key requerida")
    res = supabase.table("gz_api_keys").select("*, gz_clientes(*)").eq("api_key", x_api_key).eq("activa", True).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="API Key invalida o inactiva")
    cliente = res.data[0].get("gz_clientes", {})
    if not cliente.get("activo", False):
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    return res.data[0]

# --- Endpoints de ZONAS (admin) ---
@app.post("/zonas", tags=["Zonas - Admin"])
def crear_zona(zona: Zona, x_api_key: str = Header(None)):
    verificar_admin(x_api_key)
    res = supabase.table("zonas").insert({
        "nombre": zona.nombre,
        "coordenadas": zona.coordenadas
    }).execute()
    return res.data[0]

@app.get("/zonas", tags=["Zonas - Admin"])
def listar_zonas():
    res = supabase.table("zonas").select("*").execute()
    return res.data

@app.delete("/zonas/{id}", tags=["Zonas - Admin"])
def eliminar_zona(id: str, x_api_key: str = Header(None)):
    verificar_admin(x_api_key)
    supabase.table("zonas").delete().eq("id", id).execute()
    return {"mensaje": "Zona eliminada"}

# --- Endpoint de VERIFICACION (clientes) ---
@app.post("/zonas/verificar", tags=["Verificacion"])
def verificar_punto(punto: Punto, x_api_key: str = Header(None)):
    key_data = verificar_cliente_key(x_api_key)
    supabase.table("gz_consumo_log").insert({
        "api_key_id": key_data["id"],
        "endpoint": "/zonas/verificar"
    }).execute()
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

# --- Endpoints de REGISTRO/LOGIN (clientes) ---
@app.post("/auth/registro", tags=["Autenticacion"])
def registro_cliente(datos: ClienteRegistro):
    try:
        auth_res = supabase.auth.sign_up({
            "email": datos.email,
            "password": datos.password
        })
        user = auth_res.user
        if not user:
            raise HTTPException(status_code=400, detail="Error en el registro")
        cliente = supabase.table("gz_clientes").insert({
            "user_id": user.id,
            "nombre": datos.nombre,
            "empresa": datos.empresa
        }).execute()
        primera_key = generar_api_key()
        supabase.table("gz_api_keys").insert({
            "cliente_id": cliente.data[0]["id"],
            "api_key": primera_key,
            "nombre": "default"
        }).execute()
        return {
            "mensaje": "Registro exitoso",
            "cliente": cliente.data[0],
            "api_key": primera_key
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login", tags=["Autenticacion"])
def login_cliente(datos: ClienteLogin):
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email": datos.email,
            "password": datos.password
        })
        user = auth_res.user
        if not user:
            raise HTTPException(status_code=401, detail="Credenciales invalidas")
        cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
        if not cliente.data:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        keys = supabase.table("gz_api_keys").select("*").eq("cliente_id", cliente.data[0]["id"]).execute()
        return {
            "cliente": cliente.data[0],
            "api_keys": keys.data,
            "token": auth_res.session.access_token
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# --- Endpoints de API KEYS (clientes autenticados) ---
@app.post("/mis-keys", tags=["API Keys"])
def crear_api_key(datos: ApiKeyCrear, authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    keys_existentes = supabase.table("gz_api_keys").select("*").eq("cliente_id", cliente.data[0]["id"]).execute()
    if len(keys_existentes.data) >= 5:
        raise HTTPException(status_code=400, detail="Maximo 5 API Keys por cliente")
    nueva_key = generar_api_key()
    res = supabase.table("gz_api_keys").insert({
        "cliente_id": cliente.data[0]["id"],
        "api_key": nueva_key,
        "nombre": datos.nombre
    }).execute()
    return res.data[0]

@app.get("/mis-keys", tags=["API Keys"])
def listar_mis_keys(authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    keys = supabase.table("gz_api_keys").select("*").eq("cliente_id", cliente.data[0]["id"]).execute()
    return keys.data

@app.delete("/mis-keys/{id}", tags=["API Keys"])
def revocar_api_key(id: str, authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    supabase.table("gz_api_keys").delete().eq("id", id).eq("cliente_id", cliente.data[0]["id"]).execute()
    return {"mensaje": "API Key revocada"}

# --- Endpoint de CONSUMO (clientes) ---
@app.get("/mi-consumo", tags=["Consumo"])
def ver_consumo(authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    keys = supabase.table("gz_api_keys").select("id").eq("cliente_id", cliente.data[0]["id"]).execute()
    key_ids = [k["id"] for k in keys.data]
    if not key_ids:
        return {"total": 0, "detalle": []}
    logs = supabase.table("gz_consumo_log").select("*").in_("api_key_id", key_ids).execute()
    return {"total": len(logs.data), "detalle": logs.data}

# --- Endpoints ADMIN (gestion de clientes) ---
@app.get("/admin/clientes", tags=["Admin"])
def listar_clientes(x_api_key: str = Header(None)):
    verificar_admin(x_api_key)
    res = supabase.table("gz_clientes").select("*").execute()
    return res.data

@app.put("/admin/clientes/{id}/toggle", tags=["Admin"])
def toggle_cliente(id: str, x_api_key: str = Header(None)):
    verificar_admin(x_api_key)
    cliente = supabase.table("gz_clientes").select("*").eq("id", id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    nuevo_estado = not cliente.data[0]["activo"]
    supabase.table("gz_clientes").update({"activo": nuevo_estado}).eq("id", id).execute()
    return {"activo": nuevo_estado}

# --- Utilidad para obtener usuario de Supabase Auth ---
def obtener_usuario(authorization):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.replace("Bearer ", "")
    try:
        user_res = supabase.auth.get_user(token)
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalido")