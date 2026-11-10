"""Preguntas abiertas sobre la barbería: el LLM con los dos servidores MCP frente al mismo LLM sin herramientas.

    python -m evaluacion.preguntas_mcp

Los servidores corren en el mismo proceso, sobre la agenda de prueba con dos citas puestas, y el «ahora» es el martes
13 de octubre de 2026 a las 10:00 a. m., así que la respuesta correcta de cada pregunta se conoce. Una respuesta cuenta
como correcta si trae lo que debe traer y no trae lo que no debe. En tres preguntas lo correcto es no contestar: no
son de la barbería o piden agendar. Las respuestas del LLM se guardan en evaluacion/salidas_llm/preguntas_mcp.json.
"""
import json
import re
import statistics
import sys
import time
from pathlib import Path

from bot import respaldo
from bot.herramientas import Herramientas
from bot.servidores import barberia_mcp, calendario_mcp
from bot.tests.agenda_falsa import AgendaFalsa
from bot.tests.test_agente import AHORA

AQUI = Path(__file__).parent
SALIDA = AQUI / "salidas_llm" / "preguntas_mcp.json"

# (pregunta, patrones que deben estar, patrones que no deben estar); None = lo correcto es no contestar
PREGUNTAS = [
    ("¿cuánto vale el corte y barba?", [r"38"], [r"25\.?000", r"60"]),
    ("¿qué precio tiene arreglarme la barba?", [r"18"], []),
    ("¿hacen tinte?", [r"\bno\b"], [r"60\.?000"]),
    ("¿atienden el domingo?", [r"\bno\b|cerrad"], []),
    ("¿hasta qué hora abren el sábado?", [r"\b7(:00)?\s*p|\b19"], []),
    ("¿cuál de los barberos es el de barba?", [r"Juli[aá]n"], [r"Andr[eé]s"]),
    ("¿qué barberos hay?", [r"Andr[eé]s", r"Juli[aá]n"], [r"Felipe"]),
    ("¿Andrés tiene turno el viernes a las 3?", [r"\bno\b|ocupad"], []),
    ("¿Julián tiene turno el viernes a las 3?", [r"\bs[ií]\b|libre|disponible|tiene turno"], [r"\bno (tiene|hay|est)"]),
    ("¿cuánto me sale un corte para mí y otro para mi hijo?", [r"50"], []),
    ("¿cuánto se demora el corte y barba?", [r"50"], []),
    ("¿el 20 abren?", [r"\bs[ií]\b|abiert|atendemos|martes"], [r"\bno (abrimos|atendemos)|cerrad"]),
    ("¿mañana a qué hora abren?", [r"\b9"], []),
    ("¿hay turno pasado mañana en la tarde con Julián?", [r"Juli[aá]n"], [r"\bno (tiene|hay)"]),
    ("¿Felipe todavía trabaja ahí?", [r"\bno\b"], [r"Felipe (tiene|est[aá] disponible)"]),
    ("¿el 7 de diciembre abren?", [r"\bs[ií]\b|abiert|atendemos|lunes"], [r"cerrad"]),
    ("¿cuál es el servicio más barato?", [r"barba", r"18"], []),
    ("¿venden cera para el pelo?", None, []),
    ("¿dónde quedan?", None, [r"calle|carrera|cra\.?|#"]),
    ("¿me puedes agendar un corte el viernes?", None, []),
]

TIPOS = [("Servicios y precios", [0, 1, 2, 9, 10, 16]), ("Barberos", [5, 6, 14]), ("Horario y fechas", [3, 4, 11, 12, 15]),
         ("Turnos libres", [7, 8, 13]), ("No debe contestar", [17, 18, 19])]

SIN_HERRAMIENTAS = respaldo.ESQUEMA + """

Al final responde solo con JSON: {"intencion": "...", "ranuras": [{"tipo": "...", "valor": "..."}], "respuesta": ...}
«respuesta» es un mensaje corto para el cliente cuando el mensaje es una pregunta sobre la barbería (precios, \
servicios, barberos, horario o turnos libres); en cualquier otro caso es null."""


def agenda():
    a = AgendaFalsa(AHORA)
    a.agendar(1, 1, 1, "2026-10-16T15:00")        # Andrés, viernes 3:00 p. m.
    a.agendar(2, 3, 2, "2026-10-15T15:00")        # Julián, jueves 3:00 p. m. (50 minutos)
    return a


