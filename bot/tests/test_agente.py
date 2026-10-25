"""Conversaciones completas contra una agenda en memoria, con el clasificador real.

Cada prueba mira cómo queda la agenda al final, que es lo que importa: ninguna cita creada, movida o
cancelada por error. El «ahora» es el martes 13 de octubre de 2026 a las 10:00 a. m.
"""
from datetime import date, datetime, time

import pytest

from bot import formato as f
from bot.agente import Agente
from bot.comprension import entender
from bot.perfiles import Perfiles
from bot.tests.agenda_falsa import AgendaFalsa

AHORA = datetime(2026, 10, 13, 10, 0)
YO = 77


class Chat:
    """Un cliente escribiéndole al agente."""

    def __init__(self, cliente_id=None):
        self.agenda = AgendaFalsa(AHORA)
        self.perfiles = Perfiles()
        self.perfiles.de(YO).update(acepta=True, cliente_id=cliente_id, nombre="Carlos Ramírez" if cliente_id else "")
        self.agente = Agente(self.agenda, entender, self.perfiles)
        self.ultima = None

    def _ver(self, respuestas):
        self.ultima = respuestas[-1]
        self.todo = "\n".join(r.texto for r in respuestas)
        return self.todo

    def digo(self, texto):
        return self._ver(self.agente.texto(YO, "Daniel Vanegas", texto, AHORA))

    def toco(self, dato):
        return self._ver(self.agente.boton(YO, "Daniel Vanegas", dato, AHORA))

    def comparto(self, telefono):
        return self._ver(self.agente.contacto(YO, "Daniel Vanegas", telefono, AHORA))

    @property
    def botones(self):
        return [dato for fila in self.ultima.botones for _, dato in fila]

    @property
    def citas(self):
        return [(c["clienteId"], c["servicioId"], c["barberoId"], c["fechaHora"][:16], c["estado"]) for c in self.agenda.citas()]


def test_el_ejemplo_del_informe():
    chat = Chat()
    resumen = chat.digo("¿Me agenda un corte con Andrés mañana tipo tres?")
    assert "Corte clásico con Andrés" in resumen and "miércoles 14 de octubre, 3:00 p. m." in resumen
    assert chat.botones == ["ok", "cambiar"]
    assert chat.citas == []                                   # todavía no ha confirmado

    chat.toco("ok")
    assert chat.ultima.pedir_contacto and chat.citas == []    # primera vez: falta saber quién es
    final = chat.comparto("+57 300 123 4567")
    assert "quedó agendada" in final and "Te espero." in final
    assert chat.citas == [(1, 1, 1, "2026-10-14T15:00", "PROGRAMADA")]


def test_sin_confirmar_no_se_escribe():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte con Julián el sábado a las 11")
    assert chat.botones == ["ok", "cambiar"]
    assert "no agendé nada" in chat.digo("no, mejor no")
    assert chat.agenda.escrituras == 0


def test_cliente_nuevo_se_registra_con_su_documento():
    chat = Chat()
    chat.digo("necesito arreglarme la barba el jueves a las 4 de la tarde con Julián")
    chat.toco("ok")
    assert "documento" in chat.comparto("3209998877")
    assert "entre 6 y 10" in chat.digo("abc")
    final = chat.digo("1.110.555.444")
    assert "quedaste registrado como Daniel Vanegas" in final and "quedó agendada" in final
    assert chat.agenda.clientes()[-1] == {"id": 3, "nombre": "Daniel Vanegas", "documento": "1110555444",
                                          "telefono": "3209998877", "correo": ""}
    assert chat.citas == [(3, 2, 2, "2026-10-15T16:00", "PROGRAMADA")]
    assert chat.perfiles.de(YO)["cliente_id"] == 3


def test_un_cliente_que_ya_no_existe_se_vuelve_a_buscar_por_el_numero():
    chat = Chat(cliente_id=99)                                 # el perfil recuerda un cliente que la API ya no tiene
    chat.digo("quiero un corte con Julián el sábado a las 11")
    assert "No encontré tu ficha" in chat.toco("ok") and chat.ultima.pedir_contacto
    assert chat.perfiles.de(YO)["cliente_id"] is None and chat.citas == []
    assert "quedó agendada" in chat.comparto("+57 300 123 4567")
    assert chat.citas == [(1, 1, 2, "2026-10-17T11:00", "PROGRAMADA")]


def test_turno_ocupado_ofrece_los_cercanos():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(2, 1, 1, "2026-10-14T15:00")
    respuesta = chat.digo("me agendas un corte con Andrés mañana a las 3")
    assert "Andrés ya tiene una cita a las 3:00. ¿Te sirve alguna de estas?" in respuesta
    assert chat.botones == ["hor:14:30", "hor:15:30", "hor:16:00"]
    assert "3:30 p. m." in chat.toco("hor:15:30")
    chat.toco("ok")
    assert chat.citas[-1] == (1, 1, 1, "2026-10-14T15:30", "PROGRAMADA")


def test_pregunta_lo_que_falta_de_a_una_cosa():
    chat = Chat(cliente_id=1)
    assert "¿Qué te" in chat.digo("quiero una cita") and chat.botones[0] == "srv:1"
    assert "día" in chat.toco("srv:3") and chat.botones[0].startswith("dia:")
    assert "¿Cuál te sirve?" in chat.toco("dia:2026-10-16")
    assert "¿Con quién te quieres atender?" in chat.toco("hor:10:00")
    resumen = chat.toco("bar:2")
    assert "Corte y barba con Julián" in resumen and "viernes 16 de octubre, 10:00 a. m." in resumen and "$38.000" in resumen
    chat.digo("dale")
    assert chat.citas == [(1, 3, 2, "2026-10-16T10:00", "PROGRAMADA")]


