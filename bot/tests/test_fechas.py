"""Pruebas del normalizador. La fecha de referencia es el martes 13 de octubre de 2026, la del ejemplo del informe."""
from datetime import date, time

import pytest

from bot.fechas import Fecha, Franja, Hora, en_horario, fecha, franja, hora

HOY = date(2026, 10, 13)


def d(mes, dia, anio=2026):
    return date(anio, mes, dia)


@pytest.mark.parametrize("texto, dia", [
    ("hoy", d(10, 13)), ("hoy mismo", d(10, 13)), ("mañana", d(10, 14)), ("mañana mismo", d(10, 14)),
    ("pasado mañana", d(10, 15)), ("manana", d(10, 14)), ("oy", d(10, 13)),
    ("el sábado", d(10, 17)), ("sábado", d(10, 17)), ("este sábado", d(10, 17)), ("el próximo sábado", d(10, 17)),
    ("el sábado que viene", d(10, 17)), ("el otro sábado", d(10, 24)), ("el sábado de la otra semana", d(10, 24)),
    ("el viernes de esta semana", d(10, 16)), ("el martes", d(10, 20)), ("este martes", d(10, 13)),
    ("el lunes", d(10, 19)), ("el lunes festivo", d(10, 19)), ("el domingo", d(10, 18)), ("el miércoles", d(10, 14)),
    ("el savado", d(10, 17)), ("el biernes", d(10, 16)), ("el sabaod de la otra semana", d(10, 24)),
    ("el proximo jueves", d(10, 15)), ("el miercoles de la otra semana", d(10, 21)),
    ("el 15", d(10, 15)), ("el 12", d(11, 12)), ("el 30", d(10, 30)), ("15", d(10, 15)),
    ("el 20 de octubre", d(10, 20)), ("el 3 de noviembre", d(11, 3)), ("el 5 de octubre", d(10, 5, 2027)),
    ("el 24 de diciembre", d(12, 24)), ("el primero de noviembre", d(11, 1)), ("el 31 de octubre", d(10, 31)),
    ("15/10", d(10, 15)), ("el 28/11", d(11, 28)), ("el sábado 17", d(10, 17)), ("el jueves 22", d(10, 22)),
    ("el martes 20 de octubre", d(10, 20)), ("el 15 de este mes", d(10, 15)), ("el 2 de enero", d(1, 2, 2027)),
    ("el dieciséis", d(10, 16)), ("el quince", d(10, 15)), ("el día 16", d(10, 16)), ("el veinte", d(10, 20)),
    ("16", d(10, 16)),
])
def test_dias(texto, dia):
    assert fecha(texto, HOY).dia == dia
    assert fecha(texto, HOY).hasta is None


@pytest.mark.parametrize("texto, desde, hasta", [
    ("esta semana", d(10, 13), d(10, 18)), ("la otra semana", d(10, 19), d(10, 25)),
    ("la próxima semana", d(10, 19), d(10, 25)), ("la semana que viene", d(10, 19), d(10, 25)),
    ("la semana entrante", d(10, 19), d(10, 25)), ("el fin de semana", d(10, 17), d(10, 18)),
    ("este fin de semana", d(10, 17), d(10, 18)), ("el finde", d(10, 17), d(10, 18)),
])
def test_intervalos(texto, desde, hasta):
    f = fecha(texto, HOY)
    assert (f.dia, f.hasta) == (desde, hasta)


@pytest.mark.parametrize("texto, habitual", [
    ("los domingos", "domingo"), ("los sábados", "sabado"), ("los lunes", "lunes"), ("los festivos", "festivos"),
    ("entre semana", "entre semana"), ("los fines de semana", "fines de semana"), ("domingos", "domingo"),
])
def test_preguntas_generales(texto, habitual):
    assert fecha(texto, HOY) == Fecha(habitual=habitual)


@pytest.mark.parametrize("texto", ["", "cualquier día", "cuando se pueda", "otro día"])
def test_fechas_que_no_son(texto):
    assert fecha(texto, HOY) is None


def test_fin_de_anio():
    assert fecha("el 5", date(2026, 12, 20)).dia == date(2027, 1, 5)
    assert fecha("el sábado", date(2026, 12, 30)).dia == date(2027, 1, 2)
    assert fecha("la otra semana", date(2026, 12, 30)).dia == date(2027, 1, 4)


