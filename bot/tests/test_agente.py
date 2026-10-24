"""Conversaciones completas contra una agenda en memoria, con el clasificador real.

Cada prueba mira cómo queda la agenda al final, que es lo que importa: ninguna cita creada, movida o
cancelada por error. El «ahora» es el martes 13 de octubre de 2026 a las 10:00 a. m.
"""
from datetime import datetime

import pytest

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
    assert chat.botones == ["cita:1", "cita:2"]
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
    assert "¿Qué te" in chat.toco("duda:reservar")                          # lo que dijo se conserva; falta el servicio
    chat.toco("srv:1")
    assert "viernes 16 de octubre, 4:00 p. m." in chat.toco("bar:0")
    assert chat.agenda.escrituras == 0