def test_cambia_de_opinion_antes_de_confirmar():
    chat = Chat(cliente_id=1)
    chat.digo("un corte mañana a las 3 con Andrés")
    assert "4:00 p. m." in chat.digo("mejor a las 4")
    assert "jueves 15 de octubre, 4:00 p. m." in chat.digo("no, pasado mañana")
    chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-15T16:00", "PROGRAMADA")]


def test_reprogramar_la_del_sabado_para_el_lunes():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-17T15:00")
    resumen = chat.digo("cámbieme la del sábado para el lunes")
    assert "Te la cambio así" in resumen and "lunes 19 de octubre, 3:00 p. m." in resumen
    assert chat.citas == [(1, 1, 1, "2026-10-17T15:00", "PROGRAMADA")]
    assert "te cambié la cita" in chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-19T15:00", "PROGRAMADA")]       # la misma cita, movida


def test_reprogramar_solo_la_hora():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 3, 2, "2026-10-14T15:00")
    assert "miércoles 14 de octubre, 5:00 p. m." in chat.digo("no alcanzo a llegar a las 3, me la corres para las 5?")
    chat.toco("ok")
    assert chat.citas == [(1, 3, 2, "2026-10-14T17:00", "PROGRAMADA")]


def test_cancelar_pide_confirmacion():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-17T15:00")
    assert "te cancelo esta cita" in chat.digo("ya no voy a poder ir el sábado")
    assert chat.citas[0][-1] == "PROGRAMADA"
    assert "Listo, cancelé tu cita" in chat.toco("ok")
    assert chat.citas[0][-1] == "CANCELADA"


def test_cancelar_y_arrepentirse():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-17T15:00")
    chat.digo("cancela mi cita")
    assert "sigue en pie" in chat.toco("no")
    assert chat.agenda.escrituras == 0


def test_con_dos_citas_pregunta_cual():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-17T15:00")
    chat.agenda.agendar(1, 2, 2, "2026-10-20T10:00")
    assert "de tus citas" in chat.digo("quiero cancelar mi cita")
    assert chat.botones == ["cita:1", "cita:2", "cita:todas"]      # también puede cancelarlas todas de un toque
    chat.toco("cita:2")
    chat.toco("ok")
    assert [c[-1] for c in chat.citas] == ["PROGRAMADA", "CANCELADA"]


def test_consultas_no_tocan_la_agenda():
    chat = Chat(cliente_id=1)
    assert "$18.000" in chat.digo("cuánto vale la barba")
    assert "Corte y barba: $38.000" in chat.digo("qué servicios tienen")
    assert "no estamos haciendo tinte" in chat.digo("hacen tinte?")
    assert "No tienes citas programadas." in chat.digo("a qué hora es mi cita")
    tarde = chat.digo("¿tiene cupo mañana en la tarde?")
    assert "miércoles 14 de octubre" in tarde and chat.botones[0] == "hor:12:00" and chat.botones[-1] <= "hor:18:00"
    assert "Los domingos no atendemos" in chat.digo("abren los domingos?")
    assert chat.agenda.escrituras == 0


def test_fuera_de_alcance_muestra_el_menu():
    chat = Chat(cliente_id=1)
    chat.digo("¿venden cera para el pelo?")
    assert "menu:barbero" in chat.botones
    assert chat.agenda.escrituras == 0


def test_dia_y_hora_en_que_no_se_atiende():
    chat = Chat(cliente_id=1)
    assert "Los domingos no atendemos" in chat.digo("quiero un corte el domingo a las 10")
    chat = Chat(cliente_id=1)
    assert "A las 8:00 p. m. ya cerramos 😕 Atendemos hasta las 7:00 p. m. El" in chat.digo("quiero un corte mañana a las 8 de la noche con Andrés")
    assert chat.agenda.escrituras == 0


def test_lo_de_siempre():
    chat = Chat(cliente_id=1)
    chat.digo("corte y barba con Julián mañana a las 11")
    chat.toco("ok")
    resumen = chat.digo("quiero lo de siempre el viernes a las 4 con el de siempre")
    assert "Corte y barba con Julián" in resumen and "viernes 16 de octubre, 4:00 p. m." in resumen


def test_recordatorio_el_dia_anterior():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-14T15:00")
    avisos = chat.agente.recordatorios(AHORA)
    assert [uid for uid, _ in avisos] == [YO] and "mañana tienes cita" in avisos[0][1].texto
    assert chat.agente.recordatorios(AHORA) == []            # no se repite
    assert "te cancelo esta cita" in chat.toco("rec:cancelar:1")


def test_antes_de_todo_pide_autorizacion():
    chat = Chat()
    chat.perfiles.de(YO)["acepta"] = False
    assert "Ley 1581" in chat.digo("quiero un corte mañana a las 3 con Andrés")
    assert chat.botones == ["acepto"]
    assert "Corte clásico con Andrés" in chat.toco("acepto")  # retoma el mensaje que quedó pendiente


@pytest.mark.parametrize("mensaje", ["jajaja", "asdfgh", "cuál es la capital de Francia", "quiero pedir una pizza para las 8"])
def test_mensajes_ajenos_no_agendan(mensaje):
    chat = Chat(cliente_id=1)
    chat.digo(mensaje)
    assert chat.agenda.escrituras == 0 and chat.agente.estados[YO].intencion is None


def duda(texto):
    """Un clasificador que no está seguro, para probar el paso al LLM sin depender del modelo entrenado."""
    return {"intencion": "fuera_de_alcance", "confianza": 0.6, "ranuras": [{"tipo": "servicio", "valor": "corte de pelo"}]}


