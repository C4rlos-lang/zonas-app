"""
Normalizador de direcciones colombianas para GeoZonas.
Convierte las multiples variantes de escritura a un formato estandar
antes de geocodificar.

Casuistica colombiana: una misma direccion puede escribirse de muchas
formas ("cll 10", "cl 10", "calle 10", "c 10"). Este modulo las unifica.
"""

import re
import unicodedata


# --- Diccionario de vias (tipos de calle) ---
# Cada clave es la forma estandar; el valor es la lista de variantes.
TIPOS_VIA = {
    "Calle": ["calle", "cll", "cl", "c", "clle", "ca"],
    "Carrera": ["carrera", "cra", "cr", "kra", "kr", "k", "carr", "cras"],
    "Avenida": ["avenida", "av", "ave", "avda"],
    "Avenida Carrera": ["avenida carrera", "av carrera", "av cra", "av cr", "av kra", "avc"],
    "Avenida Calle": ["avenida calle", "av calle", "av cll", "av cl", "avcl"],
    "Diagonal": ["diagonal", "diag", "dg", "dia"],
    "Transversal": ["transversal", "trans", "tv", "tr", "trv", "transv"],
    "Circular": ["circular", "circ", "cir"],
    "Circunvalar": ["circunvalar", "circunv", "cvl"],
    "Autopista": ["autopista", "auto", "aut", "autop"],
    "Via": ["via"],
    "Manzana": ["manzana", "mz", "mza", "man"],
    "Bloque": ["bloque", "bl", "blq", "bloq"],
}

# --- Complementos / descriptores de destino ---
COMPLEMENTOS = {
    "Apartamento": ["apartamento", "apto", "apt", "ap", "aptos"],
    "Interior": ["interior", "int", "itr"],
    "Torre": ["torre", "tr", "to", "tor"],
    "Bloque": ["bloque", "bl", "blq", "bloq"],
    "Casa": ["casa", "csa", "cs"],
    "Piso": ["piso", "ps", "p"],
    "Local": ["local", "lc", "loc", "lcl"],
    "Oficina": ["oficina", "of", "ofc", "ofic"],
    "Bodega": ["bodega", "bod", "bg"],
    "Edificio": ["edificio", "ed", "edif", "edf"],
    "Conjunto": ["conjunto", "conj", "cj"],
    "Etapa": ["etapa", "et", "etp"],
    "Manzana": ["manzana", "mz", "mza", "man"],
    "Lote": ["lote", "lt", "lote", "lot"],
    "Sur": ["sur", "s"],
    "Norte": ["norte", "n", "nte"],
    "Este": ["este", "e", "est"],
    "Oeste": ["oeste", "o", "w", "oes"],
}


def _quitar_tildes(texto):
    """Elimina tildes y diacriticos, preservando la enie como n."""
    texto = texto.replace("ñ", "\x00").replace("Ñ", "\x00")
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.replace("\x00", "n")


def _construir_lookup(diccionario):
    """Invierte el diccionario: cada variante -> forma estandar."""
    lookup = {}
    for estandar, variantes in diccionario.items():
        for v in variantes:
            lookup[v] = estandar
    return lookup


_LOOKUP_VIA = _construir_lookup(TIPOS_VIA)
_LOOKUP_COMPLEMENTO = _construir_lookup(COMPLEMENTOS)


