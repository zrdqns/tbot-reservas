"""Normalizador de fechas y horas por reglas.

El clasificador marca qué palabras son una fecha, una hora o una franja; aquí se calcula su valor.
Las reglas parten de las de Duckling para español y añaden las expresiones del corpus («tipo tres»,
«a primera hora», «el otro sábado»). La fecha de referencia es la del mensaje.

    fecha("el otro sábado", date(2026, 10, 13))   -> Fecha(dia=date(2026, 10, 24))
    hora("tipo tres")                              -> Hora(hora=3, definida=False)
    franja("después de las 5")                     -> Franja(desde=time(17, 0))
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, time, timedelta
from difflib import get_close_matches

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
NUMEROS = {"una": 1, "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
           "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}
MINUTOS = {"media": 30, "cuarto": 15, "cinco": 5, "diez": 10, "veinte": 20, "veinticinco": 25, "cuarenta": 40}
# «el quince», «el dieciséis»: el día del mes escrito con letras
DIAS_MES = {**{p: n for p, n in NUMEROS.items() if p not in ("una", "un")}, "primero": 1, "trece": 13,
            "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
            "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
            "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
            "treinta": 30, "treinta y uno": 31}
ERRORES = {"savado": "sabado", "biernes": "viernes", "oy": "hoy", "mnn": "manana", "setiembre": "septiembre",
           "finde": "fin de semana", "korte": "corte", "kortes": "cortes", "kortar": "cortar", "barva": "barba",
           "kiero": "quiero", "kisiera": "quisiera"}

_DIA = "(" + "|".join(DIAS) + ")"
_MES = "(" + "|".join(MESES) + ")"
_NUM = "(" + "|".join(NUMEROS) + r"|\d{1,2})"
_OTRA_SEMANA = r"(otra|proxima|siguiente) semana|semana (que viene|entrante|siguiente|proxima)"


@dataclass
class Fecha:
    dia: date | None = None        # un día concreto, o el primero de un intervalo
    hasta: date | None = None      # último día, si es una semana o un fin de semana
    habitual: str | None = None    # «domingo», «festivos»: una pregunta general, sin día


@dataclass
class Hora:
    hora: int | None = None
    minuto: int = 0
    definida: bool = False         # False: «a las 3» puede ser de la mañana o de la tarde
    especial: str | None = None    # «primera» o «ultima» hora del día
    en_minutos: int | None = None  # «ahorita» = 0, «en media hora» = 30


@dataclass
class Franja:
    desde: time | None = None
    hasta: time | None = None
    hoy: bool = False              # «esta tarde»


def limpiar(texto):
    """Minúsculas, sin tildes y con los errores de escritura más comunes corregidos."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w:/.+\s-]", " ", t)
    palabras = []
    for p in t.split():
        p = ERRORES.get(p, p)
        if len(p) >= 5 and p.isalpha() and p not in DIAS + MESES + ["sabados", "domingos"]:
            parecidas = get_close_matches(p, DIAS + MESES + ["manana", "mediodia", "temprano"], n=1, cutoff=0.8)
            # «viene» se parece a «viernes»: solo se corrige si sobra o falta una letra como mucho
            p = parecidas[0] if parecidas and abs(len(parecidas[0]) - len(p)) <= 1 else p
        palabras.append(p)
    return re.sub(r"medio dia", "mediodia", " ".join(palabras))


# --------------------------------------------------------------------------- fechas

def _proximo(hoy, dia_semana, minimo=1):
    """La próxima fecha que cae en ese día de la semana. Con minimo=0 puede ser hoy."""
    faltan = (dia_semana - hoy.weekday()) % 7
    return hoy + timedelta(days=faltan if faltan >= minimo else faltan + 7)


def _dia_mes(hoy, dia, mes):
    for anio in (hoy.year, hoy.year + 1):
        try:
            if date(anio, mes, dia) >= hoy:
                return date(anio, mes, dia)
        except ValueError:
            return None