def test_el_respaldo_interpreta_lo_que_el_clasificador_no_entiende():
    chat, consultas = Chat(cliente_id=1), []
    entender_real = chat.agente.entender
    chat.agente.entender = lambda texto: duda(texto) if texto == "necesito un corte de pelo" else entender_real(texto)
    chat.agente.respaldo = lambda texto, contexto: consultas.append(texto) or {
        "intencion": "reservar", "confianza": 1.0, "ranuras": [{"tipo": "servicio", "valor": "corte de pelo"}]}
    assert "día" in chat.digo("necesito un corte de pelo") and chat.botones[0].startswith("dia:")
    chat.digo("mañana a las 3 con Andrés")
    assert consultas == ["necesito un corte de pelo"]                       # lo que el clasificador entiende no pasa al LLM


def test_sin_respaldo_ofrece_opciones():
    chat = Chat(cliente_id=1)
    chat.agente.entender = duda
    chat.agente.respaldo = lambda texto, contexto: None                     # el servicio no responde
    assert "¿Quieres que te agende una cita?" in chat.digo("necesito un corte de pelo")
    assert "día" in chat.toco("duda:reservar") and chat.botones[0].startswith("dia:")


def test_el_respaldo_no_escribe_en_la_agenda():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-17T15:00")
    chat.agente.respaldo = lambda texto, contexto: {"intencion": "cancelar", "confianza": 1.0, "ranuras": []}
    assert "te cancelo esta cita" in chat.digo("uy no qué pereza ir el finde")
    assert chat.agenda.escrituras == 0                                      # igual hay que confirmar


# --------------------------------------------------------------------------- versión 2: lo que falló en Telegram

def test_la_conversacion_de_la_captura():
    """«el 7 con desvanecido» describe el corte, la madrugada está antes de abrir y «cualquiera» contesta «¿con quién?»."""
    chat = Chat(cliente_id=1)
    primera = chat.digo("oe bro estoy muy mechudo dame una cita para el 16 en la madrugada, quiero solo las puntas y "
                        "el 7 con desvanecido.")
    assert "arreglada" in primera and "todavía no hemos abierto" in primera and "viernes 16 de octubre" in primera
    assert chat.botones[0] == "hor:09:00"
    assert "¿Con quién te quieres atender?" in chat.toco("hor:09:00")
    resumen = chat.digo("cualquiera")
    assert "viernes 16 de octubre, 9:00 a. m." in resumen and "solo las puntas, el 7 con desvanecido" in resumen
    chat.toco("ok")
    cita = chat.agenda.citas()[0]
    assert (cita["fechaHora"][:16], cita["observaciones"]) == ("2026-10-16T09:00", "solo las puntas, el 7 con desvanecido")


MECHUDO = "oe bro estoy muy mechudo dame una cita para el 16 en la madrugada, quiero solo las puntas y el 7 con desvanecido"


@pytest.mark.parametrize("hora", [" a las 09:52 AM", ".09:52 AM", " a las 9:52"])
def test_hora_entre_turnos_ofrece_los_mas_cercanos(hora):
    """Lo que salió en Telegram: a las 9:52 se atiende, pero las citas van en punto y a la media hora."""
    chat = Chat(cliente_id=1)
    texto = chat.digo(MECHUDO + hora)
    assert "cada media hora (9:00, 9:30, 10:00…)" in texto and "9:52 a. m." in texto
    assert "no estamos atendiendo" not in texto and "no hemos abierto" not in texto
    assert chat.botones == ["hor:09:30", "hor:10:00", "hor:10:30"]
    chat.toco("hor:10:00")
    assert "viernes 16 de octubre, 10:00 a. m." in chat.digo("cualquiera")
    chat.toco("ok")
    cita = chat.agenda.citas()[0]
    assert (cita["fechaHora"][:16], cita["observaciones"]) == ("2026-10-16T10:00", "solo las puntas, el 7 con desvanecido")


def test_madrugada_con_hora_es_de_la_manana():
    """«En la madrugada ... a las 4» son las 4:00 a. m.: un solo aviso, sin decir que a las 4 p. m. no se atiende."""
    chat = Chat(cliente_id=1)
    texto = chat.digo(MECHUDO + " a las 4")
    assert "A las 4:00 a. m. todavía no hemos abierto" in texto and texto.count("abierto") == 1
    assert "p. m. no estamos atendiendo" not in texto
    assert chat.botones == ["hor:09:00", "hor:09:30", "hor:10:00", "hor:10:30"]


def test_hora_definida_manda_sobre_la_franja():
    chat = Chat(cliente_id=1)
    assert "viernes 16 de octubre, 4:00 p. m." in chat.digo("un corte con Andrés para el 16 en la madrugada a las 4 de la tarde")


def test_cualquiera_no_amarra_al_barbero_que_le_toco():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(2, 1, 1, "2026-10-16T11:00")                  # Andrés está ocupado a las 11
    chat.digo("un corte el viernes a las 10")
    assert "con Andrés" in chat.digo("cualquiera")
    chat.toco("cambiar")
    assert "Corte clásico con Julián" in chat.digo("mejor a las 11")   # a las 11 lo atiende el que esté libre
    chat.toco("ok")
    assert chat.citas[-1] == (1, 1, 2, "2026-10-16T11:00", "PROGRAMADA")


def test_preguntar_por_una_hora_entre_turnos():
    chat = Chat(cliente_id=1)
    texto = chat.digo("¿tienen turno el viernes a las 9:52?")
    assert "cada media hora" in texto and chat.botones == ["hor:09:30", "hor:10:00", "hor:10:30"]


