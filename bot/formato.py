"""Cómo escribe el agente las fechas, las horas, los precios y las citas."""
from datetime import timedelta

from . import config
from .barberia import inicio

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def dia(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def dia_corto(d, hoy):
    if d == hoy:
        return "Hoy"
    if d == hoy + timedelta(days=1):
        return "Mañana"
    return f"{DIAS[d.weekday()][:3]} {d.day}"


def hora(t):
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'a. m.' if t.hour < 12 else 'p. m.'}"


def las(t, corta=False):
    """La hora con su artículo: «las 3:00 p. m.», pero «la 1:00 p. m.». Corta: sin a. m. ni p. m."""
    texto = hora(t)[:-6] if corta else hora(t)
    return ("la " if t.hour % 12 == 1 else "las ") + texto


def precio(valor):
    return "$" + f"{valor:,}".replace(",", ".")


def pila(nombre):
    return nombre.split()[0]


def cita(c):
    """Una cita tal como la devuelve la API: «Corte clásico con Andrés / miércoles 14 de octubre, 3:00 p. m.»."""
    cuando = inicio(c)
    return f"{c['servicioNombre']} con {pila(c['barberoNombre'])}\n{dia(cuando.date())}, {hora(cuando.time())}"


def cita_corta(c):
    cuando = inicio(c)
    return f"{DIAS[cuando.weekday()][:3]} {cuando.day} · {hora(cuando.time())} · {c['servicioNombre']}"


def horario(dia_semana=None):
    """El horario de un día de la semana, o el de toda la semana."""
    if dia_semana is not None:
        abre = config.HORARIO.get(dia_semana)
        plural = DIAS[dia_semana] if DIAS[dia_semana].endswith("s") else DIAS[dia_semana] + "s"
        if not abre:
            return f"Los {plural} no atendemos 😕"
        return f"Los {plural} atendemos de {hora(abre[0])} a {hora(abre[1])}"
    abiertos = sorted(config.HORARIO)
    if len(set(config.HORARIO.values())) == 1 and abiertos == list(range(abiertos[0], abiertos[-1] + 1)):
        abre = config.HORARIO[abiertos[0]]
        cerrados = [DIAS[d] + "s" for d in range(7) if d not in config.HORARIO]
        texto = f"Atendemos de {DIAS[abiertos[0]]} a {DIAS[abiertos[-1]]}, de {hora(abre[0])} a {hora(abre[1])}"
        return texto + (f" Los {' y '.join(cerrados)} descansamos." if cerrados else "")
    return "Atendemos:\n" + "\n".join(f"• {DIAS[d]}: {hora(a)} a {hora(c)}" for d, (a, c) in sorted(config.HORARIO.items()))
