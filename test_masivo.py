import requests
import time
import random

API_URL = "https://zonas-app-production.up.railway.app/zonas/verificar-masivo"
API_KEY = "gz_87e510111663adc4d978fd15ef04ebacae287e69db6779e8"  # CAMBIA POR TU API KEY

# Coordenadas base de las 5 ciudades
BASES = [
    (4.7350, -74.0320), (4.6450, -74.0620), (4.6100, -74.0730),
    (4.6300, -74.1550), (4.7000, -74.1150), (4.7550, -74.0850),
    (4.6350, -74.0850), (4.5350, -74.1500), (4.6700, -74.0500),
    (4.7200, -74.0450),
    (6.2050, -75.5650), (6.2450, -75.5900), (6.2300, -75.6050),
    (6.2750, -75.5900), (6.2500, -75.5700), (6.1750, -75.5900),
    (10.9950, -74.7950), (10.9800, -74.7800), (10.9650, -74.7850),
    (11.0150, -74.8250), (10.9250, -74.7750),
    (3.4500, -76.5450), (3.3700, -76.5350), (3.4800, -76.5300),
    (3.4300, -76.4900), (3.3550, -76.5100),
    (7.1150, -73.1200), (7.1300, -73.1050), (7.0950, -73.1150),
    (5.0000, -74.0000), (8.0000, -73.5000), (2.0000, -76.0000),
]

TOTAL_PUNTOS = 3000

print("=" * 60)
print("  PRUEBA MASIVA - GeoZonas API")
print("=" * 60)
print(f"  Total puntos:        {TOTAL_PUNTOS}")
print(f"  Peticiones HTTP:     1")
print(f"  API URL:             {API_URL}")
print("=" * 60)
print()

# Generar puntos
puntos = []
for i in range(TOTAL_PUNTOS):
    base = random.choice(BASES)
    lat = round(base[0] + random.uniform(-0.002, 0.002), 6)
    lon = round(base[1] + random.uniform(-0.002, 0.002), 6)
    puntos.append({"lat": lat, "lon": lon})

print(f"  Generados {len(puntos)} puntos aleatorios")
print(f"  Enviando peticion masiva...")
print()

inicio = time.time()

try:
    resp = requests.post(
        API_URL,
        json={"puntos": puntos},
        headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
        timeout=120
    )
    duracion = time.time() - inicio

    if resp.status_code == 200:
        data = resp.json()
        total = data.get("total", 0)
        resultados = data.get("resultados", [])
        con_zona = len([r for r in resultados if r["zona"]])
        sin_zona = len([r for r in resultados if not r["zona"]])

        print("=" * 60)
        print("  RESULTADOS")
        print("=" * 60)
        print(f"  Status:              200 OK")
        print(f"  Duracion total:      {duracion:.2f} segundos")
        print(f"  Puntos procesados:   {total}")
        print(f"  Puntos/segundo:      {total / duracion:.0f}")
        print()
        print(f"  Zona encontrada:     {con_zona}")
        print(f"  Sin zona:            {sin_zona}")
        print()
        print("  PRIMEROS 10 RESULTADOS:")
        for r in resultados[:10]:
            zona = r["zona"] or "-- fuera --"
            print(f"    ({r['lat']}, {r['lon']}) -> {zona}")
        print()
        print("=" * 60)
    else:
        duracion = time.time() - inicio
        print(f"  ERROR: HTTP {resp.status_code}")
        print(f"  Duracion: {duracion:.2f} segundos")
        print(f"  Respuesta: {resp.text[:500]}")

except Exception as e:
    duracion = time.time() - inicio
    print(f"  ERROR: {str(e)}")
    print(f"  Duracion: {duracion:.2f} segundos")

print()