@pytest.mark.parametrize("respuesta", ["cualquiera", "cualquiera de los dos", "me da igual", "el que esté libre"])
def test_sin_preferencia_de_barbero(respuesta):
    chat = Chat(cliente_id=1)
    chat.digo("un corte el viernes a las 10")
    assert "¿Con quién te quieres atender?" in chat.ultima.texto
    assert "viernes 16 de octubre, 10:00 a. m." in chat.digo(respuesta) and chat.botones == ["ok", "cambiar"]


@pytest.mark.parametrize("correccion", ["no bro la cita es para el 16", "la cita es para el 16", "no parce, era para el viernes"])
def test_corrige_el_dia_antes_de_confirmar(correccion):
    chat = Chat(cliente_id=1)
    assert "jueves 15 de octubre" in chat.digo("un corte el jueves a las 10 con Andrés")
    assert "viernes 16 de octubre, 10:00 a. m." in chat.digo(correccion)
    chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-16T10:00", "PROGRAMADA")]


def test_cambiar_algo_con_botones():
    chat = Chat(cliente_id=1)
    chat.digo("un corte el jueves a las 10 con Andrés")
    assert "¿qué le cambiamos?" in chat.toco("cambiar") and chat.botones[0] == "cam:dia"
    assert "¿Cuál te sirve?" in chat.toco("cam:hora")
    assert "jueves 15 de octubre, 4:00 p. m." in chat.toco("hor:16:00")
    chat.digo("la cita es para el 16")                                       # escrito también sirve
    chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-16T16:00", "PROGRAMADA")]


def test_que_barberos_hay():
    chat = Chat(cliente_id=1)
    assert "Andrés y Julián" in chat.digo("que barberos hay disponibles?")
    assert chat.botones == ["bar:1", "bar:2"]
    assert "¿Qué te" in chat.toco("bar:2")
    assert chat.agenda.escrituras == 0


def test_dos_dias_en_el_mismo_mensaje():
    chat = Chat(cliente_id=1)
    respuesta = chat.digo("quiero un corte el 16 o el 20 con Andrés a las 10")
    assert "dos fechas" in respuesta and chat.botones == ["dia:2026-10-16", "dia:2026-10-20"]
    assert "martes 20 de octubre, 10:00 a. m." in chat.toco("dia:2026-10-20")


def test_reprogramar_sin_citas_ofrece_agendar():
    chat = Chat(cliente_id=1)
    assert "¿Te agendo una nueva" in chat.digo("cámbiame la cita para el viernes a las 4")
    # lo que dijo se conserva (y se le repite); falta el servicio
    assert "Para el viernes 16 de octubre a las 4:00 p. m., ¿qué te" in chat.toco("duda:reservar")
    chat.toco("srv:1")
    assert "viernes 16 de octubre, 4:00 p. m." in chat.toco("bar:0")
    assert chat.agenda.escrituras == 0



# ----------------------------------------------------------------------------- ronda de pruebas del 24 de octubre

PIDE_HORAS = "quiero una cita para el lunes no se que horas tengas disponible para ese dia me puedes decir?"


def test_cancelar_y_agendar_en_el_mismo_mensaje():
    """Lo que salió en Telegram: «cancélala, quiero una cita para el lunes» cancelaba y se olvidaba de la nueva."""
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-11-16T10:00")
    chat.digo("cancelala " + PIDE_HORAS)
    assert chat.botones == ["ok", "no"]
    texto = chat.toco("ok")
    assert "cancelé tu cita del lunes 16 de noviembre" in texto and "El lunes 19 de octubre tengo libre" in texto
    assert chat.citas == [(1, 1, 1, "2026-11-16T10:00", "CANCELADA")]
    chat.toco("hor:11:30")
    assert "lunes 19 de octubre, 11:30 a. m." in chat.digo("cualquiera")


def test_pregunta_que_horas_hay_antes_del_servicio():
    chat = Chat(cliente_id=1)
    assert "te digo qué horas tengo el lunes 19 de octubre" in chat.digo(PIDE_HORAS)
    assert "El lunes 19 de octubre tengo libre" in chat.toco("srv:1")


def test_lo_mas_pronto_posible():
    chat = Chat(cliente_id=1)
    assert "Lo más pronto que tengo es el martes 13 de octubre" in chat.digo("quiero un corte lo más pronto posible")
    assert chat.botones == ["hor:10:30", "hor:11:00", "hor:11:30", "hor:12:00"]


@pytest.mark.parametrize("respuesta, hora", [("la que tengas", "9:00 a. m."), ("a cualquier hora", "9:00 a. m."),
                                             ("la más temprano", "9:00 a. m."), ("la más tarde que tengas", "6:30 p. m.")])
def test_deja_que_el_agente_escoja_la_hora(respuesta, hora):
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana con andres")
    texto = chat.digo(respuesta)
    assert f"hora que tengo con Andrés es a las {hora}" in texto and f"miércoles 14 de octubre, {hora}" in texto


def test_cualquier_dia_es_el_primero_libre_con_todas_sus_horas():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte")
    assert "Lo primero que tengo es el martes 13 de octubre" in chat.digo("cualquier día")
    assert chat.botones[0] == "hor:10:30" and chat.botones[-1] == "hor:18:30"     # todo el día, no solo lo primero


def test_no_se_no_cancela_la_cita():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte")
    texto = chat.digo("no sé")
    assert ("Tranqui" in texto or "Fresco" in texto) and chat.botones[0].startswith("dia:")


def test_un_cliente_no_tiene_dos_citas_a_la_vez():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    assert "A esa hora ya tienes una cita: corte clásico con Andrés" in chat.digo("corte el viernes a las 10 con julian")
    assert "hor:10:00" not in chat.botones


def test_mover_la_cita_una_hora_mas_tarde():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    assert "viernes 16 de octubre, 11:00 a. m." in chat.digo("muéveme la cita una hora más tarde")
    chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-16T11:00", "PROGRAMADA")]


