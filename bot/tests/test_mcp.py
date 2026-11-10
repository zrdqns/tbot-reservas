"""Los dos servidores MCP (barbería y calendario), el cliente que los conecta y el LLM que los usa.

Los servidores se prueban dentro del mismo proceso y el LLM con respuestas grabadas: nada sale a la red.
"""
import json
from datetime import datetime

import pytest

from bot import respaldo
from bot.herramientas import Herramientas
from bot.servidores import barberia_mcp, calendario_mcp
from bot.tests.agenda_falsa import AgendaFalsa
from bot.tests.test_agente import AHORA, Chat, duda


@pytest.fixture(scope="module")
def herramientas():
    agenda = AgendaFalsa(AHORA)
    agenda.agendar(1, 1, 1, "2026-10-16T15:00")          # Andrés ocupado el viernes a las 3
    h = Herramientas({"barberia": barberia_mcp.crear(agenda, reloj=lambda: AHORA),
                      "calendario": calendario_mcp.crear(reloj=lambda: AHORA)})
    assert h.iniciar(espera=20), h.error
    yield h
    h.cerrar()


def llamar(h, nombre, **argumentos):
    return json.loads(h.llamar(nombre, argumentos))


def test_las_herramientas_de_los_dos_servidores(herramientas):
    nombres = {x["function"]["name"] for x in herramientas.lista}
    assert nombres == {"barberia__servicios", "barberia__barberos", "barberia__horario", "barberia__turnos_libres",
                       "calendario__hoy", "calendario__fecha", "calendario__hora"}
    # solo lectura: nada para crear, mover ni cancelar citas, ni para ver clientes
    assert not any(p in n for n in nombres for p in ("crear", "mover", "cancelar", "cliente", "cita"))


def test_catalogo_solo_lo_activo(herramientas):
    servicios = llamar(herramientas, "barberia__servicios")
    assert [s["nombre"] for s in servicios] == ["Corte clásico", "Arreglo de barba", "Corte y barba"]   # sin el tinte
    assert servicios[2]["precio"] == 38000 and servicios[2]["minutos"] == 50
    assert [b["nombre"] for b in llamar(herramientas, "barberia__barberos")] == ["Andrés Rojas", "Julián Mora"]
    assert llamar(herramientas, "barberia__horario")["domingo"] == "cerrado"


def test_turnos_libres_descuenta_las_citas(herramientas):
    viernes = llamar(herramientas, "barberia__turnos_libres", fecha="2026-10-16")
    assert viernes["dia"] == "viernes"
    assert "15:00" not in viernes["turnos_por_barbero"]["Andrés"] and "15:00" in viernes["turnos_por_barbero"]["Julián"]
    solo_julian = llamar(herramientas, "barberia__turnos_libres", fecha="2026-10-16", barbero="julian",
                         servicio="corte y barba")
    assert list(solo_julian["turnos_por_barbero"]) == ["Julián"] and solo_julian["servicio"] == "Corte y barba"
    assert "18:30" not in solo_julian["turnos_por_barbero"]["Julián"]         # 50 minutos no caben antes de las 7
    assert "nota" in llamar(herramientas, "barberia__turnos_libres", fecha="2026-10-18")    # domingo
    assert llamar(herramientas, "barberia__turnos_libres", fecha="el viernes")["fecha"] == "2026-10-16"   # en palabras
    assert llamar(herramientas, "barberia__turnos_libres", fecha="mañana")["fecha"] == "2026-10-14"
    assert "error" in llamar(herramientas, "barberia__turnos_libres", fecha="cuando pueda")


def test_calendario_con_las_reglas_del_agente(herramientas):
    assert llamar(herramientas, "calendario__hoy")["fecha"] == "2026-10-13"
    assert llamar(herramientas, "calendario__fecha", expresion="el viernes")["fecha"] == "2026-10-16"
    assert llamar(herramientas, "calendario__fecha", expresion="el domingo")["abre"] is False
    assert llamar(herramientas, "calendario__hora", expresion="tipo 3")["horas"] == ["15:00"]
    assert "error" in llamar(herramientas, "calendario__fecha", expresion="cuando pueda")


