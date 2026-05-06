from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os
import secrets
import requests as http_requests
import hashlib
import time
import threading

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
RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")

# --- Cache en memoria ---
ZONAS_CACHE = []
CACHE_CARGADO = False
API_KEYS_CACHE = {}
CACHE_KEYS_TIME = 0
CONSUMO_BUFFER = []
METRICAS_BUFFER = []
# Cache de clientes
CLIENTES_CACHE = []
CLIENTES_CACHE_TIME = 0

def cargar_cache():
    global ZONAS_CACHE, CACHE_CARGADO
    res = supabase.table("zonas").select("*").execute()
    ZONAS_CACHE = res.data
    CACHE_CARGADO = True
    print("CACHE: " + str(len(ZONAS_CACHE)) + " zonas cargadas en memoria")

def invalidar_cache():
    global CACHE_CARGADO
    CACHE_CARGADO = False

def cargar_keys_cache():
    global API_KEYS_CACHE, CACHE_KEYS_TIME
    res = supabase.table("gz_api_keys").select("*, gz_clientes(*)").eq("activa", True).execute()
    API_KEYS_CACHE = {}
    for k in res.data:
        API_KEYS_CACHE[k["api_key"]] = k
    CACHE_KEYS_TIME = time.time()
    print("CACHE: " + str(len(API_KEYS_CACHE)) + " API keys cargadas")

def cargar_clientes_cache():
    global CLIENTES_CACHE, CLIENTES_CACHE_TIME
    res = supabase.table("gz_clientes").select("*").execute()
    CLIENTES_CACHE = res.data
    CLIENTES_CACHE_TIME = time.time()
    print("CACHE: " + str(len(CLIENTES_CACHE)) + " clientes cargados en memoria")

def flush_consumo():
    global CONSUMO_BUFFER
    if not CONSUMO_BUFFER:
        return
    try:
        supabase.table("gz_consumo_log").insert(CONSUMO_BUFFER).execute()
    except Exception:
        pass
    CONSUMO_BUFFER = []

def flush_metricas():
    global METRICAS_BUFFER
    if not METRICAS_BUFFER:
        return
    try:
        buffer_copy = list(METRICAS_BUFFER)
        METRICAS_BUFFER = []
        supabase.table("gz_metricas").insert(buffer_copy).execute()
    except Exception as e:
        print("ERROR flush metricas: " + str(e))

def registrar_metrica(endpoint, metodo, status_code, inicio):
    global METRICAS_BUFFER
    duracion = (time.time() - inicio) * 1000
    METRICAS_BUFFER.append({
        "endpoint": endpoint,
        "metodo": metodo,
        "status_code": status_code,
        "tiempo_ms": round(duracion, 2)
    })
    if len(METRICAS_BUFFER) >= 10:
        flush_metricas()

# --- Keep-alive: hilo que hace ping cada 4 minutos ---
def keep_alive_loop():
    time.sleep(30)  # espera inicial para que el servidor arranque
    while True:
        try:
            url = "https://" + RAILWAY_URL + "/health"
            http_requests.get(url, timeout=10)
            print("KEEP-ALIVE: ping OK -> " + url)
        except Exception as e:
            print("KEEP-ALIVE: fallo -> " + str(e))
        time.sleep(240)  # 4 minutos

# --- Startup: precalentar cache y arrancar keep-alive ---
@app.on_event("startup")
def startup_event():
    print("STARTUP: precalentando cache...")
    cargar_cache()
    cargar_keys_cache()
    cargar_clientes_cache() 
    print("STARTUP: cache listo")
    if RAILWAY_URL:
        t = threading.Thread(target=keep_alive_loop, daemon=True)
        t.start()
        print("KEEP-ALIVE: hilo iniciado para " + RAILWAY_URL)
    else:
        print("KEEP-ALIVE: RAILWAY_PUBLIC_DOMAIN no definido, keep-alive desactivado")

# --- Modelos ---
class Zona(BaseModel):
    nombre: str
    coordenadas: list

class ZonaEditar(BaseModel):
    nombre: str

class Punto(BaseModel):
    lat: float
    lon: float