@pytest.mark.parametrize("mensaje, respuesta", [
    ("quiero hablar con el barbero", "310 456 7890"), ("me dejaron mal el corte la vez pasada", "qué pena"),
    ("jajaja", "😄"), ("dónde quedan?", "Eso no lo manejo por aquí"), ("aceptan nequi?", "310 456 7890"),
])
def test_lo_que_no_es_de_citas_tiene_respuesta(mensaje, respuesta):
    chat = Chat(cliente_id=1)
    texto = chat.digo(mensaje)
    assert respuesta in texto and "no te entendí" not in texto


def test_escrito_con_errores():
    chat = Chat(cliente_id=1)
    assert "sábado 17 de octubre, 10:00 a. m." in chat.digo("kiero un korte el savado a las 10 con andres")


def test_fin_de_semana_es_el_sabado():
    chat = Chat(cliente_id=1)
    assert "El sábado 17 de octubre tengo libre" in chat.digo("un corte el fin de semana")


def test_dia_que_ya_paso():
    chat = Chat(cliente_id=1)
    assert "Ese día ya pasó" in chat.digo("un corte ayer")


def test_pulgar_arriba_confirma():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana a las 3 con julian")
    assert "quedó agendada" in chat.digo("👍")
    assert chat.citas == [(1, 1, 2, "2026-10-14T15:00", "PROGRAMADA")]


def test_lo_de_siempre_es_con_el_barbero_de_siempre():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana a las 3 con julian")
    chat.toco("ok")
    assert "Corte clásico con Julián" in chat.digo("lo de siempre el viernes a las 4")


def test_una_consulta_en_medio_no_pierde_la_cita():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana a las 3 con julian")
    assert "vale $25.000" in chat.digo("¿cuánto vale?") and chat.botones == ["ok", "cambiar"]
    chat.digo("gracias")
    assert chat.botones == ["ok", "cambiar"]
    chat.digo("ok")
    assert chat.citas == [(1, 1, 2, "2026-10-14T15:00", "PROGRAMADA")]


def test_hola_en_medio_sigue_con_la_cita():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana")
    assert "¡Qué más, Carlos!" in chat.digo("hola") and chat.botones[0] == "hor:09:00"


def test_espera_no_escoge_nada():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana")
    assert "te espero" in chat.digo("espera un momento").lower()
    chat.toco("hor:10:30")
    assert "miércoles 14 de octubre, 10:30 a. m." in chat.digo("con andres")


def test_mejor_mas_tarde_ofrece_los_siguientes():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana a las 3 con andres")
    chat.digo("mejor más tarde")
    assert chat.botones[0] == "hor:15:30" and "hor:15:00" not in chat.botones


def test_cancelar_todas_las_citas():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    chat.agenda.agendar(1, 3, 2, "2026-10-17T15:00")
    assert "estas 2 citas" in chat.digo("cancela todas mis citas")
    assert "cancelé tus 2 citas" in chat.toco("ok")
    assert [c[4] for c in chat.citas] == ["CANCELADA", "CANCELADA"]


def test_cancelar_sin_citas_sigue_con_la_nueva():
    chat = Chat(cliente_id=1)
    texto = chat.digo("cancela mi cita y agéndame una para el viernes")
    assert "vamos con la nueva" in texto and chat.botones[0].startswith("srv:")
    assert "El viernes 16 de octubre tengo libre" in chat.toco("srv:1")


@pytest.mark.parametrize("mensaje, respuesta", [
    ("eres una persona o un robot?", "Soy TBot"), ("cómo te llamas?", "Soy TBot"),
    ("tienen descuento para estudiantes?", "promociones"), ("hacen cortes a domicilio?", "solo atendemos en la barbería"),
])
def test_preguntas_con_respuesta_fija(mensaje, respuesta):
    assert respuesta in Chat(cliente_id=1).digo(mensaje)


@pytest.mark.parametrize("mensaje, esperado", [
    ("un corte y de una vez la barba mañana a las 4 con andres", "Corte y barba con Andrés"),
    ("corte mañana 0930 con julian", "miércoles 14 de octubre, 9:30 a. m."),
    ("corte en ocho días con andres a las 10", "martes 20 de octubre, 10:00 a. m."),
])
def test_mensajes_que_antes_se_leian_mal(mensaje, esperado):
    assert esperado in Chat(cliente_id=1).digo(mensaje)


def test_entre_dos_horas_es_una_franja():
    chat = Chat(cliente_id=1)
    chat.digo("corte mañana entre las 3 y las 4")
    assert chat.botones == ["hor:15:00", "hor:15:30"]


def test_recuerdame():
    chat = Chat(cliente_id=1)
    chat.digo("corte el viernes a las 3 con julian")
    chat.toco("ok")
    assert "El jueves te escribo para recordarte tu cita del viernes 16 de octubre" in chat.digo("recuérdame porfa")


# ----------------------------------------------------------------------------- capturas del 24 de octubre en la tarde

def test_cancela_mientras_arma_la_cita_la_deja():
    chat = Chat(cliente_id=1)
    chat.digo(PIDE_HORAS)
    assert "no agendé nada" in chat.digo("cancela")
    assert chat.agenda.escrituras == 0


def test_si_despues_de_te_agendo_una_arranca_la_cita():
    """«cancela» sin citas -> «¿Te agendo una?» -> «'si» mostraba el menú en vez de empezar."""
    chat = Chat(cliente_id=1)
    assert "¿Te agendo una?" in chat.digo("cancela")
    assert "¿Qué te" in chat.digo("'si") and chat.botones[0].startswith("srv:")


