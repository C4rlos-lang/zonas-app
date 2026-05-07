import requests
import time

API_URL = "https://zonas-app-production.up.railway.app/zonas/verificar-masivo"
API_KEY = "gz_87e510111663adc4d978fd15ef04ebacae287e69db6779e8"  # CAMBIA POR TU API KEY

# Puntos EXACTOS en el centro de cada zona creada
# Cada entrada: (lat, lon, zona_esperada)
PUNTOS_EXACTOS = [
    # ========== BOGOTÁ ==========
    (4.7350, -74.0320, "BOG - Usaquén"),
    (4.6450, -74.0620, "BOG - Chapinero"),
    (4.6100, -74.0730, "BOG - Santa Fe Centro"),
    (4.5700, -74.0850, "BOG - San Cristóbal"),
    (4.5100, -74.1200, "BOG - Usme"),
    (4.5750, -74.1300, "BOG - Tunjuelito"),
    (4.6100, -74.1850, "BOG - Bosa"),
    (4.6300, -74.1550, "BOG - Kennedy Norte"),
    (4.6050, -74.1600, "BOG - Kennedy Sur"),
    (4.6700, -74.1450, "BOG - Fontibón"),
    (4.7000, -74.1150, "BOG - Engativá"),
    (4.7550, -74.0850, "BOG - Suba Norte"),
    (4.7400, -74.1000, "BOG - Suba Centro"),
    (4.6650, -74.0800, "BOG - Barrios Unidos"),
    (4.6350, -74.0850, "BOG - Teusaquillo"),
    (4.6100, -74.0900, "BOG - Los Mártires"),
    (4.5900, -74.1050, "BOG - Antonio Nariño"),
    (4.6150, -74.1100, "BOG - Puente Aranda"),
    (4.5950, -74.0750, "BOG - La Candelaria"),
    (4.5650, -74.1100, "BOG - Rafael Uribe"),
    (4.5350, -74.1500, "BOG - Ciudad Bolívar"),
    (4.6700, -74.0500, "BOG - Zona T Chicó"),
    (4.7200, -74.0450, "BOG - Cedritos"),
    (4.7100, -74.0700, "BOG - Niza"),
    (4.6750, -74.1250, "BOG - Modelia"),
    (4.6500, -74.1350, "BOG - Castilla"),
    (4.6300, -74.1750, "BOG - Patio Bonito"),
    (4.6500, -74.1650, "BOG - Tintal"),
    (4.6600, -74.1050, "BOG - Salitre"),
    (4.7300, -74.0600, "BOG - Colina Campestre"),

    # ========== MEDELLÍN ==========
    (6.2050, -75.5650, "MDE - El Poblado"),
    (6.2450, -75.5900, "MDE - Laureles"),
    (6.2300, -75.6050, "MDE - Belén"),
    (6.2500, -75.5950, "MDE - La América"),
    (6.2750, -75.5900, "MDE - Robledo"),
    (6.2700, -75.5550, "MDE - Aranjuez"),
    (6.2800, -75.5400, "MDE - Manrique"),
    (6.2900, -75.5450, "MDE - Popular"),
    (6.2850, -75.5550, "MDE - Santa Cruz"),
    (6.2550, -75.5450, "MDE - Villa Hermosa"),
    (6.2350, -75.5500, "MDE - Buenos Aires"),
    (6.2500, -75.5650, "MDE - La Candelaria"),
    (6.2150, -75.5850, "MDE - Guayabal"),
    (6.2800, -75.5750, "MDE - Castilla"),
    (6.2900, -75.5700, "MDE - Doce de Octubre"),
    (6.2650, -75.6100, "MDE - San Javier"),
    (6.2500, -75.5800, "MDE - Estadio"),
    (6.2500, -75.5700, "MDE - Centro"),
    (6.2400, -75.5850, "MDE - Suramericana"),
    (6.2550, -75.5950, "MDE - Florida Nueva"),
    (6.2600, -75.6050, "MDE - Calasanz"),
    (6.2650, -75.5800, "MDE - La Floresta"),
    (6.1750, -75.5900, "MDE - Envigado Centro"),
    (6.1600, -75.5950, "MDE - Envigado Sur"),
    (6.1850, -75.6100, "MDE - Itagüí"),
    (6.1500, -75.6150, "MDE - Sabaneta"),
    (6.1900, -75.6300, "MDE - San Antonio Prado"),
    (6.2200, -75.6200, "MDE - Altavista"),
    (6.2850, -75.6150, "MDE - San Cristóbal"),
    (6.3050, -75.6350, "MDE - Palmitas"),

    # ========== BARRANQUILLA ==========
    (10.9950, -74.7950, "BAQ - El Prado"),
    (11.0000, -74.8050, "BAQ - Alto Prado"),
    (11.0100, -74.8150, "BAQ - Riomar"),
    (11.0050, -74.8100, "BAQ - Villa Country"),
    (10.9900, -74.8000, "BAQ - Ciudad Jardín"),
    (10.9850, -74.7900, "BAQ - Los Alpes"),
    (10.9800, -74.7800, "BAQ - Boston"),
    (10.9980, -74.7850, "BAQ - Barrio Abajo"),
    (10.9650, -74.7850, "BAQ - Centro"),
    (10.9700, -74.7750, "BAQ - Modelo"),
    (10.9750, -74.7900, "BAQ - Las Delicias"),
    (10.9800, -74.7950, "BAQ - San Felipe"),
    (10.9550, -74.7950, "BAQ - Recreo"),
    (10.9600, -74.8050, "BAQ - La Victoria"),
    (10.9500, -74.7900, "BAQ - San José"),
    (10.9450, -74.8000, "BAQ - Simón Bolívar"),
    (10.9700, -74.8000, "BAQ - Las Nieves"),
    (10.9600, -74.7750, "BAQ - Chiquinquirá"),
    (10.9550, -74.7700, "BAQ - Rebolo"),
    (11.0150, -74.8250, "BAQ - Villa Santos"),
    (11.0050, -74.8250, "BAQ - Buenavista"),
    (10.9950, -74.8150, "BAQ - El Golf"),
    (10.9900, -74.8100, "BAQ - La Castellana"),
    (11.0250, -74.8050, "BAQ - Las Flores"),
    (11.0350, -74.8350, "BAQ - Puerto Colombia"),
    (10.9250, -74.7750, "BAQ - Soledad Norte"),
    (10.9150, -74.7700, "BAQ - Soledad Centro"),
    (10.9050, -74.7650, "BAQ - Soledad Sur"),
    (10.8650, -74.7750, "BAQ - Malambo"),
    (10.9350, -74.7850, "BAQ - La Chinita"),

    # ========== CALI ==========
    (3.4500, -76.5450, "CLO - El Peñón"),
    (3.4400, -76.5400, "CLO - San Antonio"),
    (3.4550, -76.5350, "CLO - Granada"),
    (3.3700, -76.5350, "CLO - Ciudad Jardín"),
    (3.3850, -76.5250, "CLO - El Ingenio"),
    (3.3950, -76.5300, "CLO - El Limonar"),
    (3.3600, -76.5200, "CLO - Valle del Lili"),
    (3.4800, -76.5300, "CLO - Menga"),
    (3.4700, -76.5200, "CLO - Flora"),
    (3.4600, -76.5250, "CLO - Cristales"),
    (3.4250, -76.5350, "CLO - San Fernando"),
    (3.4350, -76.5250, "CLO - Normandía"),
    (3.4200, -76.5400, "CLO - Tequendama"),
    (3.3750, -76.5400, "CLO - El Refugio"),
    (3.4150, -76.5500, "CLO - Santa Mónica"),
    (3.3550, -76.5100, "CLO - Caney"),
    (3.3400, -76.5450, "CLO - Pance"),
    (3.4400, -76.5500, "CLO - El Lido"),
    (3.4500, -76.5150, "CLO - Bretaña"),
    (3.4500, -76.5350, "CLO - Centro"),
    (3.4300, -76.4900, "CLO - Aguablanca"),
    (3.4250, -76.5600, "CLO - Siloé"),
    (3.4650, -76.4950, "CLO - Alfonso López"),
    (3.4150, -76.4950, "CLO - Marroquín"),
    (3.4750, -76.5050, "CLO - Petecuy"),
    (3.4600, -76.5050, "CLO - Calima"),
    (3.4350, -76.5100, "CLO - Alameda"),
    (3.4100, -76.5150, "CLO - Miraflores"),
    (3.4450, -76.5000, "CLO - Junín"),
    (3.4550, -76.5450, "CLO - Versalles"),

    # ========== BUCARAMANGA ==========
    (7.1150, -73.1200, "BGA - Cabecera"),
    (7.1100, -73.1150, "BGA - Sotomayor"),
    (7.1050, -73.1100, "BGA - San Alonso"),
    (7.1200, -73.1100, "BGA - La Concordia"),
    (7.1080, -73.1250, "BGA - Provenza"),
    (7.1020, -73.1200, "BGA - El Prado"),
    (7.1000, -73.1050, "BGA - Álvarez"),
    (7.0950, -73.1150, "BGA - Lagos Cacique"),
    (7.0900, -73.1100, "BGA - Pan de Azúcar"),
    (7.1300, -73.1050, "BGA - Cañaveral"),
    (7.1250, -73.1250, "BGA - Centro"),
    (7.0850, -73.1200, "BGA - Real de Minas"),
    (7.1350, -73.1150, "BGA - La Aurora"),
    (7.0950, -73.1250, "BGA - Mutis"),
    (7.1300, -73.1300, "BGA - Diamante"),
    (7.1200, -73.1350, "BGA - San Francisco"),
    (7.1150, -73.1350, "BGA - La Victoria"),
    (7.1100, -73.1300, "BGA - García Rovira"),
    (7.1050, -73.1350, "BGA - Comuneros"),
    (7.1400, -73.1200, "BGA - Morrorico"),
    (7.0980, -73.1300, "BGA - La Floresta"),
    (7.1350, -73.1350, "BGA - Ciudadela"),
    (7.1250, -73.1350, "BGA - Kennedy"),
    (7.1150, -73.1050, "BGA - Girardot"),
    (7.1050, -73.1000, "BGA - La Joya"),
    (7.0950, -73.1050, "BGA - Terrazas"),
    (7.1200, -73.1050, "BGA - El Jardín"),
    (7.1300, -73.1200, "BGA - La Universidad"),
    (7.1250, -73.1150, "BGA - Conucos"),
    (7.1000, -73.1150, "BGA - Antiguo Campestre"),

    # ========== PUNTOS FUERA (deben devolver null) ==========
    (5.0000, -74.0000, None),
    (8.0000, -73.5000, None),
    (2.0000, -76.0000, None),
    (0.0000, -70.0000, None),
    (12.0000, -72.0000, None),
]