class PuntosMasivos(BaseModel):
    puntos: list

class ClienteRegistro(BaseModel):
    nombre: str
    empresa: str
    email: str
    password: str

class ClienteLogin(BaseModel):
    email: str
    password: str

class RecuperarPassword(BaseModel):
    email: str

class CambiarPassword(BaseModel):
    access_token: str
    new_password: str

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
    global CACHE_KEYS_TIME
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API Key requerida")
    if x_api_key == ADMIN_KEY:
        return {"id": "admin", "api_key": ADMIN_KEY, "es_admin": True}
    if not API_KEYS_CACHE or (time.time() - CACHE_KEYS_TIME) > 300:
        cargar_keys_cache()
    key_data = API_KEYS_CACHE.get(x_api_key)
    if not key_data:
        raise HTTPException(status_code=401, detail="API Key invalida o inactiva")
    cliente = key_data.get("gz_clientes", {})
    if not cliente.get("activo", False):
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    return key_data

def obtener_usuario(authorization):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.replace("Bearer ", "")
    try:
        user_res = supabase.auth.get_user(token)
        return user_res.user
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalido")

# --- Health check (usado por keep-alive) ---
@app.get("/health", tags=["Sistema"], include_in_schema=False)
def health():
    return {
        "status": "ok",
        "zonas_en_cache": len(ZONAS_CACHE),
        "keys_en_cache": len(API_KEYS_CACHE),
        "metricas_en_buffer": len(METRICAS_BUFFER)
    }

# --- Endpoints de ZONAS (admin) ---
# DESPUÉS - usa el cache
@app.get("/zonas", tags=["Zonas - Admin"])
def listar_zonas():
    t = time.time()
    if not CACHE_CARGADO:
        cargar_cache()
    registrar_metrica("/zonas", "GET", 200, t)
    return ZONAS_CACHE

@app.get("/zonas", tags=["Zonas - Admin"])
def listar_zonas():
    t = time.time()
    res = supabase.table("zonas").select("*").execute()
    registrar_metrica("/zonas", "GET", 200, t)
    return res.data

@app.put("/zonas/{id}", tags=["Zonas - Admin"])
def editar_zona(id: str, zona: ZonaEditar, x_api_key: str = Header(None)):
    t = time.time()
    verificar_admin(x_api_key)
    supabase.table("zonas").update({"nombre": zona.nombre}).eq("id", id).execute()
    invalidar_cache()
    registrar_metrica("/zonas/" + id, "PUT", 200, t)
    return {"mensaje": "Zona actualizada"}

@app.delete("/zonas/{id}", tags=["Zonas - Admin"])
def eliminar_zona(id: str, x_api_key: str = Header(None)):
    t = time.time()
    verificar_admin(x_api_key)
    supabase.table("zonas").delete().eq("id", id).execute()
    invalidar_cache()
    registrar_metrica("/zonas/" + id, "DELETE", 200, t)
    return {"mensaje": "Zona eliminada"}

# --- Endpoint de VERIFICACION (clientes) ---
@app.post("/zonas/verificar", tags=["Verificacion"])
def verificar_punto(punto: Punto, x_api_key: str = Header(None)):
    t = time.time()
    global CONSUMO_BUFFER
    key_data = verificar_cliente_key(x_api_key)
    if not key_data.get("es_admin"):
        CONSUMO_BUFFER.append({
            "api_key_id": key_data["id"],
            "endpoint": "/zonas/verificar"
        })
        if len(CONSUMO_BUFFER) >= 50:
            flush_consumo()
    if not CACHE_CARGADO:
        cargar_cache()
    encontradas = []
    for zona in ZONAS_CACHE:
        coords = zona["coordenadas"]
        if punto_en_poligono([punto.lat, punto.lon], coords):
            encontradas.append({"id": zona["id"], "nombre": zona["nombre"]})
    if not encontradas:
        registrar_metrica("/zonas/verificar", "POST", 200, t)
        return {"zona": None, "mensaje": "El punto no pertenece a ninguna zona"}
    registrar_metrica("/zonas/verificar", "POST", 200, t)
    return {"zona": encontradas[0]["nombre"], "todas": encontradas}