def test_cualquier_barbero_y_el_numero_del_degradado():
    chat = Chat(cliente_id=1)
    chat.digo("agendar")
    texto = chat.digo("corte clasico con cualquier barbero el lunes a las 3 un 7 degradado que estoy muy mechudo")
    assert "lunes 19 de octubre, 3:00 p. m." in texto and "un 7 degradado" in texto
    assert "arreglada" in texto and "¿Con quién" not in texto


# ----------------------------------------------------------------------------- capturas del 24 de octubre en la noche

def dias_ofrecidos(chat):
    return [date.fromisoformat(d[4:]) for d in chat.botones if d.startswith("dia:")]


def test_que_dias_tienes_que_no_sea_el_lunes():
    chat = Chat(cliente_id=1)
    texto = chat.digo("Hola buenas tardes que días tienes agenda para un corte que no sea el día lunes. Gracias")
    assert texto.startswith("¡Buenas tardes, Carlos!") and "sin contar el lunes" in texto
    assert dias_ofrecidos(chat) and all(d.weekday() != 0 for d in dias_ofrecidos(chat))


def test_que_no_sea_el_lunes_en_medio_de_la_reserva_no_es_cancelar():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte el lunes")
    texto = chat.digo("Que no sea día lunes")
    assert "citas programadas" not in texto and "sin contar el lunes" in texto
    assert all(d.weekday() != 0 for d in dias_ofrecidos(chat))


def test_cualquier_dia_menos_uno():
    chat = Chat(cliente_id=1)                  # hoy es martes
    texto = chat.digo("Me podrías agendar una cita de corte, que sea para cualquier día menos el día martes")
    assert "Lo primero que tengo es el miércoles 14 de octubre" in texto and "No encuentro" not in texto
    assert "Lo primero que tengo es el jueves 15" in Chat(cliente_id=1).digo("un corte cualquier día menos hoy ni mañana")


def test_que_dias_tienes_en_la_manana_no_ofrece_los_que_estan_llenos():
    chat = Chat(cliente_id=1)
    for barbero in (1, 2):                     # el miércoles en la mañana no queda nada
        for hora in ("09:00", "09:50", "10:40", "11:30"):
            chat.agenda.agendar(2, 3, barbero, f"2026-10-14T{hora}")
    texto = chat.digo("Buenas noches que días tienes agenda en la mañana y que no sea el día lunes para un corte. Gracias")
    assert "en la mañana tengo turno estos días, sin contar el lunes" in texto
    assert date(2026, 10, 14) not in dias_ofrecidos(chat) and date(2026, 10, 15) in dias_ofrecidos(chat)


def test_que_dias_tienes_disponibles_pide_el_servicio_y_muestra_los_dias():
    chat = Chat(cliente_id=1)
    assert "te digo qué días tengo" in chat.digo("Que días tienes disponibles?")
    assert "Para corte clásico tengo turno estos días" in chat.toco("srv:1")
    assert dias_ofrecidos(chat)[0] == date(2026, 10, 13)


def test_no_ofrece_hoy_si_ya_no_quedan_turnos():
    chat = Chat(cliente_id=1)
    chat._ver(chat.agente.texto(YO, "Daniel Vanegas", "quiero un corte", datetime(2026, 10, 13, 18, 45)))
    assert dias_ofrecidos(chat)[0] == date(2026, 10, 14)


def test_a_las_10_no_tienes_contesta_que_si_hay():
    chat = Chat(cliente_id=1)
    texto = chat.digo("quiero un corte el jueves")
    assert "Hay más horas entre esas" in texto and "hor:10:00" not in chat.botones   # 10:00 no cabe entre los botones
    assert "El jueves 15 de octubre a las 10:00 a. m. tengo turno con Andrés y Julián" in chat.digo("a las 10 no tienes?")
    assert chat.botones == ["bar:1", "bar:2", "bar:0"]


def test_a_la_una_con_su_articulo():
    assert "jueves 15 de octubre a la 1:00 p. m. tengo turno" in Chat(cliente_id=1).digo("un corte el jueves a la 1 de la tarde")
    assert (f.las(time(13)), f.las(time(15), corta=True)) == ("la 1:00 p. m.", "las 3:00")


def test_barba_el_mismo_dia_del_corte_no_es_corte_y_barba():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T13:00")
    texto = chat.digo("Me podrías agendar una cita de arreglo de barba para el mismo día del corte")
    assert "El viernes 16 de octubre ya tienes corte clásico a la 1:00 p. m.: te puedo atender seguido, a la 1:30" in texto
    assert "hor:13:30" in chat.botones
    chat.toco("hor:13:30")
    assert "Arreglo de barba con Andrés" in chat.toco("bar:1")
    chat.toco("ok")
    assert chat.citas[-1] == (1, 2, 1, "2026-10-16T13:30", "PROGRAMADA")


@pytest.mark.parametrize("mensaje, hora", [("agéndame una barba justo después de mi corte", "1:30 p. m."),
                                           ("una barba antes del corte porfa", "12:30 p. m.")])
def test_barba_pegada_al_corte(mensaje, hora):
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T13:00")
    assert f"{hora} tengo turno con" in chat.digo(mensaje)
    assert f"Arreglo de barba con Julián\n📅 viernes 16 de octubre, {hora}" in chat.toco("bar:2")


def test_el_mismo_dia_sin_otra_cita_lo_dice():
    texto = Chat(cliente_id=1).digo("una barba para el mismo día del corte")
    assert "No veo otra cita tuya programada" in texto and "Corte y barba" not in texto