def _dia_del_mes(hoy, dia):
    """«El 15»: el de este mes si no ha pasado; si no, el del siguiente."""
    for mes in (hoy.month, hoy.month % 12 + 1):
        anio = hoy.year + (mes < hoy.month)
        try:
            if date(anio, mes, dia) >= hoy:
                return date(anio, mes, dia)
        except ValueError:
            pass


def fecha(texto, hoy):
    """Valor de un tramo de fecha frente al día del mensaje, o None si no se reconoce."""
    s = limpiar(texto)
    lunes = hoy - timedelta(days=hoy.weekday())

    # modismos: «en ocho días» es una semana y «en quince», dos; «el sábado en ocho» es una semana después del sábado
    if m := re.search(rf"\b(?:en|dentro de) (quince|{_NUM[1:-1]}) dias?\b", s):
        cantidad = 15 if m.group(1) == "quince" else NUMEROS.get(m.group(1)) or int(m.group(1))
        return Fecha(hoy + timedelta(days={8: 7, 15: 14}.get(cantidad, cantidad)))
    if m := re.search(rf"\b(?:en|dentro de) {_NUM} semanas?\b", s):
        return Fecha(hoy + timedelta(days=7 * (NUMEROS.get(m.group(1)) or int(m.group(1)))))
    if m := re.fullmatch(r"(?:de\s+)?(.+?)\s+en (ocho|quince)", s):
        base = fecha(m.group(1), hoy)
        if base and base.dia and not base.hasta:
            return Fecha(base.dia + timedelta(days=7 if m.group(2) == "ocho" else 14))

    if m := re.search(r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})\b", s):
        return _fecha(_dia_mes(hoy, int(m.group(1)), int(m.group(2))))
    if m := re.search(rf"\b(\d{{1,2}}|primero|1ro)\s+de\s+{_MES}", s):
        dia = 1 if not m.group(1).isdigit() else int(m.group(1))
        return _fecha(_dia_mes(hoy, dia, MESES.index(m.group(2)) + 1))
    if "pasado manana" in s:
        return Fecha(hoy + timedelta(days=2))
    # días que ya pasaron: el agente le dice al cliente que no se puede
    if re.search(r"\b(anteayer|antier|antes de ayer)\b", s):
        return Fecha(hoy - timedelta(days=2))
    if re.search(r"\bayer\b", s):
        return Fecha(hoy - timedelta(days=1))
    if re.search(r"\bmanana\b", s):
        return Fecha(hoy + timedelta(days=1))
    if re.search(r"\bhoy\b", s):
        return Fecha(hoy)

    # preguntas generales: «los domingos», «los festivos»
    if m := re.search(rf"\blos\s+{_DIA}s?\b|\b(sabado|domingo)s\b", s):
        return Fecha(habitual=m.group(1) or m.group(2))
    if m := re.search(r"\b(festivos|entre semana|fines de semana)\b", s):
        return Fecha(habitual=m.group(1))

    if m := re.search(_DIA, s):
        numero = re.search(rf"{_DIA}\s+(\d{{1,2}})\b", s)
        if numero:
            return _fecha(_dia_del_mes(hoy, int(numero.group(2))))
        dia_semana = DIAS.index(m.group(1))
        if re.search(_OTRA_SEMANA, s):
            return Fecha(lunes + timedelta(days=7 + dia_semana))
        if "esta semana" in s:
            return Fecha(lunes + timedelta(days=dia_semana))
        if re.search(rf"\botro\s+{_DIA}", s):
            return Fecha(_proximo(hoy, dia_semana) + timedelta(days=7))
        return Fecha(_proximo(hoy, dia_semana, 0 if re.search(r"\beste\b", s) else 1))

    if "fin de semana" in s:
        sabado = _proximo(hoy, 5, 0)
        return Fecha(hoy, hoy) if hoy.weekday() == 6 else Fecha(sabado, sabado + timedelta(days=1))
    if "esta semana" in s:
        return Fecha(hoy, lunes + timedelta(days=6))
    if re.search(_OTRA_SEMANA, s):
        return Fecha(lunes + timedelta(days=7), lunes + timedelta(days=13))
    palabras = "|".join(sorted(DIAS_MES, key=len, reverse=True))
    if m := re.fullmatch(rf"(?:(?:para )?el\s+)?(?:dia\s+)?(\d{{1,2}}|{palabras})(?:\s+de este mes)?", s):
        return _fecha(_dia_del_mes(hoy, int(m.group(1)) if m.group(1).isdigit() else DIAS_MES[m.group(1)]))
    return None


