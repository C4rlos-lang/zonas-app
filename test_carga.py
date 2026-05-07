import requests
import time
import random
import concurrent.futures
import statistics

API_URL = "https://zonas-app-production.up.railway.app/zonas/verificar"
API_KEY = "gz_87e510111663adc4d978fd15ef04ebacae287e69db6779e8"  # CAMBIA POR TU API KEY

# Coordenadas de prueba en las 5 ciudades
PUNTOS_PRUEBA = [
    # Bogotá
    {"lat": 4.7350, "lon": -74.0320},
    {"lat": 4.6450, "lon": -74.0620},
    {"lat": 4.6100, "lon": -74.0730},
    {"lat": 4.6300, "lon": -74.1550},
    {"lat": 4.7000, "lon": -74.1150},
    {"lat": 4.7550, "lon": -74.0850},
    {"lat": 4.6350, "lon": -74.0850},
    {"lat": 4.5350, "lon": -74.1500},
    {"lat": 4.6700, "lon": -74.0500},
    {"lat": 4.7200, "lon": -74.0450},
    # Medellín
    {"lat": 6.2050, "lon": -75.5650},
    {"lat": 6.2450, "lon": -75.5900},
    {"lat": 6.2300, "lon": -75.6050},
    {"lat": 6.2750, "lon": -75.5900},
    {"lat": 6.2500, "lon": -75.5700},
    {"lat": 6.1750, "lon": -75.5900},
    {"lat": 6.1850, "lon": -75.6100},
    # Barranquilla
    {"lat": 10.9950, "lon": -74.7950},
    {"lat": 10.9800, "lon": -74.7800},
    {"lat": 10.9650, "lon": -74.7850},
    {"lat": 11.0150, "lon": -74.8250},
    {"lat": 10.9250, "lon": -74.7750},
    # Cali
    {"lat": 3.4500, "lon": -76.5450},
    {"lat": 3.3700, "lon": -76.5350},
    {"lat": 3.4800, "lon": -76.5300},
    {"lat": 3.4300, "lon": -76.4900},
    {"lat": 3.3550, "lon": -76.5100},
    # Bucaramanga
    {"lat": 7.1150, "lon": -73.1200},
    {"lat": 7.1300, "lon": -73.1050},
    {"lat": 7.0950, "lon": -73.1150},
    # Puntos FUERA de zonas (para probar negativos)
    {"lat": 5.0000, "lon": -74.0000},
    {"lat": 8.0000, "lon": -73.5000},
    {"lat": 2.0000, "lon": -76.0000},
]

TOTAL_PETICIONES = 3000
HILOS_CONCURRENTES = 10

resultados = {
    "exitosas": 0,
    "fallidas": 0,
    "zona_encontrada": 0,
    "sin_zona": 0,
    "tiempos": [],
    "errores": []
}

def hacer_peticion(i):
    punto = random.choice(PUNTOS_PRUEBA)
    # Agregar variación aleatoria pequeña
    lat = punto["lat"] + random.uniform(-0.002, 0.002)
    lon = punto["lon"] + random.uniform(-0.002, 0.002)

    inicio = time.time()
    try:
        resp = requests.post(
            API_URL,
            json={"lat": round(lat, 6), "lon": round(lon, 6)},
            headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
            timeout=30
        )
        duracion = (time.time() - inicio) * 1000  # ms

        if resp.status_code == 200:
            data = resp.json()
            return {
                "ok": True,
                "tiempo": duracion,
                "zona": data.get("zona"),
                "status": 200
            }
        else:
            return {
                "ok": False,
                "tiempo": duracion,
                "error": resp.text,
                "status": resp.status_code
            }
    except Exception as e:
        duracion = (time.time() - inicio) * 1000
        return {
            "ok": False,
            "tiempo": duracion,
            "error": str(e),
            "status": 0
        }

def main():
    print("=" * 60)
    print("  PRUEBA DE CARGA - GeoZonas API")
    print("=" * 60)
    print(f"  Total peticiones:    {TOTAL_PETICIONES}")
    print(f"  Hilos concurrentes:  {HILOS_CONCURRENTES}")
    print(f"  API URL:             {API_URL}")
    print("=" * 60)
    print()

    inicio_total = time.time()
    tiempos = []
    exitosas = 0
    fallidas = 0
    zona_encontrada = 0
    sin_zona = 0
    errores_por_codigo = {}

    print(f"  Enviando {TOTAL_PETICIONES} peticiones...\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=HILOS_CONCURRENTES) as executor:
        futuros = [executor.submit(hacer_peticion, i) for i in range(TOTAL_PETICIONES)]

        completadas = 0
        for futuro in concurrent.futures.as_completed(futuros):
            resultado = futuro.result()
            completadas += 1

            if resultado["ok"]:
                exitosas += 1
                tiempos.append(resultado["tiempo"])
                if resultado["zona"]:
                    zona_encontrada += 1
                else:
                    sin_zona += 1
            else:
                fallidas += 1
                code = resultado.get("status", 0)
                errores_por_codigo[code] = errores_por_codigo.get(code, 0) + 1

            if completadas % 500 == 0:
                elapsed = time.time() - inicio_total
                rps = completadas / elapsed if elapsed > 0 else 0
                print(f"  Progreso: {completadas}/{TOTAL_PETICIONES} ({rps:.1f} req/s)")

    duracion_total = time.time() - inicio_total

    print()
    print("=" * 60)
    print("  RESULTADOS")
    print("=" * 60)
    print(f"  Duración total:      {duracion_total:.2f} segundos")
    print(f"  Requests/segundo:    {TOTAL_PETICIONES / duracion_total:.1f}")
    print()
    print(f"  Exitosas:            {exitosas} ({exitosas/TOTAL_PETICIONES*100:.1f}%)")
    print(f"  Fallidas:            {fallidas} ({fallidas/TOTAL_PETICIONES*100:.1f}%)")
    print(f"  Zona encontrada:    {zona_encontrada}")
    print(f"  Sin zona:            {sin_zona}")
    print()

    if tiempos:
        print("  TIEMPOS DE RESPUESTA")
        print(f"  Mínimo:              {min(tiempos):.0f} ms")
        print(f"  Máximo:              {max(tiempos):.0f} ms")
        print(f"  Promedio:            {statistics.mean(tiempos):.0f} ms")
        print(f"  Mediana:             {statistics.median(tiempos):.0f} ms")
        print(f"  P95:                 {sorted(tiempos)[int(len(tiempos)*0.95)]:.0f} ms")
        print(f"  P99:                 {sorted(tiempos)[int(len(tiempos)*0.99)]:.0f} ms")
    print()

    if errores_por_codigo:
        print("  ERRORES POR CÓDIGO")
        for code, count in sorted(errores_por_codigo.items()):
            print(f"  HTTP {code}:             {count}")
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()