def test_cancelar_las_dos_del_martes():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-20T13:00")
    chat.agenda.agendar(1, 3, 1, "2026-10-20T13:30")
    chat.agenda.agendar(1, 1, 1, "2026-10-22T15:00")
    texto = chat.digo("Quiero cancelar las dos citas que tengo agendadas para el martes")
    assert "estas 2 citas" in texto and "jueves" not in texto
    assert "cancelé tus 2 citas" in chat.toco("ok")
    assert [c[-1] for c in chat.citas] == ["CANCELADA", "CANCELADA", "PROGRAMADA"]   # y no agendó otra


@pytest.mark.parametrize("mensaje", ["Cancela mis citas", "cancela todo", "cancela la del martes y la del jueves"])
def test_cancelar_varias(mensaje):
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-20T13:00")
    chat.agenda.agendar(1, 2, 2, "2026-10-22T15:00")
    assert "estas 2 citas" in chat.digo(mensaje)
    chat.toco("ok")
    assert [c[-1] for c in chat.citas] == ["CANCELADA", "CANCELADA"]


def test_boton_para_cancelar_todas():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-20T13:00")
    chat.agenda.agendar(1, 2, 2, "2026-10-22T15:00")
    chat.digo("quiero cancelar una cita")
    assert "estas 2 citas" in chat.toco("cita:todas")
    chat.toco("ok")
    assert [c[-1] for c in chat.citas] == ["CANCELADA", "CANCELADA"]


def test_cancela_todo_mientras_arma_la_cita_la_deja():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte el jueves")
    assert "no agendé nada" in chat.digo("cancela todo")


def test_el_lunes_no_puedo_mejor_el_martes():
    chat = Chat(cliente_id=1)
    chat.digo("quiero un corte")
    texto = chat.digo("el lunes no puedo, mejor el martes")
    assert "El martes 20 de octubre tengo libre" in texto and "Me nombraste dos fechas" not in texto


def test_mas_o_menos_no_descarta_el_dia():
    assert "jueves 15 de octubre, 3:00 p. m." in Chat(cliente_id=1).digo("un corte con andres más o menos el jueves a las 3")


def test_mover_a_cualquier_dia_menos_el_lunes_no_crea_otra_cita():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-19T15:00")          # lunes
    texto = chat.digo("cámbiame la cita para cualquier día menos el lunes")
    assert "Te la cambio así" in texto and "martes 13 de octubre, 3:00 p. m." in texto
    chat.toco("ok")
    assert chat.citas == [(1, 1, 1, "2026-10-13T15:00", "PROGRAMADA")]


def test_pedir_el_numero_para_ver_citas_no_atrapa_la_conversacion():
    chat = Chat()
    chat._ver(chat.agente.comando(YO, "Daniel Vanegas", "miscitas", AHORA))
    assert chat.ultima.pedir_contacto
    assert "El jueves 15 de octubre tengo libre" in chat.digo("quiero un corte el jueves")


# ----------------------------------------------------------------------------- cada cambio se confirma

def test_cambiar_la_hora_antes_de_escoger_el_servicio_se_confirma():
    """La captura: «agéndame el martes a las 3» -> «cámbiame la hora a las 5», y el agente solo volvía a preguntar."""
    chat = Chat(cliente_id=1)
    assert "Para el martes 20 de octubre a las 3:00 p. m., ¿qué te" in chat.digo("agendame una cita para el martes a las 3")
    texto = chat.digo("cambiame la hora a las 5")
    assert texto.startswith("Listo, cambié la hora a las 5:00 p. m. 👍") and "martes 20 de octubre a las 5:00 p. m." in texto
    chat.toco("srv:1")
    assert "martes 20 de octubre, 5:00 p. m." in chat.toco("bar:1")


def test_cambiar_el_servicio_se_confirma():
    chat = Chat(cliente_id=1)
    # en Telegram el clasificador dudó y el LLM leyó el mensaje como reprogramar: sigue siendo la cita que se arma
    chat.agente.respaldo = lambda texto, contexto: {"intencion": "reprogramar", "confianza": 1.0,
                                                    "ranuras": [{"tipo": "servicio", "valor": "corte y barba"}]}
    chat.digo("quiero un corte a las 3")
    texto = chat.digo("ya no quiero ese servicio quiero corte y barba, puedes cambiarlo?")
    assert texto.startswith("Listo, cambié el servicio a corte y barba 👍")
    assert "¿Qué día te queda bien para corte y barba a las 3:00 p. m.?" in texto     # y lo demás sigue en pie


@pytest.mark.parametrize("cambio, confirmacion, queda", [
    ("cámbiame la hora a las 5", "la hora a las 5:00 p. m.", "jueves 15 de octubre, 5:00 p. m."),
    ("mejor con julián", "el barbero a Julián", "Corte clásico con Julián"),
    ("mejor el viernes", "el día al viernes 16 de octubre", "viernes 16 de octubre, 3:00 p. m."),
    ("mejor corte y barba", "el servicio a corte y barba", "Corte y barba con Andrés"),
    ("una hora más tarde", "la hora a las 4:00 p. m.", "jueves 15 de octubre, 4:00 p. m."),
    ("mejor el viernes a las 5 con julian", "el día al viernes 16 de octubre, la hora a las 5:00 p. m. y el barbero a Julián",
     "Corte clásico con Julián\n📅 viernes 16 de octubre, 5:00 p. m."),
])
def test_cada_cambio_en_el_resumen_se_confirma(cambio, confirmacion, queda):
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    texto = chat.digo(cambio)
    assert texto.startswith(f"Listo, cambié {confirmacion} 👍") and queda in texto
    assert chat.botones == ["ok", "cambiar"]