@pytest.mark.parametrize("texto, esperada", [
    ("a las 3", Hora(3, 0)), ("tipo tres", Hora(3, 0)), ("tipo 3", Hora(3, 0)), ("las 11", Hora(11, 0)),
    ("como a las 4", Hora(4, 0)), ("a eso de las 7", Hora(7, 0)), ("sobre las 5", Hora(5, 0)),
    ("a la 1", Hora(1, 0)), ("a la una y media", Hora(1, 30)), ("a las 3 y media", Hora(3, 30)),
    ("tres y cuarto", Hora(3, 15)), ("3:30", Hora(3, 30)), ("a las 5:15", Hora(5, 15)),
    ("a las 4 en punto", Hora(4, 0)), ("a las 4 menos cuarto", Hora(3, 45)), ("a las 3 y 20", Hora(3, 20)),
    ("a las 3 de la tarde", Hora(15, 0, True)), ("3pm", Hora(15, 0, True)), ("3 pm", Hora(15, 0, True)),
    ("4:30 pm", Hora(16, 30, True)), ("a las 4:00 p.m.", Hora(16, 0, True)), ("a las 7 pm", Hora(19, 0, True)),
    ("tres y media de la tarde", Hora(15, 30, True)), ("a las 8 de la noche", Hora(20, 0, True)),
    ("a las 10 de la mañana", Hora(10, 0, True)), ("10 am", Hora(10, 0, True)), ("9am", Hora(9, 0, True)),
    ("a las 9:30 a.m.", Hora(9, 30, True)), ("15:00", Hora(15, 0, True)), ("a las 14:30", Hora(14, 30, True)),
    ("a mediodía", Hora(12, 0, True)), ("al medio día", Hora(12, 0, True)), ("a las 12", Hora(12, 0, True)),
    ("12 del día", Hora(12, 0, True)), ("a primera hora", Hora(especial="primera")),
    ("a última hora", Hora(especial="ultima")), ("ahorita", Hora(en_minutos=0)), ("ahora mismo", Hora(en_minutos=0)),
    ("en media hora", Hora(en_minutos=30)), ("en una hora", Hora(en_minutos=60)),
    ("en 20 minutos", Hora(en_minutos=20)), ("en dos horas", Hora(en_minutos=120)),
])
def test_horas(texto, esperada):
    assert hora(texto) == esperada


@pytest.mark.parametrize("texto, lecturas", [
    ("a las 3", [time(15)]), ("a las 10", [time(10)]), ("tipo 11", [time(11)]), ("a las 9", [time(9)]),
    ("a las 6:30", [time(18, 30)]), ("a las 8", []), ("a las 7", []), ("a las 8 de la noche", []),
    ("a las 3 de la tarde", [time(15)]), ("a mediodía", [time(12)]),
])
def test_la_hora_se_lee_dentro_del_horario(texto, lecturas):
    assert en_horario(hora(texto), time(9), time(19)) == lecturas


def test_la_franja_decide_cuando_el_horario_no_alcanza():
    # Con un horario de 8 a 20, «a las 8» puede ser de la mañana o de la noche
    assert en_horario(hora("a las 8"), time(8), time(21)) == [time(8), time(20)]
    assert en_horario(hora("a las 8"), time(8), time(21), franja("en la noche")) == [time(20)]


@pytest.mark.parametrize("texto, esperada", [
    ("en la tarde", Franja(time(12), time(18))), ("por la tarde", Franja(time(12), time(18))),
    ("en la tardecita", Franja(time(12), time(18))), ("la tarde", Franja(time(12), time(18))),
    ("en la mañana", Franja(hasta=time(12))), ("por la mañana", Franja(hasta=time(12))),
    ("en horas de la mañana", Franja(hasta=time(12))), ("en la noche", Franja(desde=time(18))),
    ("temprano", Franja(hasta=time(10, 30))), ("bien tempranito", Franja(hasta=time(10, 30))),
    ("después de las 5", Franja(desde=time(17))), ("después de las 6 de la tarde", Franja(desde=time(18))),
    ("a partir de las 4", Franja(desde=time(16))), ("antes de las 10", Franja(hasta=time(10))),
    ("antes de las 7", Franja(hasta=time(19))), ("después del almuerzo", Franja(desde=time(14))),
    ("antes del almuerzo", Franja(hasta=time(12))), ("antes del mediodía", Franja(hasta=time(12))),
    ("después del mediodía", Franja(desde=time(12))), ("entre las 3 y las 4", Franja(time(15), time(16))),
    ("a media mañana", Franja(time(10), time(11, 30))), ("a media tarde", Franja(time(15), time(16, 30))),
    ("al final de la tarde", Franja(desde=time(17))), ("esta tarde", Franja(time(12), time(18), True)),
    ("esta noche", Franja(desde=time(18), hoy=True)), ("en la madrugada", Franja(hasta=time(6))),
    ("de madrugada", Franja(hasta=time(6))), ("a la hora del almuerzo", Franja(time(12), time(14))),
])
def test_franjas(texto, esperada):
    assert franja(texto) == esperada
