"""Configuración del agente: direcciones de la API, horario de la barbería y umbral de confianza."""
import os
import sys
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).parent.parent
DATOS = Path(__file__).parent / "datos"      # perfiles y registro de mensajes; no se comparte

# Sistema de gestión de la barbería (proyecto barberia-microservicios). En Vercel llegan por variables de entorno.
API_CITAS = os.environ.get("API_CITAS_URL", "http://localhost:8080")          # clientes y citas
API_CATALOGO = os.environ.get("API_CATALOGO_URL", "http://localhost:8081")    # servicios y barberos
# Segundos que se espera cada respuesta. En Vercel un microservicio sin uso se apaga a los cinco minutos y
# tarda unos segundos en volver (más si a su vez despierta al otro), así que se le da margen.
ESPERA_API = 60

ZONA = ZoneInfo("America/Bogota")

# Horario de atención por día de la semana (0 = lunes). Lo guarda api-citas (GET /api/horario) y el bot lo
# lee al arrancar y cada media hora con Barberia.leer_horario; este es el que usa mientras la API no responde.
# El domingo no se atiende.
HORARIO = {dia: (time(9), time(19)) for dia in range(6)}
PASO = 30                                    # minutos entre un turno y el siguiente
UMBRAL = 0.95                                # confianza mínima para aceptar lo que dice el clasificador
TELEFONO = "310 456 7890"                    # a dónde remitir cuando el agente no puede ayudar


def leer_env(clave, obligatoria=True):
    """Una clave de las variables de entorno (así llegan en Vercel) o, si no está, del archivo .env local."""
    if os.environ.get(clave):
        return os.environ[clave]
    archivo = RAIZ / ".env"
    for linea in archivo.read_text(encoding="utf-8").splitlines() if archivo.exists() else []:
        nombre, _, valor = linea.partition("=")
        if nombre.strip() == clave:
            return valor.strip()
    if obligatoria:
        sys.exit(f"Falta {clave} en .env")
    return ""