def _fecha(dia):
    return Fecha(dia) if dia else None


# --------------------------------------------------------------------------- horas

def hora(texto):
    """Valor de un tramo de hora, o None. No decide entre mañana y tarde: eso lo hace `lecturas`."""
    s = limpiar(texto)
    if re.search(r"\bdias\b|\bsemanas?\b|\bmes(es)?\b|\bdentro de\b", s):
        return None                        # «dentro de 15 días» es una fecha aunque el clasificador la marque como hora
    if re.search(r"\bentre\b|\bdesde\b|\bdespues de\b|\bantes de\b|\ba partir de\b", s):
        return None                        # «entre las 3 y las 4» es una franja
    if "mediodia" in s:
        return Hora(12, 0, True)
    if "primera hora" in s:
        return Hora(especial="primera")
    if "ultima hora" in s:
        return Hora(especial="ultima")
    if re.search(r"\b(ahorita|ahora|ya mismo|este momento)\b", s):
        return Hora(en_minutos=0)
    if "media hora" in s and "en" in s.split():
        return Hora(en_minutos=30)
    if re.search(r"\ben hora y media\b", s):
        return Hora(en_minutos=90)
    # «un cuarto para las 4», «faltando diez para las cinco»
    if m := re.search(rf"\b(cuarto|{_NUM[1:-1]})\s+para\s+las?\s+{_NUM}", s):
        faltan = 15 if m.group(1) == "cuarto" else NUMEROS.get(m.group(1)) or int(m.group(1))
        h = NUMEROS.get(m.group(2)) or int(m.group(2))
        return Hora(h - 1 or 12, 60 - faltan) if 0 < faltan < 60 and 1 <= h <= 12 else None
    if m := re.search(rf"\ben {_NUM}\s*(hora|min)", s):
        cantidad = NUMEROS.get(m.group(1)) or int(m.group(1))
        return Hora(en_minutos=cantidad * (60 if m.group(2) == "hora" else 1) + (30 if "y media" in s else 0))

    # «0930», «1530»: hora y minutos pegados
    if m := re.search(r"\b([01]?\d|2[0-3])([0-5]\d)\s*(h|hrs?|horas)?\b", s):
        if len(m.group(1) + m.group(2)) >= 3:
            s = s[:m.start()] + f"{int(m.group(1))}:{m.group(2)}" + s[m.end(2):]
    m = re.search(rf"\b{_NUM}(?:\s*[:.h]\s*(\d{{2}}))?", s)
    if not m:
        return None
    h = NUMEROS.get(m.group(1)) or int(m.group(1))
    minuto = int(m.group(2) or 0)
    resto = s[m.end():]
    if fraccion := re.match(rf"\s*y\s+({'|'.join(MINUTOS)}|\d{{1,2}})\b", resto):
        minuto = MINUTOS.get(fraccion.group(1)) or int(fraccion.group(1))
    elif re.match(r"\s*menos cuarto", resto):
        h, minuto = h - 1 or 12, 45
    if h > 23 or minuto > 59:
        return None

    tarde = re.search(r"p\.?\s?m\b|de la (tarde|noche)", resto)
    manana = re.search(r"a\.?\s?m\b|de la manana", resto)
    if tarde and h < 12:
        return Hora(h + 12, minuto, True)
    if manana:
        return Hora(h % 12, minuto, True)
    return Hora(h, minuto, definida=h >= 12 or h == 0)