print("=" * 60)
print("  PRUEBA DE CALIDAD - GeoZonas API")
print("=" * 60)
print(f"  Total puntos:        {len(PUNTOS_EXACTOS)}")
print(f"  Zonas validas:       {len([p for p in PUNTOS_EXACTOS if p[2]])}")
print(f"  Puntos fuera:        {len([p for p in PUNTOS_EXACTOS if not p[2]])}")
print("=" * 60)
print()

puntos_body = [{"lat": p[0], "lon": p[1]} for p in PUNTOS_EXACTOS]

inicio = time.time()
resp = requests.post(
    API_URL,
    json={"puntos": puntos_body},
    headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
    timeout=60
)
duracion = time.time() - inicio

if resp.status_code != 200:
    print(f"  ERROR: HTTP {resp.status_code}")
    print(f"  {resp.text[:500]}")
    exit()

data = resp.json()
resultados = data.get("resultados", [])

correctos = 0
incorrectos = 0
errores_detalle = []

for i, resultado in enumerate(resultados):
    esperado = PUNTOS_EXACTOS[i][2]
    obtenido = resultado.get("zona")

    if esperado == obtenido:
        correctos += 1
    elif esperado is None and obtenido is None:
        correctos += 1
    else:
        incorrectos += 1
        errores_detalle.append({
            "lat": PUNTOS_EXACTOS[i][0],
            "lon": PUNTOS_EXACTOS[i][1],
            "esperado": esperado,
            "obtenido": obtenido
        })