# --- Endpoint de VERIFICACION MASIVA (clientes) ---
@app.post("/zonas/verificar-masivo", tags=["Verificacion"])
def verificar_masivo(datos: PuntosMasivos, x_api_key: str = Header(None)):
    t = time.time()
    global CONSUMO_BUFFER
    key_data = verificar_cliente_key(x_api_key)
    if not CACHE_CARGADO:
        cargar_cache()
    resultados = []
    for punto in datos.puntos:
        lat = punto.get("lat", 0)
        lon = punto.get("lon", 0)
        encontradas = []
        for zona in ZONAS_CACHE:
            coords = zona["coordenadas"]
            if punto_en_poligono([lat, lon], coords):
                encontradas.append({"id": zona["id"], "nombre": zona["nombre"]})
        if encontradas:
            resultados.append({"lat": lat, "lon": lon, "zona": encontradas[0]["nombre"]})
        else:
            resultados.append({"lat": lat, "lon": lon, "zona": None})
    if not key_data.get("es_admin"):
        CONSUMO_BUFFER.append({
            "api_key_id": key_data["id"],
            "endpoint": "/zonas/verificar-masivo",
        })
        if len(CONSUMO_BUFFER) >= 50:
            flush_consumo()
    registrar_metrica("/zonas/verificar-masivo", "POST", 200, t)
    return {"total": len(resultados), "resultados": resultados}

# --- Endpoints de REGISTRO/LOGIN (clientes) ---
@app.post("/auth/registro", tags=["Autenticacion"])
def registro_cliente(datos: ClienteRegistro):
    t = time.time()
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
        invalidar_cache()
        cargar_keys_cache()
        registrar_metrica("/auth/registro", "POST", 200, t)
        return {
            "mensaje": "Registro exitoso",
            "cliente": cliente.data[0],
            "api_key": primera_key
        }
    except Exception as e:
        registrar_metrica("/auth/registro", "POST", 400, t)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login", tags=["Autenticacion"])
def login_cliente(datos: ClienteLogin):
    t = time.time()
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
        registrar_metrica("/auth/login", "POST", 200, t)
        return {
            "cliente": cliente.data[0],
            "api_keys": keys.data,
            "token": auth_res.session.access_token
        }
    except Exception as e:
        registrar_metrica("/auth/login", "POST", 401, t)
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/auth/recuperar", tags=["Autenticacion"])
def recuperar_password(datos: RecuperarPassword):
    t = time.time()
    try:
        supabase.auth.reset_password_email(datos.email, {
            "redirect_to": "https://zonas-frontend.vercel.app/#/portal/reset"
        })
        registrar_metrica("/auth/recuperar", "POST", 200, t)
        return {"mensaje": "Si el correo existe, recibiras un enlace para restablecer tu contrasena"}
    except Exception as e:
        registrar_metrica("/auth/recuperar", "POST", 200, t)
        return {"mensaje": "Si el correo existe, recibiras un enlace para restablecer tu contrasena"}