def test_lo_que_el_llm_manda_de_mas_no_rompe_la_llamada(herramientas):
    assert llamar(herramientas, "barberia__servicios", **{"": {}})            # gpt-oss a veces manda {"": {}}
    assert "error" in llamar(herramientas, "barberia__nada")
    assert "error" in llamar(herramientas, "otro__servicios")


# --------------------------------------------------------------------------- el LLM con las herramientas

def grabado(pasos, monkeypatch):
    """Sustituye la API de Groq por respuestas grabadas, en orden; guarda lo que se le mandó."""
    enviados = []

    def pedir(cuerpo, *_):
        enviados.append(cuerpo)
        paso = pasos.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return {"choices": [{"message": paso}]}
    monkeypatch.setattr(respaldo, "_pedir", pedir)
    monkeypatch.setattr(respaldo.config, "leer_env", lambda *a, **k: "clave")
    return enviados


def llamada(nombre, argumentos, i=1):
    return {"id": f"c{i}", "type": "function", "function": {"name": nombre, "arguments": json.dumps(argumentos)}}


def test_el_llm_consulta_y_contesta(herramientas, monkeypatch):
    enviados = grabado([
        {"content": "", "tool_calls": [llamada("barberia__servicios", {})]},
        {"content": "", "tool_calls": [llamada("responder", {"intencion": "consultar_servicios", "ranuras": [],
                                                              "respuesta": "El corte y barba vale $38.000."}, 2)]},
    ], monkeypatch)
    marco = respaldo.interpretar("cuánto me sale corte y barba?", "", herramientas)
    assert marco["respuesta"] == "El corte y barba vale $38.000."
    assert marco["herramientas"] == ["barberia__servicios"]
    # el resultado de la herramienta MCP volvió al LLM antes de la segunda vuelta
    devueltos = [m["content"] for m in enviados[1]["messages"] if m["role"] == "tool"]
    assert len(devueltos) == 1 and '"precio": 38000' in devueltos[0]
    assert {t["function"]["name"] for t in enviados[0]["tools"]} >= {"barberia__turnos_libres", "responder"}


def test_sin_consultar_no_hay_respuesta(herramientas, monkeypatch):
    grabado([{"content": "", "tool_calls": [llamada("responder", {"intencion": "consultar_servicios", "ranuras": [],
                                                                  "respuesta": "Vale $10.000."})]}], monkeypatch)
    assert "respuesta" not in respaldo.interpretar("cuánto vale?", "", herramientas)      # un precio inventado


def test_un_precio_que_no_salio_de_las_herramientas_se_descarta(herramientas, monkeypatch):
    # pasó en la evaluación: consultó los servicios (sin tinte) y aun así contestó con un precio inventado
    grabado([
        {"content": "", "tool_calls": [llamada("barberia__servicios", {})]},
        {"content": "", "tool_calls": [llamada("responder", {"intencion": "consultar_servicios", "ranuras": [],
                                                              "respuesta": "Sí, hacemos tinte por $45.000."}, 2)]},
    ], monkeypatch)
    assert "respuesta" not in respaldo.interpretar("¿hacen tinte?", "", herramientas)


@pytest.mark.parametrize("respuesta, vale", [
    ("El corte y barba vale $38.000.", True), ("Para los dos sale $50.000 en total.", True),
    ("Corte y barba para ti y tu hijo: 76.000 pesos.", True), ("La barba sale en 18 mil.", True),
    ("El tinte vale $45.000.", False), ("Te sale en 30 mil.", False), ("Abrimos a las 9:00 a. m.", True)])
def test_precios_respaldados(respuesta, vale):
    resultados = ['[{"nombre": "Corte clásico", "precio": 25000}, {"nombre": "Arreglo de barba", "precio": 18000}, '
                  '{"nombre": "Corte y barba", "precio": 38000}]']
    assert respaldo.precios_respaldados(respuesta, resultados) is vale