def normalizar_direccion(direccion_raw, ciudad=None):
    """
    Normaliza una direccion colombiana a formato estandar.

    Args:
        direccion_raw: la direccion tal como viene ("cll 10 # 5-30 apto 201")
        ciudad: opcional, ciudad/municipio para dar contexto al geocoder

    Returns:
        dict con:
          - original: la entrada sin tocar
          - normalizada: la direccion estandarizada
          - via_principal: tipo de via principal detectada (Calle, Carrera...)
          - numero_via: numero de la via principal
          - query_geocoder: string listo para mandar a Nominatim
    """
    if not direccion_raw or not direccion_raw.strip():
        return {
            "original": direccion_raw,
            "normalizada": "",
            "via_principal": None,
            "numero_via": None,
            "query_geocoder": "",
        }

    original = direccion_raw

    # 1. Limpieza base: minusculas, sin tildes, espacios colapsados
    texto = _quitar_tildes(direccion_raw.lower().strip())

    # 2. Unificar separadores de numero (#, No, Nro, N°) a "#"
    # Solo cuando van seguidos de un digito, para no romper "norte" o "numero" sueltos.
    texto = texto.replace("°", "").replace("º", "").replace("ª", "")
    texto = re.sub(r"\b(numero|nro|num|no)\b\s*\.?\s*[:.\-]?\s*(?=\d)", "# ", texto)
    # "n" como abreviatura de numero: solo si va seguida de digito
    texto = re.sub(r"\bn\s*\.?\s*[:.\-]?\s*(?=\d)", "# ", texto)
    texto = re.sub(r"\s*#\s*", " # ", texto)

    # 3. Normalizar guiones entre numeros (5 - 30  ->  5-30)
    texto = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", texto)

    # 4. Colapsar espacios y quitar puntos sueltos
    texto = re.sub(r"\.", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    # 5. Tokenizar y traducir cada token via/complemento
    tokens = texto.split(" ")
    resultado = []
    via_principal = None
    numero_via = None
    i = 0
    primera_via_encontrada = False

    while i < len(tokens):
        tok = tokens[i]

        # Intento de match de via compuesta (dos palabras): "av carrera"
        if i + 1 < len(tokens):
            par = tok + " " + tokens[i + 1]
            if par in _LOOKUP_VIA:
                estandar = _LOOKUP_VIA[par]
                resultado.append(estandar)
                if not primera_via_encontrada:
                    via_principal = estandar
                    primera_via_encontrada = True
                i += 2
                if numero_via is None and i < len(tokens):
                    m = re.match(r"^(\d+[a-z]?)$", tokens[i])
                    if m:
                        numero_via = m.group(1)
                continue

        # Match de via simple
        if tok in _LOOKUP_VIA:
            estandar = _LOOKUP_VIA[tok]
            resultado.append(estandar)
            if not primera_via_encontrada:
                via_principal = estandar
                primera_via_encontrada = True
            i += 1
            # capturar el numero de la via principal si sigue
            if numero_via is None and i < len(tokens):
                m = re.match(r"^(\d+[a-z]?)$", tokens[i])
                if m:
                    numero_via = m.group(1)
            continue

        # Match de complemento
        if tok in _LOOKUP_COMPLEMENTO:
            estandar_comp = _LOOKUP_COMPLEMENTO[tok]
            # Caso especial: direccional (Norte/Sur/Este/Oeste) justo despues
            # de una via SIN numero es parte del nombre (ej "Autopista Norte").
            direccionales = ("Norte", "Sur", "Este", "Oeste")
            if (estandar_comp in direccionales
                    and primera_via_encontrada
                    and numero_via is None
                    and len(resultado) > 0
                    and resultado[-1] in TIPOS_VIA):
                resultado.append(estandar_comp)
                i += 1
                continue
            resultado.append(estandar_comp)
            i += 1
            continue

        # Token normal (numero, letra, nombre): capitalizar si es palabra
        if re.match(r"^[a-z]+$", tok) and len(tok) > 2:
            resultado.append(tok.capitalize())
        else:
            resultado.append(tok.upper() if len(tok) <= 2 and tok.isalpha() else tok)
        i += 1

    normalizada = " ".join(resultado)
    # Reafinar el "#" con espacios correctos
    normalizada = re.sub(r"\s*#\s*", " # ", normalizada).strip()
    normalizada = re.sub(r"\s+", " ", normalizada)

    # 6. Construir query para el geocoder
    query = normalizada
    if ciudad:
        query = f"{normalizada}, {ciudad}, Colombia"
    else:
        query = f"{normalizada}, Colombia"

    return {
        "original": original,
        "normalizada": normalizada,
        "via_principal": via_principal,
        "numero_via": numero_via,
        "query_geocoder": query,
    }


def es_codigo_dane(texto):
    """
    Determina si un input es un codigo DANE (5 digitos = municipio,
    o 8 digitos = centro poblado) en lugar de una direccion.
    """
    if not texto:
        return False
    limpio = texto.strip()
    return bool(re.fullmatch(r"\d{5}|\d{8}", limpio))


# --- Pruebas rapidas ---
if __name__ == "__main__":
    casos = [
        "cll 10 # 5-30",
        "CL 10 No 5 - 30 apto 201",
        "calle 10 numero 5-30",
        "cra 7 # 45-10 torre 3 apto 502",
        "Kr 7 45 10",
        "av carrera 68 # 40-55 sur",
        "diag 25 g # 5-30",
        "transv 93 # 53-48 int 2",
        "AUTOPISTA NORTE # 100-50",
        "cll 100 #15-20 of 301, Bogota",
        "mz 5 casa 12 barrio kennedy",
        "carrera 15 no. 93-60 piso 4",
        "11001",           # codigo DANE Bogota
        "05001",           # codigo DANE Medellin
    ]

    print("=" * 70)
    print("  PRUEBAS DEL NORMALIZADOR DE DIRECCIONES")
    print("=" * 70)
    for c in casos:
        if es_codigo_dane(c):
            print(f"\n  INPUT:  {c}")
            print(f"  TIPO:   Codigo DANE (no es direccion)")
            continue
        r = normalizar_direccion(c, ciudad="Bogota")
        print(f"\n  INPUT:  {c}")
        print(f"  NORM:   {r['normalizada']}")
        print(f"  VIA:    {r['via_principal']} {r['numero_via'] or ''}")
        print(f"  QUERY:  {r['query_geocoder']}")