total = correctos + incorrectos
precision = (correctos / total * 100) if total > 0 else 0

print("=" * 60)
print("  RESULTADOS DE CALIDAD")
print("=" * 60)
print(f"  Duracion:            {duracion:.2f} segundos")
print(f"  Puntos evaluados:    {total}")
print()
print(f"  CORRECTOS:           {correctos} ({precision:.1f}%)")
print(f"  INCORRECTOS:         {incorrectos} ({100-precision:.1f}%)")
print()

if errores_detalle:
    print("  DETALLE DE ERRORES:")
    print("  " + "-" * 56)
    for e in errores_detalle[:20]:
        esp = e["esperado"] or "-- fuera --"
        obt = e["obtenido"] or "-- fuera --"
        print(f"  ({e['lat']}, {e['lon']})")
        print(f"    Esperado: {esp}")
        print(f"    Obtenido: {obt}")
        print()
else:
    print("  SIN ERRORES - 100% DE PRECISION")
    print()

# Resumen por ciudad
print("  RESUMEN POR CIUDAD:")
print("  " + "-" * 56)
ciudades = {"BOG": 0, "MDE": 0, "BAQ": 0, "CLO": 0, "BGA": 0}
ciudades_ok = {"BOG": 0, "MDE": 0, "BAQ": 0, "CLO": 0, "BGA": 0}

for i, resultado in enumerate(resultados):
    esperado = PUNTOS_EXACTOS[i][2]
    if not esperado:
        continue
    ciudad = esperado[:3]
    if ciudad in ciudades:
        ciudades[ciudad] += 1
        obtenido = resultado.get("zona")
        if esperado == obtenido:
            ciudades_ok[ciudad] += 1

nombres = {"BOG": "Bogota", "MDE": "Medellin", "BAQ": "Barranquilla", "CLO": "Cali", "BGA": "Bucaramanga"}
for c in ciudades:
    total_c = ciudades[c]
    ok_c = ciudades_ok[c]
    pct = (ok_c / total_c * 100) if total_c > 0 else 0
    print(f"  {nombres[c]:15s}  {ok_c}/{total_c}  ({pct:.0f}%)")

print()
print("=" * 60)
