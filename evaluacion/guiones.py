"""Los guiones con que se mide la tarea completa (Tabla IV del informe).

Cada guion dice qué quiere el cliente, cómo está la agenda antes de empezar y cómo debe quedar al final.
Los 60 primeros cubren reservas completas e incompletas, cambios de opinión, turnos ocupados,
reprogramaciones, cancelaciones, consultas y mensajes fuera de alcance. Los 10 del grupo H se añadieron en
la segunda versión con lo que falló al probar el bot en Telegram: registro colombiano, descripciones del
corte con números, correcciones antes de confirmar y «cualquiera». El «ahora» de todos es el martes 13 de
octubre de 2026 a las 10:00 a. m.

Catálogo: servicios 1 Corte clásico, 2 Arreglo de barba, 3 Corte y barba; barberos 1 Andrés, 2 Julián.
Clientes: 1 Carlos Ramírez, 2 Mateo Herrera. Una cita se escribe (cliente, servicio, barbero, fecha y hora).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time

from bot import formato as f

AHORA = datetime(2026, 10, 13, 10, 0)


@dataclass
class Guion:
    id: str
    tipo: str
    que: str
    abre: list                                      # maneras de empezar; cada repetición usa una
    sabe: dict = field(default_factory=dict)        # qué contesta si le preguntan: {"hor": (frases, botón)}
    quiere: list = field(default_factory=list)      # lo que debe decir el resumen para que confirme
    corrige: list = field(default_factory=list)     # cambios de opinión al ver el resumen («#cambiar» es un botón)
    si: dict = field(default_factory=dict)          # reacción a una frase del agente: texto, botón o «primera»
    confirma: bool = True
    cliente: int | None = 1                         # None: todavía no está vinculado a un cliente de la barbería
    telefono: str = ""
    documento: str = ""
    agenda: list = field(default_factory=list)      # citas que ya existen
    queda: list = field(default_factory=list)       # agenda al final, con el estado de cada cita
    dice: str = ""                                  # algo que el agente debe decir (consultas)


# --------------------------------------------------------------------------- lo que pide el cliente

CORTE = (["un corte", "un corte de pelo", "una motilada"], "srv:1", "Corte clásico")
BARBA = (["un arreglo de barba", "la barba", "una afeitada"], "srv:2", "Arreglo de barba")
COMBO = (["corte y barba", "un corte con barba", "corte y arreglo de barba"], "srv:3", "Corte y barba")
ANDRES = (["con Andrés", "con andres", "con Andrés Rojas"], "bar:1", "Andrés")
JULIAN = (["con Julián", "con julian", "con Juli"], "bar:2", "Julián")
LIBRE = (["con cualquiera", "con el que esté libre", "con el que sea"], "bar:0", None)


def dia(d, *frases):
    return (list(frases), f"dia:{d.isoformat()}", d)


def hora(t, *frases):
    return (list(frases), f"hor:{t.strftime('%H:%M')}", t)


HOY = dia(date(2026, 10, 13), "hoy", "hoy mismo", "hoy martes")
MANANA = dia(date(2026, 10, 14), "mañana", "manana", "el miércoles")
PASADO = dia(date(2026, 10, 15), "pasado mañana", "el jueves", "pasado manana")
VIERNES = dia(date(2026, 10, 16), "el viernes", "este viernes", "el viernes 16")
SABADO = dia(date(2026, 10, 17), "el sábado", "este sábado", "el sabado")
LUNES = dia(date(2026, 10, 19), "el lunes", "el próximo lunes", "el lunes 19")
MARTES20 = dia(date(2026, 10, 20), "el 20 de octubre", "el martes 20", "el 20")
OTRO_SABADO = dia(date(2026, 10, 24), "el otro sábado", "el sábado de la otra semana", "el 24 de octubre")

H9 = hora(time(9), "a las 9", "a las 9 de la mañana", "9am")
H930 = hora(time(9, 30), "a las 9 y media", "a las 9:30", "9:30 am")
H10 = hora(time(10), "a las 10", "a las 10 de la mañana", "10 am")
H11 = hora(time(11), "a las 11", "tipo 11", "a las 11 de la mañana")
H12 = hora(time(12), "a mediodía", "a las 12", "al mediodía")
H14 = hora(time(14), "a las 2", "a las 2 de la tarde", "tipo 2")
H15 = hora(time(15), "a las 3", "tipo tres", "a las 3 de la tarde")
H1530 = hora(time(15, 30), "a las 3 y media", "a las 3:30", "3:30 pm")
H16 = hora(time(16), "a las 4", "tipo 4", "a las 4 de la tarde")
H17 = hora(time(17), "a las 5", "a las 5 de la tarde", "5pm")
H18 = hora(time(18), "a las 6", "a las 6 de la tarde", "6 pm")
PRIMERA = hora(time(9), "a primera hora", "a primera hora", "a primera hora")

PLANTILLAS = [
    lambda p: f"quiero {p['s']} {p['b']} {p['d']} {p['h']}",
    lambda p: f"necesito {p['s']} {p['d']} {p['h']} {p['b']}",
    lambda p: f"hola, quisiera {p['s']} {'para ' + p['d'] if p['d'] else ''} {p['h']} {p['b']}",
    lambda p: f"buenas, es para {p['s']} {p['d']} {p['h']} {p['b']}",
    lambda p: f"me puedes agendar {p['s']} {p['b']} {p['d']} {p['h']}?",
]


def reserva(id, tipo, que, s, b, d, h, dice="sbdh", final=None, cliente=1, queda=None, **otros):
    """Guion de una reserva.

    `dice` son las ranuras que el cliente da en el primer mensaje; las demás las contesta cuando el agente
    las pregunta. `final` es lo que cambia entre lo que pidió al principio y lo que debe quedar agendado.
    """
    partes, abre = {"s": s[0], "b": b[0], "d": d[0], "h": h[0]}, []
    for i, plantilla in enumerate(PLANTILLAS):
        p = {clave: (frases[i % len(frases)] if clave in dice else "") for clave, frases in partes.items()}
        p["s"] = p["s"] or "una cita"
        abre.append(" ".join(plantilla(p).split()).replace(" ?", "?"))
    s2, b2, d2, h2 = ({"s": s, "b": b, "d": d, "h": h} | (final or {})).values()
    quiere = [f"{s2[2]} con {b2[2]}" if b2[2] else s2[2], f"{f.dia(d2[2])}, {f.hora(h2[2])}"]
    previas = [(*c, "PROGRAMADA") for c in otros.get("agenda", [])]
    cita = (cliente or otros.pop("sera", 3), int(s2[1][4:]), int(b2[1][4:]) or 1,
            f"{d2[2].isoformat()}T{h2[2].strftime('%H:%M')}", "PROGRAMADA")
    return Guion(id, tipo, que, abre, sabe={"srv": s[:2], "bar": b[:2], "dia": d[:2], "hor": h[:2]}, quiere=quiere,
                 queda=previas + [cita] if queda is None else queda, cliente=cliente, **otros)


def con(*citas, estado="PROGRAMADA"):
    return [(*c, estado) for c in citas]


MIA = (1, 1, 1, "2026-10-17T15:00")            # la cita de Carlos: corte con Andrés el sábado a las 3
OTRA_MIA = (1, 2, 2, "2026-10-20T10:00")       # y una segunda: barba con Julián el martes 20 a las 10
AJENA = (2, 1, 1, "2026-10-14T15:00")          # Mateo ya tiene a Andrés mañana a las 3
JULIAN_LLENO = [(2, 3, 2, f"2026-10-17T{h:02d}:00") for h in range(9, 19)]     # Julián sin un turno el sábado

GUIONES = [
    # ----------------------------------------------------------------------- reservas completas
    reserva("A01", "reserva completa", "Corte con Andrés mañana a las 3", CORTE, ANDRES, MANANA, H15),
    reserva("A02", "reserva completa", "Corte y barba con Julián el sábado a las 10", COMBO, JULIAN, SABADO, H10),
    reserva("A03", "reserva completa", "Barba con Julián pasado mañana a las 4", BARBA, JULIAN, PASADO, H16),
    reserva("A04", "reserva completa", "Corte con Andrés hoy a las 5", CORTE, ANDRES, HOY, H17),
    reserva("A05", "reserva completa", "Corte con Julián el viernes a las 11", CORTE, JULIAN, VIERNES, H11),
    reserva("A06", "reserva completa", "Corte y barba con Andrés el lunes a las 2", COMBO, ANDRES, LUNES, H14),
    reserva("A07", "reserva completa", "Corte mañana a las 9 con el que esté libre", CORTE, LIBRE, MANANA, H9),
    reserva("A08", "reserva completa", "Cliente nuevo: se registra con documento y agenda", CORTE, ANDRES, PASADO, H1530,
            cliente=None, telefono="3205551234", documento="1110222333"),
    reserva("A09", "reserva completa", "Cliente que ya existe en la barbería y escribe por primera vez", BARBA, JULIAN,
            VIERNES, H16, cliente=None, sera=2, telefono="3012345678"),
    reserva("A10", "reserva completa", "Corte con Andrés el 20 de octubre a las 10", CORTE, ANDRES, MARTES20, H10),
    reserva("A11", "reserva completa", "Corte y barba con Julián el otro sábado a mediodía", COMBO, JULIAN, OTRO_SABADO, H12),
    reserva("A12", "reserva completa", "Corte con Andrés mañana a primera hora", CORTE, ANDRES, MANANA, PRIMERA),
    reserva("A13", "reserva completa", "Corte con Julián mañana a las 6", CORTE, JULIAN, MANANA, H18),
    reserva("A14", "reserva completa", "Barba con Andrés el sábado a las 3", BARBA, ANDRES, SABADO, H15),

    # ----------------------------------------------------------------------- reservas incompletas
    reserva("B01", "reserva incompleta", "Solo dice que quiere una cita", CORTE, ANDRES, VIERNES, H10, dice=""),
    reserva("B02", "reserva incompleta", "Dice el servicio", COMBO, JULIAN, MANANA, H16, dice="s"),
    reserva("B03", "reserva incompleta", "Dice servicio y día; no le importa el barbero", BARBA, LIBRE, SABADO, H11, dice="sd"),
    reserva("B04", "reserva incompleta", "Dice día y hora", CORTE, JULIAN, MANANA, H15, dice="dh"),
    reserva("B05", "reserva incompleta", "Dice el barbero", CORTE, ANDRES, PASADO, H17, dice="b"),
    reserva("B06", "reserva incompleta", "Dice servicio y barbero", CORTE, JULIAN, PASADO, H930, dice="sb"),
    reserva("B07", "reserva incompleta", "Dice servicio y hora", CORTE, ANDRES, HOY, H16, dice="sh"),
    reserva("B08", "reserva incompleta", "Dice servicio, día y barbero", BARBA, JULIAN, LUNES, H12, dice="sdb"),
    reserva("B09", "reserva incompleta", "Dice servicio y día", COMBO, JULIAN, MANANA, H14, dice="sd"),
    reserva("B10", "reserva incompleta", "Cliente nuevo que solo dice el servicio", CORTE, ANDRES, VIERNES, H15, dice="s",
            cliente=None, telefono="3187776655", documento="1005123456"),

    # ----------------------------------------------------------------------- cambios de opinión
    reserva("C01", "cambio de opinión", "Cambia la hora", CORTE, ANDRES, MANANA, H15, corrige=["mejor a las 4"], final={"h": H16}),
    reserva("C02", "cambio de opinión", "Cambia el día", CORTE, ANDRES, MANANA, H15, corrige=["no, pasado mañana"], final={"d": PASADO}),
    reserva("C03", "cambio de opinión", "Cambia el barbero", CORTE, ANDRES, MANANA, H15, corrige=["mejor con Julián"], final={"b": JULIAN}),
    reserva("C04", "cambio de opinión", "Cambia el servicio", CORTE, ANDRES, MANANA, H15, corrige=["mejor corte y barba"], final={"s": COMBO}),
    reserva("C05", "cambio de opinión", "Cambia el día y después la hora", CORTE, ANDRES, MANANA, H15,
            corrige=["mejor el viernes", "y que sea a las 5"], final={"d": VIERNES, "h": H17}),
    reserva("C06", "cambio de opinión", "Toca Cambiar y da otra hora", CORTE, ANDRES, MANANA, H15,
            corrige=["#cambiar", "a las 11"], final={"h": H11}),
    reserva("C07", "cambio de opinión", "Ve el resumen y se arrepiente", CORTE, ANDRES, MANANA, H15, confirma=False, queda=[]),
    reserva("C08", "cambio de opinión", "Cambia el día y la franja, y escoge hora", COMBO, JULIAN, MANANA, H10,
            corrige=["no, el sábado en la mañana"], final={"d": SABADO}),

    # ----------------------------------------------------------------------- turnos ocupados
    reserva("D01", "turno ocupado", "Escoge una de las horas cercanas", CORTE, ANDRES, MANANA, H15, agenda=[AJENA],
            si={"¿Te sirve alguna de estas?": "hor:15:30"}, final={"h": H1530}),
    reserva("D02", "turno ocupado", "Toma la primera hora que le ofrecen", CORTE, ANDRES, MANANA, H15, agenda=[AJENA],
            si={"¿Te sirve alguna de estas?": "primera"}, final={"h": hora(time(14, 30))}),
    reserva("D03", "turno ocupado", "No le sirve ninguna y lo deja", CORTE, ANDRES, MANANA, H15, agenda=[AJENA],
            si={"¿Te sirve alguna de estas?": "no, gracias"}, queda=con(AJENA)),
    reserva("D04", "turno ocupado", "Prefiere la misma hora con otro barbero", CORTE, ANDRES, MANANA, H15, agenda=[AJENA],
            si={"¿Te sirve alguna de estas?": "mejor con Julián"}, final={"b": JULIAN}),
    reserva("D05", "turno ocupado", "Sin preferencia: se le asigna el barbero libre", CORTE, LIBRE, MANANA, H15, dice="sdh",
            agenda=[AJENA], final={"b": JULIAN}),
    reserva("D06", "turno ocupado", "Los dos barberos ocupados a esa hora", CORTE, LIBRE, MANANA, H15,
            agenda=[AJENA, (2, 2, 2, "2026-10-14T15:00")], si={"¿Te sirve alguna de estas?": "hor:15:30"}, final={"h": H1530}),
    reserva("D07", "turno ocupado", "El barbero no tiene turnos ese día y pasa a otro", CORTE, JULIAN, SABADO, H10,
            agenda=JULIAN_LLENO, si={"¿Te sirve otro día?": "dia:2026-10-19"}, final={"d": LUNES}),
    reserva("D08", "turno ocupado", "El servicio largo se cruza con la cita siguiente", COMBO, ANDRES, MANANA,
            hora(time(14, 30), "a las 2 y media", "a las 2:30", "2:30 pm"), agenda=[AJENA],
            si={"¿Te sirve alguna de estas?": "hor:14:00"}, final={"h": H14}),

    # ----------------------------------------------------------------------- reprogramaciones
    Guion("E01", "reprogramación", "Pasa la cita del sábado para el lunes",
          ["cámbieme la del sábado para el lunes", "necesito pasar mi cita del sábado para el lunes",
           "ya no puedo el sábado, me la cambias para el lunes?"],
          quiere=["lunes 19 de octubre, 3:00 p. m."], agenda=[MIA], queda=con((1, 1, 1, "2026-10-19T15:00"))),
    Guion("E02", "reprogramación", "Corre la hora el mismo día",
          ["no alcanzo a llegar a las 3, me la corres para las 5?", "voy tarde, me cambias la cita de las 3 para las 5?",
           "puedes pasarme la cita para las 5 de la tarde?"],
          quiere=["miércoles 14 de octubre, 5:00 p. m."], agenda=[(1, 3, 2, "2026-10-14T15:00")],
          queda=con((1, 3, 2, "2026-10-14T17:00"))),
    Guion("E03", "reprogramación", "Cambia de barbero",
          ["quiero cambiar mi cita, que me atienda Julián", "puedo cambiar el barbero de mi cita? quiero con Julián",
           "cámbiame la cita con Julián"],
          quiere=["Corte clásico con Julián", "viernes 16 de octubre, 10:00 a. m."], agenda=[(1, 1, 1, "2026-10-16T10:00")],
          queda=con((1, 1, 2, "2026-10-16T10:00"))),
    Guion("E04", "reprogramación", "Cambia el día y la hora",
          ["necesito pasar mi cita para el viernes a las 11", "me cambias la cita para el viernes a las 11?",
           "quiero reprogramar mi cita para el viernes a las 11 de la mañana"],
          quiere=["viernes 16 de octubre, 11:00 a. m."], agenda=[(1, 1, 1, "2026-10-15T16:00")],
          queda=con((1, 1, 1, "2026-10-16T11:00"))),
    Guion("E05", "reprogramación", "Tiene dos citas y nombra cuál",
          ["pásame la cita del sábado para el viernes", "necesito cambiar la cita del sábado para el viernes",
           "la del sábado me la cambias para el viernes?"],
          quiere=["viernes 16 de octubre, 3:00 p. m."], agenda=[MIA, OTRA_MIA],
          queda=con((1, 1, 1, "2026-10-16T15:00"), OTRA_MIA)),
    Guion("E06", "reprogramación", "Tiene dos citas y el agente pregunta cuál",
          ["quiero cambiar mi cita para el jueves", "necesito pasar mi cita para el jueves",
           "me cambias la cita para el jueves?"],
          sabe={"cita": ([], "cita:2")}, quiere=["jueves 15 de octubre, 10:00 a. m."], agenda=[MIA, OTRA_MIA],
          queda=con(MIA, (1, 2, 2, "2026-10-15T10:00"))),
    Guion("E07", "reprogramación", "El turno nuevo está ocupado",
          ["pásame la cita para el jueves", "necesito cambiar mi cita para el jueves", "me corres la cita para el jueves?"],
          si={"¿Te sirve alguna de estas?": "hor:15:30"}, quiere=["jueves 15 de octubre, 3:30 p. m."],
          agenda=[(1, 1, 1, "2026-10-14T15:00"), (2, 1, 1, "2026-10-15T15:00")],
          queda=con((1, 1, 1, "2026-10-15T15:30"), (2, 1, 1, "2026-10-15T15:00"))),
    Guion("E08", "reprogramación", "Pide el cambio y se arrepiente",
          ["cámbiame la cita para el viernes", "quiero pasar mi cita para el viernes", "me cambias la cita para el viernes?"],
          confirma=False, agenda=[MIA], queda=con(MIA)),

    # ----------------------------------------------------------------------- cancelaciones
    Guion("F01", "cancelación", "Cancela su única cita",
          ["cancela mi cita", "quiero cancelar mi cita", "necesito cancelar la cita"],
          quiere=["sábado 17 de octubre, 3:00 p. m."], agenda=[MIA], queda=con(MIA, estado="CANCELADA")),
    Guion("F02", "cancelación", "Avisa que no puede ir",
          ["ya no voy a poder ir el sábado", "no puedo ir el sábado", "me salió algo y no voy a poder ir el sábado"],
          quiere=["sábado 17 de octubre, 3:00 p. m."], agenda=[MIA], queda=con(MIA, estado="CANCELADA")),
    Guion("F03", "cancelación", "Tiene dos citas y nombra cuál",
          ["cancela la del sábado", "quiero cancelar la cita del sábado", "ya no puedo ir el sábado, cancélala"],
          quiere=["sábado 17 de octubre, 3:00 p. m."], agenda=[MIA, OTRA_MIA],
          queda=con(MIA, estado="CANCELADA") + con(OTRA_MIA)),
    Guion("F04", "cancelación", "Tiene dos citas y el agente pregunta cuál",
          ["quiero cancelar mi cita", "cancela mi cita", "necesito cancelar una cita"],
          sabe={"cita": ([], "cita:2")}, quiere=["martes 20 de octubre, 10:00 a. m."], agenda=[MIA, OTRA_MIA],
          queda=con(MIA) + con(OTRA_MIA, estado="CANCELADA")),
    Guion("F05", "cancelación", "Pide cancelar y se arrepiente",
          ["cancela mi cita", "quiero cancelar la cita del sábado", "ya no voy a ir"],
          confirma=False, agenda=[MIA], queda=con(MIA)),
    Guion("F06", "cancelación", "Pide cancelar y no tiene citas",
          ["cancela mi cita", "quiero cancelar mi cita", "ya no voy a poder ir"], dice="No tienes citas programadas"),

    # ----------------------------------------------------------------------- consultas y fuera de alcance
    Guion("G01", "consulta", "Pregunta un precio",
          ["cuánto vale el corte y barba", "qué precio tiene el corte y barba?", "a cómo el corte y barba"], dice="$38.000"),
    Guion("G02", "consulta", "Pregunta por cupos",
          ["tiene cupo mañana en la tarde?", "hay turnos mañana por la tarde?", "qué horarios tienen mañana en la tarde"],
          dice="miércoles 14 de octubre"),
    Guion("G03", "consulta", "Pregunta por su cita",
          ["a qué hora es mi cita", "cuándo es mi cita?", "me recuerdas mi cita"],
          dice="sábado 17 de octubre, 3:00 p. m.", agenda=[MIA], queda=con(MIA)),
    Guion("G04", "fuera de alcance", "Pregunta por un producto",
          ["¿venden cera para el pelo?", "venden productos para la barba?", "tienen minoxidil"], agenda=[MIA], queda=con(MIA)),
    Guion("G05", "fuera de alcance", "Pide algo de otro negocio",
          ["quiero pedir una pizza para las 8", "necesito un taxi para las 5", "reserva una mesa para dos esta noche"]),
    Guion("G06", "fuera de alcance", "Conversa de otra cosa",
          ["quién ganó el partido anoche", "cuéntame un chiste", "qué clima va a hacer mañana"], agenda=[MIA], queda=con(MIA)),

    # ----------------------------------------------------------------------- segunda versión: lo que falló en Telegram
    Guion("H01", "registro colombiano", "El mensaje de la prueba en Telegram: descripción del corte y madrugada",
          ["oe bro estoy muy mechudo dame una cita para el 16 en la madrugada, quiero solo las puntas y el 7 con desvanecido.",
           "parce ando greñudo, agéndame pal 16 bien de madrugada, el 2 a los lados con desvanecido",
           "quiubo, me motila el viernes 16 en la madrugada? quiero el 7 con desvanecido"],
          sabe={"hor": ([], "hor:09:00"), "bar": (["cualquiera", "cualquiera de los dos", "me da igual"], "bar:0")},
          quiere=["Corte clásico con Andrés", "viernes 16 de octubre, 9:00 a. m."], queda=con((1, 1, 1, "2026-10-16T09:00"))),
    Guion("H02", "registro colombiano", "Corrige el día al ver el resumen",
          ["parce agéndame un corte con Andrés el jueves a las 10", "oe, un corte el jueves a las 10 con Andrés",
           "me motila el jueves a las 10? con Andrés"],
          corrige=["no bro la cita es para el 16"], quiere=["viernes 16 de octubre, 10:00 a. m."],
          queda=con((1, 1, 1, "2026-10-16T10:00"))),
    Guion("H03", "registro colombiano", "Toca «Cambiar algo» y corrige el día escribiendo",
          ["quiero un corte con Julián el jueves a las 11", "un corte el jueves a las 11 con Julián",
           "agéndame con Julián el jueves a las 11 pa motilarme"],
          corrige=["#cambiar", "la cita es para el 16"], quiere=["viernes 16 de octubre, 11:00 a. m."],
          queda=con((1, 1, 2, "2026-10-16T11:00"))),
    Guion("H04", "registro colombiano", "Contesta «cualquiera» a «¿con quién?»",
          ["oe, me agenda una motilada el viernes a las 11", "dame una cita el viernes a las 11 pa un corte",
           "le caigo el viernes a las 11 pa motilarme"],
          sabe={"bar": (["cualquiera", "cualquiera de los dos", "me da igual"], "bar:0")},
          quiere=["Corte clásico con Andrés", "viernes 16 de octubre, 11:00 a. m."], queda=con((1, 1, 1, "2026-10-16T11:00"))),
    Guion("H05", "registro colombiano", "Pregunta qué barberos hay y agenda con uno",
          ["que barberos hay disponibles?", "qué barberos hay?", "con quién puedo agendar?"],
          sabe={"bar": ([], "bar:2"), "srv": (["un corte", "una motilada"], "srv:1"),
                "dia": (["el sábado", "este sábado"], "dia:2026-10-17"), "hor": (["a las 10", "10 am"], "hor:10:00")},
          quiere=["Corte clásico con Julián", "sábado 17 de octubre, 10:00 a. m."], queda=con((1, 1, 2, "2026-10-17T10:00"))),
    Guion("H06", "registro colombiano", "Dice cómo quiere el corte con números y la fecha del mes",
          ["dame una cita pal 16 a las 4, quiero el 2 a los lados con desvanecido",
           "parce el 16 a las 4 pa un desvanecido en 0", "me agenda el 16 a las 4? es el 7 parejo"],
          sabe={"bar": (["cualquiera", "el que esté libre", "me da igual"], "bar:0")},
          quiere=["Corte clásico con Andrés", "viernes 16 de octubre, 4:00 p. m."], queda=con((1, 1, 1, "2026-10-16T16:00"))),
    Guion("H07", "registro colombiano", "Nombra dos días y escoge uno",
          ["quiero un corte el 16 o el 20 con Andrés a las 10", "un corte con Andrés a las 10, el 16 o el 20",
           "parce el 16 o el 20 a las 10 con Andrés pa un corte"],
          sabe={"dia": (["el 20", "el martes 20"], "dia:2026-10-20")},
          quiere=["Corte clásico con Andrés", "martes 20 de octubre, 10:00 a. m."], queda=con((1, 1, 1, "2026-10-20T10:00"))),
    Guion("H08", "registro colombiano", "Pide cambiar una cita que no tiene y agenda una nueva",
          ["cámbiame la cita para el viernes a las 4", "me corre la cita pal viernes a las 4?",
           "quiero pasar mi cita para el viernes a las 4"],
          sabe={"srv": (["un corte", "una motilada"], "srv:1"), "bar": (["cualquiera", "me da igual"], "bar:0")},
          quiere=["Corte clásico con Andrés", "viernes 16 de octubre, 4:00 p. m."], queda=con((1, 1, 1, "2026-10-16T16:00"))),
    Guion("H09", "registro colombiano", "Pide la madrugada con un barbero y toma el primer turno",
          ["necesito un corte el sábado bien de madrugada con Julián", "oe, el sábado de madrugada con Julián pa un corte",
           "un corte con Julián el sábado en la madrugada"],
          sabe={"hor": ([], "hor:09:00")},
          quiere=["Corte clásico con Julián", "sábado 17 de octubre, 9:00 a. m."], queda=con((1, 1, 2, "2026-10-17T09:00"))),
    Guion("H10", "registro colombiano", "Habla en registro colombiano de principio a fin",
          ["quiubo parce, me motila mañana a las 3 con Andrés?", "oe mi llave, le caigo mañana a las 3 pa motilarme con Andrés",
           "estoy muy mechudo, dame un turno mañana a las 3 con Andrés"],
          quiere=["Corte clásico con Andrés", "miércoles 14 de octubre, 3:00 p. m."], queda=con((1, 1, 1, "2026-10-14T15:00"))),
]
