"""Conversación con el agente desde la consola, sin Telegram.

    py -m bot.consola

Habla con la API real de la barbería. Los botones salen numerados: se tocan escribiendo #1, #2...
/contacto 3001234567 simula el botón «Compartir mi número». Los demás comandos son los del bot.
"""
from datetime import datetime

from . import config
from .agente import Agente
from .barberia import Barberia
from .comprension import entender
from .perfiles import Perfiles
from .herramientas import Herramientas
from .respaldo import interpretar


def main():
    herramientas = Herramientas()
    print("Servidores MCP conectados." if herramientas.iniciar() else "Sin servidores MCP: el LLM va sin herramientas.")
    agente, yo, botones = Agente(Barberia(), entender, Perfiles(),
                                 respaldo=lambda t, c="": interpretar(t, c, herramientas)), 1, []
    if not agente.api.leer_horario():
        print("api-citas no respondió: uso el horario de config.py.")
    print("Escribe como un cliente. Línea vacía para salir.")
    while linea := input("\n> ").strip():
        ahora = datetime.now(config.ZONA).replace(tzinfo=None)
        if linea.startswith("#") and linea[1:].isdigit() and int(linea[1:]) <= len(botones):
            respuestas = agente.boton(yo, "Cliente de consola", botones[int(linea[1:]) - 1], ahora)
        elif linea.startswith("/contacto"):
            respuestas = agente.contacto(yo, "Cliente de consola", linea.partition(" ")[2], ahora)
        elif linea.startswith("/"):
            respuestas = agente.comando(yo, "Cliente de consola", linea[1:], ahora)
        else:
            respuestas = agente.texto(yo, "Cliente de consola", linea, ahora)
        for r in respuestas:
            print(r.texto)
            botones = [dato for fila in r.botones for _, dato in fila]
            for i, (texto, _) in enumerate((b for fila in r.botones for b in fila), 1):
                print(f"   #{i} [{texto}]")
            if r.pedir_contacto:
                print("   [Compartir mi número]  ->  /contacto 3001234567")


if __name__ == "__main__":
    main()