def test_nunca_dice_que_agendo(herramientas, monkeypatch):
    grabado([
        {"content": "", "tool_calls": [llamada("barberia__turnos_libres", {"fecha": "2026-10-16"})]},
        {"content": "", "tool_calls": [llamada("responder", {"intencion": "consultar_disponibilidad", "ranuras": [],
                                                              "respuesta": "Listo, te agendé el viernes."}, 2)]},
    ], monkeypatch)
    assert "respuesta" not in respaldo.interpretar("tienes el viernes?", "", herramientas)


def test_entrega_rechazada_por_groq(herramientas, monkeypatch):
    rechazo = {"error": {"code": "tool_use_failed", "failed_generation": json.dumps(
        {"name": "json", "arguments": {"intencion": "consultar_disponibilidad", "ranuras": [],
                                       "respuesta": "Los domingos no atendemos."}})}}
    grabado([{"content": "", "tool_calls": [llamada("barberia__horario", {})]},
             respaldo.SinRespuesta("HTTP 400", json.dumps(rechazo))], monkeypatch)
    marco = respaldo.interpretar("¿abren el domingo?", "", herramientas)
    assert marco["respuesta"] == "Los domingos no atendemos." and marco["herramientas"] == ["barberia__horario"]


def test_sin_herramientas_funciona_como_antes(monkeypatch):
    monkeypatch.setattr(respaldo, "chat", lambda *a, **k: ({"intencion": "reservar", "ranuras": []}, 0))
    monkeypatch.setattr(respaldo.config, "leer_env", lambda *a, **k: "clave")
    assert respaldo.interpretar("necesito un corte", "", Herramientas({}))["intencion"] == "reservar"


# --------------------------------------------------------------------------- en la conversación

def test_el_agente_contesta_con_lo_que_trajo_el_llm():
    chat = Chat(cliente_id=1)
    chat.agente.entender = duda
    chat.agente.respaldo = lambda texto, contexto: {
        "intencion": "consultar_disponibilidad", "confianza": 1.0, "ranuras": [], "herramientas": ["barberia__horario"],
        "respuesta": "No, los domingos estamos cerrados."}
    assert chat.digo("¿atienden el domingo?") == "No, los domingos estamos cerrados."
    assert chat.agenda.escrituras == 0


def test_una_consulta_abierta_pasa_al_llm_aunque_el_clasificador_este_seguro():
    chat, consultas = Chat(cliente_id=1), []
    chat.agente.respaldo = lambda texto, contexto: consultas.append(texto) or {
        "intencion": "consultar_servicios", "confianza": 1.0, "ranuras": [], "herramientas": ["barberia__servicios"],
        "respuesta": "El más barato es el arreglo de barba: $18.000."}
    assert chat.digo("¿cuál es el servicio más barato?") == "El más barato es el arreglo de barba: $18.000."
    assert "El corte clásico vale $25.000" in chat.digo("¿cuánto vale el corte?")    # la respuesta fija sigue igual
    assert consultas == ["¿cuál es el servicio más barato?"]


def test_si_el_llm_no_contesta_queda_la_respuesta_fija():
    chat = Chat(cliente_id=1)
    chat.agente.respaldo = lambda texto, contexto: None                     # Groq no responde
    assert "Arreglo de barba: $18.000" in chat.digo("¿cuál es el servicio más barato?")


def test_la_respuesta_no_interrumpe_la_reserva():
    chat = Chat(cliente_id=1)
    chat.digo("corte con Andrés mañana a las 3")                             # queda esperando la confirmación
    chat.agente.entender = duda
    chat.agente.respaldo = lambda texto, contexto: {
        "intencion": "consultar_servicios", "confianza": 1.0, "ranuras": [], "herramientas": ["barberia__servicios"],
        "respuesta": "La barba sola vale $18.000."}
    todo = chat.digo("y la barba sola cuánto vale?")
    assert "La barba sola vale $18.000." in todo and "¿Te la agendo así?" in todo
    assert chat.botones == ["ok", "cambiar"] and chat.citas == []
