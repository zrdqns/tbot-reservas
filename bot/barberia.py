"""Acceso al sistema de la barbería: su API REST, el catálogo y los turnos libres.

El agente usa las mismas operaciones que la interfaz web: consultar servicios y barberos (api-catalogo),
y consultar, crear, modificar y cancelar citas (api-citas).
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, time, timedelta
from difflib import get_close_matches

from . import config
from .fechas import limpiar

SIN_CONEXION = "No pude comunicarme con la agenda de la barbería. Intenta de nuevo en un momento."


class ErrorAPI(Exception):
    """La API rechazó la operación. `mensaje` es el texto que devolvió, listo para mostrar al cliente."""

    def __init__(self, estado, mensaje):
        super().__init__(mensaje)
        self.estado, self.mensaje = estado, mensaje


class Barberia:
    def __init__(self, citas=config.API_CITAS, catalogo=config.API_CATALOGO):
        self.url_citas, self.url_catalogo = citas, catalogo

    def _pedir(self, metodo, url, datos=None):
        pedido = urllib.request.Request(
            url, method=metodo, data=None if datos is None else json.dumps(datos).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=config.ESPERA_API) as respuesta:
                return json.load(respuesta)
        except urllib.error.HTTPError as error:
            try:
                mensaje = json.load(error).get("mensaje", "")
            except ValueError:
                mensaje = ""
            raise ErrorAPI(error.code, mensaje or "La agenda rechazó la operación.") from None
        except (urllib.error.URLError, OSError):
            raise ErrorAPI(0, SIN_CONEXION) from None

    # catálogo
    def servicios(self):
        return self._pedir("GET", f"{self.url_catalogo}/api/servicios")

    def barberos(self):
        return self._pedir("GET", f"{self.url_catalogo}/api/barberos")

    # clientes
    def clientes(self):
        return self._pedir("GET", f"{self.url_citas}/api/clientes")

    def crear_cliente(self, nombre, documento, telefono):
        return self._pedir("POST", f"{self.url_citas}/api/clientes",
                           {"nombre": nombre, "documento": documento, "telefono": telefono, "correo": ""})

    # citas
    def citas(self):
        return self._pedir("GET", f"{self.url_citas}/api/citas")

    def crear_cita(self, cliente_id, servicio_id, barbero_id, cuando, observaciones=""):
        return self._pedir("POST", f"{self.url_citas}/api/citas",
                           _cita(cliente_id, servicio_id, barbero_id, cuando, observaciones))

    def mover_cita(self, cita_id, cliente_id, servicio_id, barbero_id, cuando, observaciones=""):
        return self._pedir("PUT", f"{self.url_citas}/api/citas/{cita_id}",
                           _cita(cliente_id, servicio_id, barbero_id, cuando, observaciones))

    def cancelar_cita(self, cita_id):
        return self._pedir("PATCH", f"{self.url_citas}/api/citas/{cita_id}/estado", {"estado": "CANCELADA"})

    # horario
    def leer_horario(self):
        """Pone en config.HORARIO el horario que guarda api-citas. Si no responde, se queda el que había."""
        try:
            dias = self._pedir("GET", f"{self.url_citas}/api/horario")
        except ErrorAPI:
            return False
        nuevo = {d["diaSemana"] - 1: (time.fromisoformat(d["apertura"]), time.fromisoformat(d["cierre"]))
                 for d in dias if d["abierto"]}
        config.HORARIO.clear()          # se cambia en el mismo diccionario: los demás módulos lo leen de ahí
        config.HORARIO.update(nuevo)
        return True


def _cita(cliente_id, servicio_id, barbero_id, cuando, observaciones):
    return {"clienteId": cliente_id, "servicioId": servicio_id, "barberoId": barbero_id,
            "fechaHora": cuando.strftime("%Y-%m-%dT%H:%M"), "observaciones": observaciones or ""}


def inicio(cita):
    return datetime.fromisoformat(cita["fechaHora"])


# --------------------------------------------------------------------------- catálogo

# Lo que el cliente dice y a qué servicio se refiere. Con dos conceptos («pelo y barba») se busca el combo.
CONCEPTOS = {"corte": r"cort|motil|peluq|pelo|cabello|degrad|fade|desvanec|taper|punt|despunt|rapad|rapar|"
                       r"\ba ras\b|tijera|maquina|cerquillo|mohican|rebaj|lados|costados|nuca|empareja|patilla|"
                       r"\braya\b|\bel \d\b|\btodo al \d|^\d\b|\bparejo\b",
             "barba": r"barb|afeit|perfil",
             "tinte": r"tint|pint|decolor|mecha|rayito"}
# Lo que describe cómo quiere el corte, más allá del nombre del servicio: va a las observaciones de la cita
DETALLE = (r"\d|punt|desvanec|degrad|fade|taper|lados|costados|arriba|abajo|nuca|\braya\b|linea|cerquillo|bajit|"
           r"\balto\b|rapad|\bras\b|tijera|maquina|mohican|crespo|rebaj|largo|empareja|patilla|contorno|parejo")
VACIAS = {"de", "la", "el", "un", "una", "con", "y", "para", "arreglo", "servicio"}
APODOS = {"pipe": "felipe", "juli": "julian", "sebas": "sebastian", "cami": "camilo", "santi": "santiago",
          "nico": "nicolas", "alejo": "alejandro", "dani": "daniel", "juancho": "juan", "mao": "mauricio",
          "migue": "miguel", "tavo": "gustavo", "lucho": "luis", "juanpa": "juan pablo", "juanda": "juan david",
          "cris": "cristian", "fer": "fernando", "leo": "leonardo", "memo": "guillermo", "pacho": "francisco",
          "chucho": "jesus", "beto": "alberto", "nacho": "ignacio", "rafa": "rafael", "kike": "enrique",
          "andresito": "andres"}
SIN_PREFERENCIA = (r"cualquier|el que (este|sea|haya|tenga|pueda)|quien (este|sea)|no importa|da igual|da lo mismo|"
                   r"como sea|ninguno en especial|no tengo preferencia|\bambos\b|los dos")
EL_DE_SIEMPRE = r"siempre|el mismo|lo mismo|otra vez|vez pasada"


def _conceptos(texto):
    s = limpiar(texto)
    return {concepto for concepto, patron in CONCEPTOS.items() if re.search(patron, s)}


def buscar_servicio(texto, servicios):
    """El servicio del catálogo al que se refiere el cliente, o None si la barbería no lo tiene."""
    activos_primero = sorted(servicios, key=lambda s: not s["activo"])
    buscados = _conceptos(texto)
    for servicio in activos_primero:
        if buscados and _conceptos(servicio["nombre"]) == buscados:
            return servicio
    # un servicio que alguien añadió al catálogo y no está entre los conceptos conocidos
    palabras = set(limpiar(texto).split()) - VACIAS
    for servicio in activos_primero:
        if not buscados and palabras & (set(limpiar(servicio["nombre"]).split()) - VACIAS):
            return servicio
    return None


def detalle(textos):
    """«solo las puntas, el 7 con desvanecido»: los tramos de servicio que dicen cómo quiere el corte."""
    return ", ".join(t.strip() for t in textos if re.search(DETALLE, limpiar(t)))


def buscar_barbero(texto, barberos):
    """El barbero del catálogo, «cualquiera», «habitual» o None si no se reconoce."""
    s = limpiar(texto)
    if re.search(SIN_PREFERENCIA, s):
        return "cualquiera"
    if re.search(EL_DE_SIEMPRE, s):
        return "habitual"
    s = APODOS.get(s, s)
    nombres = {limpiar(b["nombre"]): b for b in barberos}
    for nombre, barbero in nombres.items():
        if s == nombre or s in nombre.split() or (len(s) >= 3 and nombre.startswith(s)):
            return barbero
    parecidos = get_close_matches(s.split()[0] if s else "", [n.split()[0] for n in nombres], n=1, cutoff=0.8)
    return next((b for n, b in nombres.items() if parecidos and n.split()[0] == parecidos[0]), None)


# --------------------------------------------------------------------------- turnos

def libres_a(cuando, duracion, barberos, citas, ahora, excepto=None):
    """Barberos que pueden atender a esa hora: dentro del horario, sin haber pasado y sin cruce de citas."""
    horario = config.HORARIO.get(cuando.weekday())
    fin = cuando + timedelta(minutes=duracion)
    if not horario or cuando <= ahora or cuando.time() < horario[0] or fin.date() != cuando.date() \
            or fin.time() > horario[1]:
        return []
    ocupados = {c["barberoId"] for c in citas
                if c["estado"] == "PROGRAMADA" and c["id"] != excepto
                and cuando < inicio(c) + timedelta(minutes=c["duracionMinutos"]) and inicio(c) < fin}
    return [b for b in barberos if b["id"] not in ocupados]


def turnos(dia, duracion, barberos, citas, ahora, excepto=None):
    """{hora: barberos libres} para cada turno del día en que alguien puede atender."""
    horario = config.HORARIO.get(dia.weekday())
    if not horario:
        return {}
    salida, cuando = {}, datetime.combine(dia, horario[0])
    while cuando.time() < horario[1] and cuando.date() == dia:
        quienes = libres_a(cuando, duracion, barberos, citas, ahora, excepto)
        if quienes:
            salida[cuando.time()] = quienes
        cuando += timedelta(minutes=config.PASO)
    return salida