@app.post("/auth/cambiar-password", tags=["Autenticacion"], include_in_schema=False)
def cambiar_password(datos: CambiarPassword):
    t = time.time()
    try:
        from supabase import create_client as sc
        admin_client = sc(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
        user = supabase.auth.get_user(datos.access_token)
        admin_client.auth.admin.update_user_by_id(user.user.id, {"password": datos.new_password})
        registrar_metrica("/auth/cambiar-password", "POST", 200, t)
        return {"mensaje": "Contrasena actualizada exitosamente"}
    except Exception as e:
        registrar_metrica("/auth/cambiar-password", "POST", 400, t)
        raise HTTPException(status_code=400, detail=str(e))

# --- Endpoints de API KEYS (clientes autenticados) ---
@app.post("/mis-keys", tags=["API Keys"])
def crear_api_key(datos: ApiKeyCrear, authorization: str = Header(None)):
    t = time.time()
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
    cargar_keys_cache()
    registrar_metrica("/mis-keys", "POST", 200, t)
    return res.data[0]

@app.get("/mis-keys", tags=["API Keys"])
def listar_mis_keys(authorization: str = Header(None)):
    t = time.time()
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    keys = supabase.table("gz_api_keys").select("*").eq("cliente_id", cliente.data[0]["id"]).execute()
    registrar_metrica("/mis-keys", "GET", 200, t)
    return keys.data

@app.delete("/mis-keys/{id}", tags=["API Keys"])
def revocar_api_key(id: str, authorization: str = Header(None)):
    t = time.time()
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    supabase.table("gz_api_keys").delete().eq("id", id).eq("cliente_id", cliente.data[0]["id"]).execute()
    cargar_keys_cache()
    registrar_metrica("/mis-keys/" + id, "DELETE", 200, t)
    return {"mensaje": "API Key revocada"}

# --- Endpoint de CONSUMO (clientes) ---
@app.get("/mi-consumo", tags=["Consumo"])
def ver_consumo(authorization: str = Header(None)):
    t = time.time()
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    keys = supabase.table("gz_api_keys").select("id").eq("cliente_id", cliente.data[0]["id"]).execute()
    key_ids = [k["id"] for k in keys.data]
    if not key_ids:
        registrar_metrica("/mi-consumo", "GET", 200, t)
        return {"total": 0, "detalle": []}
    logs = supabase.table("gz_consumo_log").select("*").in_("api_key_id", key_ids).execute()
    registrar_metrica("/mi-consumo", "GET", 200, t)
    return {"total": len(logs.data), "detalle": logs.data}

# --- Endpoint de MI PLAN (clientes) ---
@app.get("/mi-plan", tags=["Plan"])
def ver_plan(authorization: str = Header(None)):
    t = time.time()
    user = obtener_usuario(authorization)
    cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    c = cliente.data[0]
    plan_info = supabase.table("gz_planes").select("*").eq("nombre", c.get("plan", "starter")).execute()
    registrar_metrica("/mi-plan", "GET", 200, t)
    return {
        "plan": c.get("plan", "starter"),
        "consultas_restantes": c.get("consultas_restantes", 0),
        "consultas_mes": plan_info.data[0]["consultas_mes"] if plan_info.data else 1000,
        "max_api_keys": plan_info.data[0]["max_api_keys"] if plan_info.data else 1
    }

# --- Endpoints de PAGO con Wompi ---
@app.post("/pagos/crear", tags=["Pagos"], include_in_schema=False)
def crear_pago(datos: CrearTransaccion, authorization: str = Header(None)):
    t = time.time()
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
    referencia = "gz" + secrets.token_hex(12)
    integrity_secret = os.getenv("WOMPI_INTEGRITY_SECRET", "")
    integrity_str = referencia + str(precio_centavos) + "COP" + integrity_secret
    integrity_hash = hashlib.sha256(integrity_str.encode('utf-8')).hexdigest()
    registrar_metrica("/pagos/crear", "POST", 200, t)
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

@app.post("/pagos/webhook", tags=["Pagos"], include_in_schema=False)
async def webhook_wompi(request: Request):
    t = time.time()
    body = await request.json()
    try:
        evento = body.get("event", "")
        data = body.get("data", {}).get("transaction", {})
        referencia = data.get("reference", "")
        estado = data.get("status", "")
        if evento == "transaction.updated" and estado == "APPROVED":
            if referencia.startswith("gz"):
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
        registrar_metrica("/pagos/webhook", "POST", 200, t)
        return {"ok": True}
    except Exception as e:
        registrar_metrica("/pagos/webhook", "POST", 500, t)
        return {"ok": False, "error": str(e)}

@app.get("/pagos/verificar/{referencia}", tags=["Pagos"], include_in_schema=False)
def verificar_pago(referencia: str, authorization: str = Header(None)):
    t = time.time()
    user = obtener_usuario(authorization)
    try:
        url = "https://production.wompi.co/v1/transactions?reference=" + referencia
        headers = {"Authorization": "Bearer " + WOMPI_PRIVATE_KEY}
        resp = http_requests.get(url, headers=headers)
        data = resp.json()
        if data.get("data") and len(data["data"]) > 0:
            transaccion = data["data"][0]
            estado = transaccion.get("status", "")
            if estado == "APPROVED":
                cliente = supabase.table("gz_clientes").select("*").eq("user_id", user.id).execute()
                if cliente.data:
                    plan_nombre = "business"
                    plan = supabase.table("gz_planes").select("*").eq("nombre", plan_nombre).execute()
                    if plan.data:
                        supabase.table("gz_clientes").update({
                            "plan": plan_nombre,
                            "consultas_restantes": plan.data[0]["consultas_mes"]
                        }).eq("id", cliente.data[0]["id"]).execute()
                    registrar_metrica("/pagos/verificar", "GET", 200, t)
                    return {
                        "estado": "APPROVED",
                        "plan": plan_nombre
                    }
            registrar_metrica("/pagos/verificar", "GET", 200, t)
            return {"estado": estado}
        registrar_metrica("/pagos/verificar", "GET", 404, t)
        return {"estado": "NOT_FOUND"}
    except Exception as e:
        registrar_metrica("/pagos/verificar", "GET", 500, t)
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints ADMIN (gestion de clientes) ---
@app.get("/admin/clientes", tags=["Admin"], include_in_schema=False)
def listar_clientes(x_api_key: str = Header(None)):
    t = time.time()
    verificar_admin(x_api_key)
    if not CLIENTES_CACHE or (time.time() - CLIENTES_CACHE_TIME) > 300:
        cargar_clientes_cache()
    registrar_metrica("/admin/clientes", "GET", 200, t)
    return CLIENTES_CACHE

@app.put("/admin/clientes/{id}/toggle", tags=["Admin"], include_in_schema=False)
def toggle_cliente(id: str, x_api_key: str = Header(None)):
    t = time.time()
    verificar_admin(x_api_key)
    cliente = supabase.table("gz_clientes").select("*").eq("id", id).execute()
    if not cliente.data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    nuevo_estado = not cliente.data[0]["activo"]
    supabase.table("gz_clientes").update({"activo": nuevo_estado}).eq("id", id).execute()
    cargar_clientes_cache()
    registrar_metrica("/admin/clientes/" + id + "/toggle", "PUT", 200, t)
    return {"activo": nuevo_estado}

# --- Endpoint de METRICAS (admin) ---
@app.get("/admin/metricas", tags=["Admin"], include_in_schema=False)
def ver_metricas(x_api_key: str = Header(None)):
    verificar_admin(x_api_key)
    flush_metricas()
    res = supabase.table("gz_metricas").select("*").order("created_at", desc=True).limit(1000).execute()
    datos = res.data
    if not datos:
        return {"total_peticiones": 0, "promedio_ms": 0, "tasa_error": 0, "errores": 0, "endpoints": {}}
    total = len(datos)
    promedio = sum([d["tiempo_ms"] for d in datos]) / total
    errores = len([d for d in datos if d["status_code"] >= 400])
    endpoints = {}
    for d in datos:
        ep = d["metodo"] + " " + d["endpoint"]
        if ep not in endpoints:
            endpoints[ep] = {"total": 0, "tiempos": [], "errores": 0}
        endpoints[ep]["total"] += 1
        endpoints[ep]["tiempos"].append(d["tiempo_ms"])
        if d["status_code"] >= 400:
            endpoints[ep]["errores"] += 1
    resumen = {}
    for ep in endpoints:
        t = endpoints[ep]["tiempos"]
        resumen[ep] = {
            "total": endpoints[ep]["total"],
            "promedio_ms": round(sum(t) / len(t), 1),
            "min_ms": round(min(t), 1),
            "max_ms": round(max(t), 1),
            "errores": endpoints[ep]["errores"]
        }
    return {
        "total_peticiones": total,
        "promedio_ms": round(promedio, 1),
        "tasa_error": round(errores / total * 100, 2),
        "errores": errores,
        "endpoints": resumen
    }

# --- Evento de cierre ---
@app.on_event("shutdown")
def shutdown_event():
    flush_consumo()
    flush_metricas()