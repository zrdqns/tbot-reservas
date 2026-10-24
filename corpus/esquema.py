"""Esquema del corpus: intenciones, ranuras, tokenizador y formato de anotación.

Un mensaje anotado se escribe como en MASSIVE, con cada ranura entre corchetes:

    quiero un [servicio : corte] con [barbero : Camilo] [fecha : mañana] [hora : a las 3]
"""
import re

INTENCIONES = [
    "reservar", "reprogramar", "cancelar",
    "consultar_disponibilidad", "consultar_servicios", "consultar_citas",
    "afirmar", "negar", "fuera_de_alcance",
]
RANURAS = ["servicio", "barbero", "fecha", "hora", "franja", "nombre"]
ETIQUETAS = ["O"] + [f"{p}-{r}" for r in RANURAS for p in ("B", "I")]

SIN_RANURAS = {"afirmar", "negar", "fuera_de_alcance"}

# Palabras que no pueden abrir un tramo (ver guia_anotacion.md)
_NO_ABRE = {
    "servicio": {"un", "una", "unos", "unas", "el", "la", "los", "las", "para", "de", "del", "me", "por"},
    "barbero": {"con", "don", "doña", "al", "del", "de", "la", "los", "las", "barbero"},
    "nombre": {"de", "don", "doña", "soy", "a", "el", "la", "para"},
    "fecha": {"para", "pa", "pal", "de", "del", "al", "desde", "hasta", "a"},
    "hora": {"para", "pa", "de", "desde", "hasta", "del"},
    "franja": {"para", "pa", "del"},
}

_DETALLE = r"^(el|la|las|un) (\d|punt|nuca|lados|l[ií]nea|raya|contorno|cerquillo|patillas)"

_TOKEN = re.compile(r"\d+[:/.]\d+(?:[:/.]\d+)?|[ap]\.\s?m\.|\w+|[^\w\s]", re.I)
_RANURA = re.compile(r"\[(\w+) : ([^\[\]]+)\]")


def tokenizar(texto):
    """Devuelve [(token, inicio, fin)]. Horas (3:30) y fechas (15/10) quedan en un solo token."""
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(texto)]


def leer_anotado(anotado):
    """'un [servicio : corte] [fecha : mañana]' -> ('un corte mañana', [ranuras con posiciones])."""
    texto, ranuras, pos = "", [], 0
    for m in _RANURA.finditer(anotado):
        texto += anotado[pos:m.start()]
        inicio = len(texto)
        texto += m.group(2)
        ranuras.append({"tipo": m.group(1), "valor": m.group(2), "inicio": inicio, "fin": len(texto)})
        pos = m.end()
    return texto + anotado[pos:], ranuras


def a_bio(texto, ranuras):
    """Tokens y etiquetas BIO. Falla si una ranura no coincide con los límites de los tokens."""
    tokens = tokenizar(texto)
    etiquetas = ["O"] * len(tokens)
    for r in ranuras:
        dentro = [i for i, (_, a, b) in enumerate(tokens) if a >= r["inicio"] and b <= r["fin"]]
        if not dentro or tokens[dentro[0]][1] != r["inicio"] or tokens[dentro[-1]][2] != r["fin"]:
            raise ValueError(f"la ranura «{r['valor']}» no coincide con los tokens de «{texto}»")
        etiquetas[dentro[0]] = "B-" + r["tipo"]
        for i in dentro[1:]:
            etiquetas[i] = "I-" + r["tipo"]
    return [t for t, _, _ in tokens], etiquetas


def ejemplo(intencion, anotado):
    """Arma el registro del corpus a partir de la intención y el mensaje anotado."""
    texto, ranuras = leer_anotado(anotado)
    tokens, etiquetas = a_bio(texto, ranuras)
    return {"texto": texto, "intencion": intencion, "ranuras": ranuras, "tokens": tokens, "etiquetas": etiquetas}


def revisar(ej):
    """Lista de problemas de un registro frente a la guía de anotación (vacía si está bien)."""
    problemas = []
    texto = ej["texto"]
    if ej["intencion"] not in INTENCIONES:
        problemas.append(f"intención desconocida: {ej['intencion']}")
    if not texto.strip() or texto != texto.strip() or "  " in texto:
        problemas.append("espacios sobrantes o texto vacío")
    if "[" in texto or "]" in texto or " : " in texto:
        problemas.append("anotación mal formada")
    if ej["intencion"] in SIN_RANURAS and ej["ranuras"]:
        problemas.append(f"{ej['intencion']} no lleva ranuras")
    fin_anterior = 0
    for r in ej["ranuras"]:
        if r["tipo"] not in RANURAS:
            problemas.append(f"ranura desconocida: {r['tipo']}")
            continue
        valor = r["valor"]
        if valor != valor.strip() or not valor[0].isalnum() or valor[-1] in ",;:¿?¡!":
            problemas.append(f"límites de «{valor}»")
        primera = valor.split()[0].lower()
        descriptivo = r["tipo"] == "barbero" and valor.split()[0].lower() in {"el", "la"} and len(valor.split()) > 1
        # la descripción del corte va con su artículo: «el 7 con desvanecido», «las puntas», «la nuca y los lados»
        descriptivo |= r["tipo"] == "servicio" and bool(re.search(_DETALLE, valor.lower()))
        if primera in _NO_ABRE[r["tipo"]] and not descriptivo:
            problemas.append(f"«{valor}» ({r['tipo']}) no debe empezar con «{primera}»")
        if r["inicio"] < fin_anterior:
            problemas.append("ranuras solapadas")
        fin_anterior = r["fin"]
    return problemas
