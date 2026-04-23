from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os
import secrets
import requests as http_requests
import hashlib

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
WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY")
WOMPI_PRIVATE_KEY = os.getenv("WOMPI_PRIVATE_KEY")

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

class CrearTransaccion(BaseModel):
    plan: str

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
    if x_api_key == ADMIN_KEY:
        return {"id": "admin", "api_key": ADMIN_KEY, "es_admin": True}
    res = supabase.table("gz_api_keys").select("*, gz_clientes(*)").eq("api_key", x_api_key).eq("activa", True).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="API Key invalida o inactiva")
    cliente = res.data[0].get("gz_clientes", {})
    if not cliente.get("activo", False):
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    consultas = cliente.get("consultas_restantes", 0)
    if consultas <= 0 and cliente.get("plan", "starter") != "enterprise":
        raise HTTPException(status_code=429, detail="Limite de consultas alcanzado. Actualiza tu plan.")
    return res.data[0]

def obtener_usuario(authorization):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.replace("Bearer ", "")
    try:
        user_res = supabase.auth.get_user(token)
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalido")

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
    if not key_data.get("es_admin"):
        supabase.table("gz_consumo_log").insert({
            "api_key_id": key_data["id"],
            "endpoint": "/zonas/verificar"
        }).execute()
        cliente = key_data.get("gz_clientes", {})
        if cliente and cliente.get("plan", "starter") != "enterprise":
            nuevas = max(0, cliente.get("consultas_restantes", 0) - 1)
            supabase.table("gz_clientes").update({
                "consultas_restantes": nuevas
            }).eq("id", cliente["id"]).execute()
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
            "empresa": datos.empresa,
            "plan": "starter",
            "consultas_restantes": 1000
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
    plan = cliente.data[0].get("plan", "starter")
    plan_info = supabase.table("gz_planes").select("*").eq("nombre", plan).execute()
    max_keys = 1
    if plan_info.data:
        max_keys = plan_info.data[0].get("max_api_keys", 1)
    keys_existentes = supabase.table("gz_api_keys").select("*").eq("cliente_id", cliente.data[0]["id"]).execute()
    if len(keys_existentes.data) >= max_keys:
        raise HTTPException(status_code=400, detail="Maximo " + str(max_keys) + " API Keys en plan " + plan)
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

# --- Endpoint de MI PLAN (clientes) ---
@app.get("/mi-plan", tags=["Plan"])
def ver_plan(authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    c = cliente.data[0]
    plan_info = supabase.table("gz_planes").select("*").eq("nombre", c.get("plan", "starter")).execute()
    return {
        "plan": c.get("plan", "starter"),
        "consultas_restantes": c.get("consultas_restantes", 0),
        "consultas_mes": plan_info.data[0]["consultas_mes"] if plan_info.data else 1000,
        "max_api_keys": plan_info.data[0]["max_api_keys"] if plan_info.data else 1
    }

# --- Endpoints de PAGO con Wompi ---
@app.post("/pagos/crear", tags=["Pagos"])
def crear_pago(datos: CrearTransaccion, authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    plan = supabase.table("gz_planes").select("*").eq("nombre", datos.plan).execute()
    if not plan.data:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    if plan.data[0]["precio"] == 0:
        raise HTTPException(status_code=400, detail="Este plan es gratuito")
    precio_centavos = plan.data[0]["precio"] * 100
    referencia = "gz_" + secrets.token_hex(12)
    integrity_str = referencia + str(precio_centavos) + "COP" + os.getenv("WOMPI_INTEGRITY_SECRET", "")
    integrity_hash = hashlib.sha256(integrity_str.encode()).hexdigest()
    return {
        "public_key": WOMPI_PUBLIC_KEY,
        "monto": precio_centavos,
        "moneda": "COP",
        "referencia": referencia,
        "integrity": integrity_hash,
        "plan": datos.plan,
        "cliente_id": cliente.data[0]["id"],
        "redirect_url": "https://zonas-frontend.vercel.app/#/portal/dashboard"
    }

@app.post("/pagos/webhook", tags=["Pagos"])
async def webhook_wompi(request: Request):
    body = await request.json()
    try:
        evento = body.get("event", "")
        data = body.get("data", {}).get("transaction", {})
        referencia = data.get("reference", "")
        estado = data.get("status", "")
        if evento == "transaction.updated" and estado == "APPROVED":
            if referencia.startswith("gz_"):
                meta = data.get("metadata", {})
                cliente_id = meta.get("cliente_id", "")
                plan_nombre = meta.get("plan", "")
                if cliente_id and plan_nombre:
                    plan = supabase.table("gz_planes").select("*").eq("nombre", plan_nombre).execute()
                    if plan.data:
                        supabase.table("gz_clientes").update({
                            "plan": plan_nombre,
                            "consultas_restantes": plan.data[0]["consultas_mes"]
                        }).eq("id", cliente_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/pagos/verificar/{referencia}", tags=["Pagos"])
def verificar_pago(referencia: str, authorization: str = Header(None)):
    user = obtener_usuario(authorization)
    try:
        url = "https://sandbox.wompi.co/v1/transactions?reference=" + referencia
        headers = {"Authorization": "Bearer " + WOMPI_PRIVATE_KEY}
        resp = http_requests.get(url, headers=headers)
        data = resp.json()
        if data.get("data") and len(data["data"]) > 0:
            transaccion = data["data"][0]
            estado = transaccion.get("status", "")
            if estado == "APPROVED":
                cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
                if cliente.data:
                    return {
                        "estado": "APPROVED",
                        "plan": cliente.data[0].get("plan", "starter")
                    }
            return {"estado": estado}
        return {"estado": "NOT_FOUND"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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