@pytest.mark.parametrize("pasos, confirmacion", [
    (["cam:hora", "hor:17:00"], "la hora a las 5:00 p. m."), (["cam:barbero", "bar:2"], "el barbero a Julián"),
    (["cam:servicio", "srv:3"], "el servicio a corte y barba"), (["cam:dia", "dia:2026-10-16"], "el día al viernes 16 de octubre"),
])
def test_cambiar_algo_con_botones_se_confirma(pasos, confirmacion):
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    chat.toco("cambiar")
    for paso in pasos:
        texto = chat.toco(paso)
    assert texto.startswith(f"Listo, cambié {confirmacion} 👍") and chat.botones == ["ok", "cambiar"]


def test_lo_que_no_cambia_no_se_confirma():
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    assert "Listo, cambié" not in chat.digo("mejor más tarde")      # muestra las horas siguientes: todavía no cambió
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    chat.toco("cambiar")
    chat.toco("cam:hora")
    assert "Listo, cambié" not in chat.toco("hor:15:00")             # escogió la misma hora


def test_si_la_hora_nueva_esta_ocupada_dice_que_no_la_cambio():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(2, 1, 1, "2026-10-15T17:00")
    chat.digo("corte con andres el jueves a las 3")
    texto = chat.digo("mejor a las 5")
    assert "Listo, cambié" not in texto and "No te la cambié. ¿Te sirve alguna de estas, o la dejamos a las 3:00 p. m.?" in texto
    assert "jueves 15 de octubre, 3:00 p. m." in chat.toco("hor:15:00")


def test_sin_preferencia_de_barbero_avisa_si_cambia_quien_atiende():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(2, 1, 1, "2026-10-15T17:00")                # a las 5 Andrés está ocupado
    assert "Corte clásico con Andrés" in chat.digo("corte el jueves a las 3 con cualquiera")
    assert chat.digo("mejor a las 5").startswith("Listo, cambié la hora a las 5:00 p. m. y el barbero a Julián 👍")


def test_mover_una_cita_dice_de_que_a_que():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    chat.digo("cámbiame la cita para el jueves")
    assert chat.digo("mejor a las 4").startswith("Listo, cambié la hora a las 4:00 p. m. 👍")
    final = chat.toco("ok")
    assert "Ya no es el viernes 16 de octubre a las 10:00 a. m.; ahora quedó así:\nCorte clásico con Andrés\njueves 15" in final
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    chat.digo("cámbiame la cita con julián")
    assert "¡Listo, te cambié la cita! Ahora quedó así:\nCorte clásico con Julián" in chat.toco("ok")


def test_ya_no_la_quiero_para_el_martes_cambiamela_para_el_domingo():
    """La captura: el domingo no se atiende y el martes lo descartó; antes quedaban «dos fechas» y se perdía el martes
    sin decir nada."""
    chat = Chat(cliente_id=1)
    chat.digo("quiero una cita para el martes a las tres")
    texto = chat.digo("ya no la quiero para el martes cambiamela para el domingo")
    assert texto.startswith("Listo, ya no es el martes 20 de octubre 👍") and "Los domingos no atendemos" in texto
    texto = chat.toco("srv:1")
    assert "Para corte clásico a las 3:00 p. m. tengo turno estos días, sin contar el martes" in texto
    assert "dos fechas" not in texto and all(d.weekday() not in (1, 6) for d in dias_ofrecidos(chat))


@pytest.mark.parametrize("cambio, motivo", [("mejor el domingo", "Los domingos no atendemos 😕"),
                                            ("cámbiamela para el domingo", "Los domingos no atendemos 😕"),
                                            ("mejor ayer", "Ese día ya pasó 😅")])
def test_un_dia_que_no_se_puede_no_cambia_la_cita(cambio, motivo):
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    texto = chat.digo(cambio)
    assert f"{motivo}, así que no te la cambié de día." in texto and "jueves 15 de octubre, 3:00 p. m." in texto
    assert chat.botones == ["ok", "cambiar"]


@pytest.mark.parametrize("mensaje", ["ya no la quiero para el jueves", "el jueves no me sirve"])
def test_descartar_el_dia_de_la_cita_que_se_arma(mensaje):
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    texto = chat.digo(mensaje)
    assert texto.startswith("Listo, ya no es el jueves 15 de octubre 👍") and "citas programadas" not in texto
    assert "a las 3:00 p. m. tengo turno estos días, sin contar el jueves" in texto      # la hora sigue en pie
    assert dias_ofrecidos(chat) and all(d.weekday() != 3 for d in dias_ofrecidos(chat))
    assert "viernes 16 de octubre, 3:00 p. m." in chat.toco("dia:2026-10-16")
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    assert chat.digo("ya no la quiero para el jueves, mejor el viernes").startswith(
        "Listo, cambié el día al viernes 16 de octubre 👍")


def test_una_hora_que_no_se_atiende_no_cambia_la_cita():
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 3")
    assert chat.digo("mejor a las 8 de la noche").startswith("No te la cambié de hora. A las 8:00 p. m. ya cerramos")
    assert "hor:15:00" in chat.botones                              # el botón para dejarla como estaba
    chat = Chat(cliente_id=1)
    chat.digo("corte con andres el jueves a las 10")
    assert "No te la cambié" not in chat.digo("mejor en la tarde")  # pidió otra franja: no es un cambio fallido


def test_mover_una_cita_a_un_dia_cerrado_dice_que_sigue_igual():
    chat = Chat(cliente_id=1)
    chat.agenda.agendar(1, 1, 1, "2026-10-16T10:00")
    assert "Los domingos no atendemos 😕, así que tu cita sigue el viernes 16 de octubre." in chat.digo(
        "cámbiamela para el domingo")
    assert chat.agenda.escrituras == 0


def test_dos_fechas_y_una_no_se_atiende():
    assert "sábado 17 de octubre, 10:00 a. m." in Chat(cliente_id=1).digo("corte el sábado o el domingo a las 10 con julian")