def lecturas(h):
    """Las horas de reloj que puede significar una Hora: una si está definida, dos si no."""
    if h.hora is None:
        return []
    if h.definida:
        return [time(h.hora, h.minuto)]
    return [time(h.hora, h.minuto), time(h.hora + 12, h.minuto)]


def en_horario(h, apertura, cierre, fr=None):
    """Lecturas de una Hora que caen dentro del horario de atención y, si la hay, de la franja."""
    def cabe(t):
        return apertura <= t < cierre and (fr is None or dentro(t, fr))
    return [t for t in lecturas(h) if cabe(t)]


def resolver(h, apertura, cierre, fr=None):
    """Qué hora quiso decir el cliente: (las lecturas dentro del horario, la lectura que cae fuera de él).

    La franja solo sirve para escoger entre la mañana y la tarde: «en la madrugada a las 4» son las 4:00 a. m.
    Si la hora ya trae a. m. o p. m., manda la hora: «en la madrugada a las 9:52 a. m.» son las 9:52 a. m.
    La segunda parte es None si alguna lectura cabe o si no se sabe cuál de las dos quiso.
    """
    todas = lecturas(h)
    if fr is not None and len(todas) == 2:
        en_franja = [t for t in todas if dentro(t, fr)]
        todas = en_franja if len(en_franja) == 1 else todas
    abiertas = [t for t in todas if apertura <= t < cierre]
    return abiertas, (todas[0] if not abiertas and len(todas) == 1 else None)


def dentro(t, fr):
    """Un turno está en la franja si empieza dentro de ella: el de las 12:00 ya no es «en la mañana»."""
    return (fr.desde is None or t >= fr.desde) and (fr.hasta is None or t < fr.hasta)


# --------------------------------------------------------------------------- franjas

def _limite(texto, apertura, cierre):
    """Hora que cierra o abre un intervalo: «las 5» es de la tarde si a las 5 a. m. no se atiende."""
    if "mediodia" in texto:
        return time(12)
    if "almuerzo" in texto:
        return None
    h = hora(texto)
    if not h or h.hora is None:
        return None
    return ([t for t in lecturas(h) if apertura <= t <= cierre] or lecturas(h))[-1]


def franja(texto, apertura=time(9), cierre=time(19)):
    """Valor de un tramo de franja del día, o None."""
    s = limpiar(texto)
    hoy = bool(re.search(r"\best[ae]\b", s))
    if "madrugad" in s:                     # antes de abrir: el agente ofrece los primeros turnos del día
        return Franja(hasta=time(6), hoy=hoy)
    if "hora del almuerzo" in s:
        return Franja(time(12), time(14), hoy)
    if m := re.search(r"entre (?:las? )?(.+?) y (?:las? )?(.+)", s):
        return Franja(_limite(m.group(1), apertura, cierre), _limite(m.group(2), apertura, cierre), hoy)
    if m := re.fullmatch(r"de (?:las? )?(.+?) a (?:las? )?(.+)", s):
        return Franja(_limite(m.group(1), apertura, cierre), _limite(m.group(2), apertura, cierre), hoy)
    if m := re.search(r"(despues|a partir|luego|pasad[oa]s?) (?:del?|el|las?) (.+)", s):
        return Franja(desde=time(14) if "almuerzo" in s else _limite(m.group(2), apertura, cierre), hoy=hoy)
    if m := re.search(r"antes del? (.+)", s):
        return Franja(hasta=time(12) if "almuerzo" in s else _limite(m.group(1), apertura, cierre), hoy=hoy)
    if "media manana" in s:
        return Franja(time(10), time(11, 30), hoy)
    if "media tarde" in s:
        return Franja(time(15), time(16, 30), hoy)
    if "final de la tarde" in s:
        return Franja(desde=time(17), hoy=hoy)
    if "tempran" in s:
        return Franja(hasta=time(10, 30), hoy=hoy)
    if re.search(r"\bmanan", s):
        return Franja(hasta=time(12), hoy=hoy)
    if "tarde" in s:
        return Franja(time(12), time(18), hoy)
    if "noche" in s:
        return Franja(desde=time(18), hoy=hoy)
    return None