def correcta(respuesta, deben, no_deben):
    return bool(respuesta) and all(re.search(p, respuesta, re.I) for p in deben) \
        and not any(re.search(p, respuesta, re.I) for p in no_deben)


def preguntar(herramientas, salidas):
    """Pregunta lo que falte y guarda después de cada pregunta: si se interrumpe, sigue donde iba."""
    for i, (pregunta, _, _) in enumerate(PREGUNTAS, 1):
        if pregunta in salidas:
            continue
        usuario = f"Mensaje: {pregunta}"
        time.sleep(45)          # el plan gratuito de Groq da 8 000 tokens por minuto: se espera antes, no se mide
        t = time.time()
        try:
            con = respaldo.con_herramientas(pregunta, usuario, herramientas, espera=20, reintentos=6, tope_429=None)
        except respaldo.SinRespuesta as error:
            con = {"error": str(error)[:200]}
        t_con = time.time() - t
        try:
            crudo, _ = respaldo.chat(SIN_HERRAMIENTAS, usuario, espera=20, reintentos=6)
            sin = {"intencion": crudo.get("intencion"), "respuesta": crudo.get("respuesta")}
        except respaldo.SinRespuesta as error:
            sin = {"error": str(error)[:200]}
        salidas[pregunta] = {"con_mcp": con, "segundos": round(t_con, 2), "sin_mcp": sin}
        SALIDA.write_text(json.dumps(salidas, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {i}/{len(PREGUNTAS)} {pregunta} ({t_con:.1f} s)", file=sys.stderr)


def main():
    salidas = {} if "--de-nuevo" in sys.argv or not SALIDA.exists() else json.loads(SALIDA.read_text(encoding="utf-8"))
    if any(p not in salidas for p, _, _ in PREGUNTAS):
        h = Herramientas({"barberia": barberia_mcp.crear(agenda(), reloj=lambda: AHORA),
                          "calendario": calendario_mcp.crear(reloj=lambda: AHORA)})
        assert h.iniciar(espera=20), h.error
        preguntar(h, salidas)
        h.cerrar()

    bien_con = bien_sin = 0
    usadas, segundos, filas, aciertos = [], [], [], []
    for pregunta, deben, no_deben in PREGUNTAS:
        s = salidas[pregunta]
        r_con = s["con_mcp"].get("respuesta")
        r_sin = s["sin_mcp"].get("respuesta")
        ok_con = correcta(r_con, deben, no_deben) if deben is not None else not r_con
        ok_sin = correcta(r_sin, deben, no_deben) if deben is not None else not r_sin
        bien_con += ok_con
        bien_sin += ok_sin
        aciertos.append((ok_con, ok_sin))
        usadas.append(len(s["con_mcp"].get("herramientas", [])))
        segundos.append(s["segundos"])
        filas.append(f"| {pregunta} | {'✓' if ok_con else '✗'} | {'✓' if ok_sin else '✗'} | "
                     f"{', '.join(x.replace('__', '.') for x in s['con_mcp'].get('herramientas', [])) or '—'} |")
    n = len(PREGUNTAS)
    print(f"| Sistema | Correctas | Exactitud |\n|---|---|---|\n| LLM con los dos MCP | {bien_con}/{n} | {bien_con / n:.0%} |"
          f"\n| LLM sin herramientas | {bien_sin}/{n} | {bien_sin / n:.0%} |\n")
    print("| Tipo de pregunta | Preguntas | Con los dos MCP | Sin herramientas |\n|---|---|---|---|")
    for tipo, indices in TIPOS:
        print(f"| {tipo} | {len(indices)} | {sum(aciertos[i][0] for i in indices)} | {sum(aciertos[i][1] for i in indices)} |")
    print()
    print(f"Herramientas por pregunta: {statistics.mean(usadas):.1f} en promedio. Tiempo con MCP: "
          f"{statistics.median(segundos):.1f} s de mediana, {max(segundos):.1f} s la más lenta (incluye esperas por el "
          f"límite de tokens por minuto de Groq).\n")
    print("| Pregunta | Con MCP | Sin herramientas | Herramientas usadas |\n|---|---|---|---|\n" + "\n".join(filas))


if __name__ == "__main__":
    main()
