"""Servidor MCP «calendario»: la fecha de hoy en Colombia y las reglas de fechas y horas del agente.

    python -m bot.servidores.calendario_mcp

Es el mismo normalizador que usa el agente (bot/fechas.py). Los modelos de lenguaje se equivocan con el calendario
(«el domingo» les sale sábado); con esta herramienta el LLM pregunta en vez de calcular.
"""
from datetime import timedelta

from mcp.server import MCPServer

from .. import config, fechas
from .barberia_mcp import DIAS, ahora_colombia


def _dia(d):
    return {"fecha": d.isoformat(), "dia": DIAS[d.weekday()], "abre": d.weekday() in config.HORARIO}


def crear(reloj=ahora_colombia):
    mcp = MCPServer("calendario", instructions="Fecha y hora actuales en Colombia y lectura de fechas y horas dichas "
                                               "con palabras. Usa estas herramientas en vez de calcular fechas.")

    @mcp.tool()
    def hoy() -> dict:
        """La fecha, el día de la semana y la hora actuales en Colombia."""
        ahora = reloj()
        return {**_dia(ahora.date()), "hora": f"{ahora:%H:%M}", "manana": _dia(ahora.date() + timedelta(days=1))}

    @mcp.tool()
    def fecha(expresion: str) -> dict:
        """Convierte una fecha dicha con palabras («mañana», «el viernes», «el 16», «en ocho días», «la otra semana»)
        en el día exacto, contando desde hoy en Colombia."""
        valor = fechas.fecha(expresion, reloj().date())
        if valor is None:
            return {"expresion": expresion, "error": "No reconozco esa fecha."}
        if valor.habitual:
            return {"expresion": expresion, "pregunta_general_por": valor.habitual}
        if valor.hasta:
            return {"expresion": expresion, "desde": _dia(valor.dia), "hasta": _dia(valor.hasta)}
        return {"expresion": expresion, **_dia(valor.dia)}

    @mcp.tool()
    def hora(expresion: str) -> dict:
        """Convierte una hora dicha con palabras («tipo 3», «a las 4 de la tarde», «a mediodía») en hora de reloj de
        24 horas. Si no dice mañana o tarde, se toma la lectura que cae en el horario de atención."""
        valor = fechas.hora(expresion)
        if valor is None:
            return {"expresion": expresion, "error": "No reconozco esa hora."}
        if valor.especial:
            return {"expresion": expresion, "hora": "la primera del día" if valor.especial == "primera" else "la última del día"}
        if valor.en_minutos is not None:
            return {"expresion": expresion, "hora": f"{reloj() + timedelta(minutes=valor.en_minutos):%H:%M}"}
        apertura = min(a for a, _ in config.HORARIO.values())
        cierre = max(c for _, c in config.HORARIO.values())
        dentro, fuera = fechas.resolver(valor, apertura, cierre)
        if dentro:
            return {"expresion": expresion, "horas": [f"{t:%H:%M}" for t in dentro]}
        return {"expresion": expresion, "fuera_de_horario": f"{fuera:%H:%M}" if fuera else None,
                "horario": f"{apertura:%H:%M}-{cierre:%H:%M}"}

    return mcp


if __name__ == "__main__":
    crear().run()
