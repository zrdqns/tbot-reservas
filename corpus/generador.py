"""Generador composicional de mensajes anotados.

Cada mensaje sale de un marco (una manera de pedir algo) que se rellena con realizaciones de las ranuras,
se envuelve con saludo o cortesía y pasa por un estilo de escritura (minúsculas, sin tildes, abreviaturas,
errores de tecleo). Las etiquetas se conservan porque el estilo se aplica por separado dentro y fuera de
cada ranura.
"""
import re

_PARTE = re.compile(r"(\[\w+ : [^\[\]]+\])")
_RANURA = re.compile(r"\[(\w+) : ([^\[\]]+)\]")


def r(tipo, valor):
    return f"[{tipo} : {valor}]"


def elegir(rng, pesos):
    valores, ws = zip(*pesos)
    return rng.choices(valores, weights=ws)[0]


# --------------------------------------------------------------------------- léxico

# (valor, artículo indefinido, artículo definido, peso). El catálogo real tiene corte clásico,
# arreglo de barba, corte y barba, y tinte; «otros» son servicios que la barbería no ofrece.
SERVICIOS = {
    "corte": [
        ("corte", "un", "el", 30), ("corte de pelo", "un", "el", 12), ("corte de cabello", "un", "el", 8),
        ("corte clásico", "un", "el", 8), ("corte sencillo", "un", "el", 3), ("corte normal", "un", "el", 3),
        ("motilada", "una", "la", 6), ("peluqueada", "una", "la", 2), ("corte a máquina", "un", "el", 2),
        ("corte a tijera", "un", "el", 2), ("degradado", "un", "el", 6), ("corte con degradado", "un", "el", 2),
        ("fade", "un", "el", 2), ("low fade", "un", "el", 1), ("mid fade", "un", "el", 1),
        ("desvanecido", "un", "el", 1), ("corte de caballero", "un", "el", 1), ("corte de hombre", "un", "el", 1),
    ],
    "barba": [
        ("barba", "", "la", 14), ("arreglo de barba", "un", "el", 10), ("perfilado de barba", "un", "el", 4),
        ("afeitada", "una", "la", 3), ("afeitado", "un", "el", 3), ("arreglo de la barba", "un", "el", 2),
        ("retoque de barba", "un", "el", 1), ("perfilada de barba", "una", "la", 1),
    ],
    "combo": [
        ("corte y barba", "un", "el", 16), ("corte con barba", "un", "el", 5), ("corte más barba", "", "", 2),
        ("corte + barba", "", "", 1), ("corte de pelo y barba", "un", "el", 3),
        ("combo de corte y barba", "un", "el", 2), ("pelo y barba", "", "", 2), ("cabello y barba", "", "", 1),
        ("motilada y barba", "una", "la", 1), ("corte y arreglo de barba", "un", "el", 2),
    ],
    "tinte": [
        ("tinte", "un", "el", 8), ("tintura", "una", "la", 3), ("decoloración", "una", "la", 1),
        ("mechas", "unas", "las", 1), ("rayitos", "unos", "los", 1),
    ],
    "otros": [
        ("cejas", "", "las", 3), ("arreglo de cejas", "un", "el", 2), ("diseño de cejas", "un", "el", 1),
        ("limpieza facial", "una", "la", 2), ("mascarilla", "una", "la", 2), ("keratina", "una", "la", 2),
        ("alisado", "un", "el", 1), ("corte de niño", "un", "el", 3), ("corte para niño", "un", "el", 1),
        ("diseño", "un", "el", 1), ("lavado", "un", "el", 1), ("masaje capilar", "un", "el", 1),
        ("trenzas", "unas", "las", 1), ("tatuaje", "un", "el", 1),
    ],
}
GRUPOS = [("corte", 40), ("barba", 18), ("combo", 22), ("tinte", 8), ("otros", 12)]

# (infinitivo con «me», infinitivo, subjuntivo, peso)
VERBOS = [
    ("cortarme el pelo", "cortar el pelo", "corten el pelo", 14),
    ("cortarme el cabello", "cortar el cabello", "corten el cabello", 5),
    ("motilarme", "motilar", "motilen", 10), ("peluquearme", "peluquear", "peluqueen", 3),
    ("arreglarme la barba", "arreglar la barba", "arreglen la barba", 8),
    ("afeitarme", "afeitar", "afeiten", 4),
    ("perfilarme la barba", "perfilar la barba", "perfilen la barba", 2),
    ("hacerme la barba", "hacer la barba", "hagan la barba", 3),
    ("cortarme el pelo y la barba", "cortar el pelo y la barba", "corten el pelo y la barba", 4),
    ("cortarme el pelo y arreglarme la barba", "cortar el pelo y arreglar la barba",
     "corten el pelo y arreglen la barba", 3),
    ("motilarme y arreglarme la barba", "motilar y arreglar la barba", "motilen y arreglen la barba", 2),
    ("tinturarme el pelo", "tinturar el pelo", "tinturen el pelo", 2),
    ("pintarme el pelo", "pintar el pelo", "pinten el pelo", 1),
    ("hacerme un degradado", "hacer un degradado", "hagan un degradado", 3),
    ("hacerme las cejas", "hacer las cejas", "hagan las cejas", 1),
    ("retocarme la barba", "retocar la barba", "retoquen la barba", 1),
    ("despuntarme el pelo", "despuntar el pelo", "despunten el pelo", 2),
    ("rebajarme el pelo", "rebajar el pelo", "rebajen el pelo", 1),
    ("raparme", "rapar", "rapen", 1),
]

# Cómo quiere el corte. La descripción va completa en la ranura servicio, con el número de la guarda y su
# artículo («el 7 con desvanecido»), porque el agente se la pasa al barbero como observación de la cita.
BASES = [("desvanecido", 10), ("degradado", 7), ("fade", 4), ("low fade", 2), ("mid fade", 2), ("taper", 1),
         ("corte", 5), ("rapado", 1), ("motilada", 1)]
GUARDAS = [0, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6, 7, 8]
LADOS = ["a los lados", "en los lados", "a los costados", "abajo"]
RETOQUES = [
    "solo las puntas", "solo las puntas", "las puntas", "las puntitas", "despuntar", "solo despuntar",
    "emparejar", "solo emparejar", "rebajar un poquito", "rebajar los lados", "bajito a los lados",
    "la nuca y los lados", "solo los lados", "a ras", "con tijera", "solo tijera", "largo arriba",
    "el cerquillo", "marcar la línea", "perfilar la línea", "la raya", "el contorno", "solo las patillas",
]

# Lo que dice el cliente antes de pedir la cita y que no la describe: no se anota
CONTEXTOS = [
    "estoy muy mechudo", "ando muy mechudo", "estoy muy greñudo", "ya parezco un oso", "estoy hecho un oso",
    "tengo el pelo hecho un desastre", "ya me toca", "la barba ya está muy larga", "tengo una entrevista",
    "tengo un matrimonio", "tengo grado", "voy para una fiesta", "quiero quedar bien pinta",
    "ando todo despelucado", "el pelo ya me está estorbando", "ando muy peludo",
]

CATALOGO = ["Andrés", "Julián", "Felipe", "Camilo"]
CATALOGO_COMPLETO = ["Andrés Rojas", "Julián Mora", "Felipe Cárdenas"]
NOMBRES = [
    "Carlos", "Juan", "Sebastián", "Santiago", "David", "Daniel", "Mateo", "Nicolás", "Alejandro", "Esteban",
    "Jhon", "Brayan", "Kevin", "Cristian", "Óscar", "Jorge", "Luis", "Diego", "Mauricio", "Fabián", "Iván",
    "Wilson", "Edwin", "Yeison", "Stiven", "Duván", "Harold", "Jairo", "Miguel", "Samuel", "Tomás", "Jerónimo",
    "Juan Pablo", "Juan David", "Juan Camilo", "Luis Fernando", "José", "Ricardo", "Germán", "Hernán", "Álvaro",
    "Fernando", "Gustavo", "Leonardo", "Anderson", "Jefferson", "Maicol", "Emanuel", "Simón", "Martín", "Pablo",
    "Manuel", "Víctor", "César", "Rubén", "Néstor", "Alexander", "Giovanny", "Freddy", "William", "Arley",
    "Yesid", "Ferney", "Dairo", "Elkin", "Andrés", "Julián", "Felipe", "Camilo",
    "Laura", "Paola", "Andrea", "Natalia", "Carolina", "Valentina", "Daniela", "Camila", "María", "Luisa",
    "Sofía", "Diana", "Sara", "Juliana", "Tatiana", "Lina", "Marcela", "Angie", "Yuliana", "Karen",
]
APODOS = [
    "Pipe", "Juli", "Sebas", "Cami", "Santi", "Nico", "Alejo", "Dani", "Juancho", "Mao", "Migue", "Tavo",
    "Lucho", "Juanpa", "Juanda", "Cris", "Fer", "Leo", "Memo", "Toño", "Pacho", "Chucho", "Beto", "Nacho",
    "Rafa", "Tato", "Kike",
]
APELLIDOS = [
    "Rojas", "Mora", "Cárdenas", "Gómez", "Rodríguez", "Martínez", "López", "García", "Hernández", "Ramírez",
    "Torres", "Díaz", "Vargas", "Castro", "Ortiz", "Moreno", "Jiménez", "Rincón", "Suárez", "Giraldo",
    "Restrepo", "Zapata", "Ospina", "Quintero", "Vanegas", "Paternina", "Guzmán", "Lozano", "Barrero", "Tovar",
    "Sánchez", "Peña", "Acosta", "Pérez", "Cortés", "Medina", "Trujillo", "Bonilla", "Parra", "Salazar",
]
SIN_PREFERENCIA = [
    "cualquiera", "cualquiera", "cualquiera", "el que esté libre", "el que esté disponible", "el que sea",
    "el que esté", "el de siempre", "el de siempre", "el mismo de siempre", "el mismo de la otra vez",
    "el que me atendió la vez pasada", "quien esté libre", "cualquiera de los dos", "el que haya",
    "quien sea", "cualquier barbero", "el que esté desocupado", "el que tenga espacio",
]
# Respuestas sueltas a «¿con quién?» cuando no tiene preferencia
CUALQUIERA = ["cualquiera", "cualquiera", "cualquiera", "cualquiera de los dos", "el que esté libre", "el que sea",
              "quien sea", "el que haya", "cualquier barbero", "el que esté desocupado", "cualquiera de ellos"]

DIAS = [("lunes", 10), ("martes", 12), ("miércoles", 13), ("jueves", 14), ("viernes", 18), ("sábado", 25),
        ("domingo", 8)]
MESES = [("octubre", 6), ("noviembre", 6), ("diciembre", 5), ("enero", 3), ("febrero", 1), ("marzo", 1),
         ("abril", 1), ("mayo", 1), ("junio", 1), ("julio", 1), ("agosto", 1), ("septiembre", 1)]
PALABRA = {1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho",
           9: "nueve", 10: "diez", 11: "once", 12: "doce"}
DIA_PALABRA = {1: "primero", 2: "dos", 3: "tres", 5: "cinco", 8: "ocho", 10: "diez", 12: "doce", 14: "catorce",
               15: "quince", 16: "dieciséis", 18: "dieciocho", 20: "veinte", 22: "veintidós", 24: "veinticuatro",
               25: "veinticinco", 28: "veintiocho", 30: "treinta"}
HABITUALES = ["los domingos", "los domingos", "los sábados", "los festivos", "los lunes", "los fines de semana",
              "entre semana"]
AHORA = ["ahorita", "ahorita", "ahora", "ahora mismo", "ya mismo", "en media hora", "en una hora",
         "en 20 minutos"]

SALUDOS = [
    "hola", "hola", "hola", "buenas", "buenas", "buenas tardes", "buenos días", "buen día", "buenas noches",
    "hola buenas", "hola buenas tardes", "hola buenos días", "qué más", "quiubo", "hola qué tal", "hey", "ey",
    "holi", "hola cómo estás", "hola cómo van", "buenas buenas", "qué hubo", "saludos", "hola muy buenas",
    "oe", "oe", "oe parce", "oiga", "quiubo parce", "qué más pues", "qué hubo pues", "epa", "ey parce",
    "qué más mi llave", "buenas mi rey", "hola hola", "buenas parcero", "quiubo pues", "ole",
]
VOCATIVOS = ["parce", "parcero", "bro", "hermano", "amigo", "viejo", "mijo", "socio", "llave", "crack", "compa",
             "veci", "mi llave", "pana", "papá", "maestro", "jefe", "mi hermano", "manito", "mi rey", "brother"]
ENTRADAS = ["una pregunta, ", "una consulta, ", "oye, ", "disculpa, ", "qué pena, ", "qué pena la molestia, ",
            "una preguntica, "]
CORTESIAS = ["por favor", "por favor", "porfa", "porfa", "porfis", "gracias", "gracias", "muchas gracias",
             "mil gracias", "si me haces el favor", "si es tan amable", "te lo agradezco", "quedo atento",
             "porfa, gracias", "plis", "hágame el favor", "le agradezco", "Dios le pague", "porfa parce"]
CORTESIAS_DENTRO = {"por favor", "porfa", "porfis", "plis"}
EMOJIS = ["🙏", "💈", "👍", "😅", "😊", "🙌", "👌", "😎", "🔥", "💇"]


# --------------------------------------------------------------------------- ranuras

def _servicio(rng, grupos=GRUPOS):
    valor, indef, defin, _ = elegir(rng, [(s, s[3]) for s in SERVICIOS[elegir(rng, grupos)]])
    return valor, indef, defin


def s_bare(rng):
    return r("servicio", _servicio(rng)[0])


def s_indef(rng):
    """«un corte», «una motilada», «la barba», «un desvanecido con el 2 a los lados»."""
    if rng.random() < .12:
        base, descripcion = _con_base(rng)
        return f"{'una' if base == 'motilada' else 'un'} {r('servicio', descripcion)}"
    valor, indef, defin = _servicio(rng)
    art = indef or (defin if rng.random() < .5 else "")
    return f"{art} {r('servicio', valor)}".strip()


def s_def(rng):
    """«el corte», «la barba»."""
    valor, _, defin = _servicio(rng)
    return f"{defin} {r('servicio', valor)}".strip()


def s_de(rng):
    """«del corte», «de la barba»."""
    valor, _, defin = _servicio(rng)
    prep = {"el": "del", "": "de"}.get(defin, f"de {defin}")
    return f"{prep} {r('servicio', valor)}"


def s_para(rng):
    """Lo que sigue a «cita para»: «corte», «un corte», «cortarme el pelo»."""
    x = rng.random()
    if x < .40:
        return s_bare(rng)
    if x < .72:
        return s_indef(rng)
    if x < .84:
        return s_detalle(rng)
    return s_verbo(rng)


def s_otro(rng):
    """Servicio por el que se pregunta si lo hacen: «tinte», «cejas»."""
    return r("servicio", _servicio(rng, [("tinte", 30), ("otros", 50), ("barba", 10), ("corte", 10)])[0])


def dos_servicios(rng):
    """«el corte y la barba»: dos servicios con artículo, cada uno en su tramo."""
    a, b = rng.sample(["corte", "barba", "tinte", "otros"], 2)
    partes = []
    for grupo in (a, b):
        valor, _, defin = elegir(rng, [(s, s[3]) for s in SERVICIOS[grupo] if s[2]])[:3]
        partes.append(f"{defin} {r('servicio', valor)}")
    return f"{partes[0]} {rng.choice(['y', 'y', 'o'])} {partes[1]}"


def _verbo(rng):
    return elegir(rng, [(v, v[3]) for v in VERBOS])


def s_verbo(rng):
    return r("servicio", _verbo(rng)[0])


def s_verbo_inf(rng):
    return r("servicio", _verbo(rng)[1])


def s_verbo_subj(rng):
    return r("servicio", _verbo(rng)[2])


def s_verbo_se(rng):
    return r("servicio", re.sub(r"(ar|er|ir)me\b", r"\1se", _verbo(rng)[0]))


def _con_base(rng):
    """Descripción que empieza por el tipo de corte: «desvanecido con el 2 a los lados»."""
    n, base, lado = rng.choice(GUARDAS), elegir(rng, BASES), rng.choice(LADOS)
    return base, elegir(rng, [
        (f"{base} en {n}", 8), (f"{base} con el {n} {lado}", 8), (f"{base} bajito", 4), (f"{base} alto", 2),
        (f"{base} con raya", 3), (f"{base} con línea", 2), (f"{base} y largo arriba", 2),
        (f"{base} con el {n} y tijera arriba", 2)])


def _detalle(rng):
    n, lado = rng.choice(GUARDAS), rng.choice(LADOS)
    fade = elegir(rng, [b for b in BASES if b[0] not in ("corte", "rapado", "motilada")])
    return elegir(rng, [
        (f"el {n} con {fade}", 12), (_con_base(rng)[1], 30), (f"el {n} {lado}", 7),
        (f"el {n} {lado} y tijera arriba", 3), (f"el {n} parejo", 3), (f"todo al {n}", 2), (rng.choice(RETOQUES), 26),
    ])


def s_detalle(rng):
    """«el 7 con desvanecido», «solo las puntas», «degradado con el 2 a los lados»."""
    return r("servicio", _detalle(rng))


def dos_detalles(rng):
    """«solo las puntas y el 7 con desvanecido»: dos descripciones, cada una en su tramo."""
    return f"{s_detalle(rng)} y {s_detalle(rng)}"


def b_libre(rng):
    """Respuesta suelta de quien no tiene preferencia de barbero."""
    return r("barbero", rng.choice(CUALQUIERA))


def _barbero(rng):
    x = rng.random()
    if x < .40:
        return rng.choice(CATALOGO)
    if x < .80:
        return rng.choice(NOMBRES)
    if x < .91:
        return rng.choice(APODOS)
    return rng.choice(CATALOGO_COMPLETO + [f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"])


def b_nombre(rng):
    return r("barbero", _barbero(rng))


def b_pila(rng):
    """Solo el nombre de pila o el apodo: un nombre suelto con apellido se lee como el del cliente."""
    return r("barbero", _barbero(rng).split()[0])


def barbero(rng):
    if rng.random() < .12:
        return "con " + r("barbero", rng.choice(SIN_PREFERENCIA))
    b = b_nombre(rng)
    return elegir(rng, [(f"con {b}", 72), (f"con el barbero {b}", 6), (f"con don {b}", 4),
                        (f"que me atienda {b}", 8), (f"con {b} si se puede", 5), (f"y que me atienda {b}", 3),
                        (f"donde {b}", 2)])


def n_solo(rng, apellido=None):
    """El nombre del cliente: «Daniel», «Daniel Vanegas»."""
    persona = rng.choice(NOMBRES)
    if apellido or (apellido is None and rng.random() < .45):
        persona += " " + rng.choice(APELLIDOS)
    return r("nombre", persona)


def nombre(rng):
    n = n_solo(rng)
    return elegir(rng, [(f"a nombre de {n}", 45), (f"queda a nombre de {n}", 8), (f"de parte de {n}", 6),
                        (f"es para mi hijo {n}", 8), (f"es para mi hermano {n}", 5), (f"la cita es para {n}", 8),
                        (f"soy {n}", 12), (f"mi nombre es {n}", 8)])


def _fecha(rng, dia=False):
    """(artículo, núcleo): «el» + «sábado», «» + «mañana». Con dia=True no devuelve semanas."""
    d, mes, n = elegir(rng, DIAS), elegir(rng, MESES), rng.randint(1, 30)
    opciones = [
        (("", "hoy"), 10), (("", "mañana"), 21), (("", "pasado mañana"), 5), (("", "hoy mismo"), 1),
        (("", "mañana mismo"), 1), (("el", d), 22), (("", f"este {d}"), 7), (("el", f"próximo {d}"), 5),
        (("el", f"otro {d}"), 4), (("el", f"{d} que viene"), 3), (("el", f"{d} {n}"), 3),
        (("el", f"{d} {n} de {mes}"), 2), (("el", f"{d} de la otra semana"), 2),
        (("el", f"{d} de esta semana"), 1), (("el", f"{n}"), 9), (("el", f"{n} de {mes}"), 6),
        (("el", f"{n} de este mes"), 1), (("el", f"primero de {mes}"), 1),
        (("el", f"{n}/{rng.randint(10, 12)}"), 1), (("el", rng.choice(list(DIA_PALABRA.values()))), 2),
        (("", f"mañana {n}"), 1), (("el", f"día {n}"), 1),
    ]
    if not dia:
        opciones += [
            (("", "esta semana"), 2), (("la", "otra semana"), 2), (("la", "próxima semana"), 1),
            (("la", "semana que viene"), 1), (("la", "semana entrante"), 1), (("el", "fin de semana"), 2),
            (("", "este fin de semana"), 1),
        ]
    return elegir(rng, opciones)


def fecha(rng, forma="", dia=False):
    """forma: «» (el sábado), «para» (para el sábado) o «de» (del sábado)."""
    art, nucleo = _fecha(rng, dia)
    if forma == "de":
        if art == "el":
            return f"del {r('fecha', nucleo)}"
        return f"de {r('fecha', f'{art} {nucleo}'.strip())}"
    if forma == "para" and art == "el" and rng.random() < .06:
        return f"pal {r('fecha', nucleo)}"
    tramo = r("fecha", f"{art} {nucleo}".strip())
    return f"para {tramo}" if forma == "para" else tramo


def f_habitual(rng):
    return r("fecha", rng.choice(HABITUALES)) if rng.random() < .5 else fecha(rng)


def dos_fechas(rng):
    if rng.random() < .35:
        a, b = rng.choice([("hoy", "mañana"), ("mañana", "pasado mañana"), ("hoy", "el sábado")])
    else:
        i = rng.randrange(6)
        a, b = f"el {DIAS[i][0]}", f"el {DIAS[i + 1][0]}"
    return f"{r('fecha', a)} o {r('fecha', b)}"


def _hora(rng, periodo=None, sufijo=True):
    """(artículo, núcleo): «las» + «3 de la tarde»."""
    periodo = periodo or elegir(rng, [("mañana", 30), ("tarde", 55), ("noche", 15)])
    h = rng.choice({"mañana": [8, 9, 10, 11], "tarde": [12, 1, 2, 3, 4, 5], "noche": [6, 7, 8]}[periodo])
    sufijos = {"mañana": ["am", "a.m.", "de la mañana"], "tarde": ["pm", "p.m.", "de la tarde"],
               "noche": ["pm", "de la noche"]}[periodo]
    if h == 12:
        sufijos = ["pm", "del día"]
    minutos = elegir(rng, [("", 62), (":30", 22), (":00", 10), (":15", 3), (":45", 3)])
    fraccion = elegir(rng, [("", 68), (" y media", 26), (" y cuarto", 6)])
    estilos = [("num", 34), ("pal", 14)]
    if sufijo:
        estilos += [("num_suf", 30), ("pal_suf", 9), ("24h", 5), ("pegado", 8)]
    estilo_hora = elegir(rng, estilos)
    art = "la" if h == 1 else "las"
    if estilo_hora == "num":
        nucleo = f"{h}{minutos}"
    elif estilo_hora == "pal":
        nucleo = PALABRA[h] + fraccion
    elif estilo_hora == "num_suf":
        nucleo = f"{h}{minutos} {rng.choice(sufijos)}"
    elif estilo_hora == "pal_suf":
        nucleo = f"{PALABRA[h]}{fraccion} {sufijos[-1]}"
    elif estilo_hora == "24h":
        h24 = h if periodo == "mañana" or h == 12 else h + 12
        art, nucleo = "las", f"{h24}:{rng.choice(['00', '00', '30'])}"
    else:
        nucleo = f"{h}{minutos}{'am' if periodo == 'mañana' else 'pm'}"
    return art, nucleo


def hora(rng, forma="", periodo=None, sufijo=True):
    """forma: «» (a las 3, tipo 3), «para» (para las 3) o «de» (de las 3)."""
    if forma == "" and periodo is None:
        x = rng.random()
        if x < .06:
            return r("hora", rng.choice(["a mediodía", "al mediodía", "a medio día", "al medio día"]))
        if x < .10:
            return r("hora", rng.choice(["a primera hora", "a primera hora", "a última hora"]))
    art, nucleo = _hora(rng, periodo, sufijo)
    if forma:
        return f"{forma} {r('hora', f'{art} {nucleo}')}"
    solo = bool(re.search(r"[:a-z]", nucleo)) and nucleo[0].isdigit()
    intro = elegir(rng, [(f"a {art} ", 56), ("tipo ", 14), (f"como a {art} ", 5), (f"a eso de {art} ", 4),
                         (f"sobre {art} ", 3), (f"hacia {art} ", 2), (f"por ahí a {art} ", 2),
                         (f"tipo {art} ", 2), ("", 12 if solo else 0)])
    return r("hora", intro + nucleo)


def ahora(rng):
    return r("hora", rng.choice(AHORA))


def _franja(rng, sola=True):
    """(tramo, tramo tras «para», periodo). Con sola=False no devuelve «esta tarde»."""
    h = rng.choice([4, 5, 6])
    opciones = [
        (("en la mañana", "la mañana", "mañana"), 14), (("por la mañana", "la mañana", "mañana"), 9),
        (("en horas de la mañana", "la mañana", "mañana"), 2), (("en la tarde", "la tarde", "tarde"), 22),
        (("por la tarde", "la tarde", "tarde"), 14), (("en horas de la tarde", "la tarde", "tarde"), 3),
        (("en la tardecita", "la tardecita", "tarde"), 2), (("en la noche", "la noche", "noche"), 6),
        (("por la noche", "la noche", "noche"), 4), (("temprano", None, None), 6),
        (("tempranito", None, None), 2), (("bien temprano", None, None), 2),
        (("después del almuerzo", None, None), 3), (("antes del almuerzo", None, None), 1),
        (("después del mediodía", None, None), 2), (("antes del mediodía", None, None), 2),
        ((f"después de las {h}", None, None), 4), ((f"después de las {h} de la tarde", None, None), 1),
        ((f"antes de las {rng.choice([10, 11, 12])}", None, None), 2), (("a media mañana", None, None), 1),
        (("a media tarde", None, None), 1), (("al final de la tarde", None, None), 1),
        (("en la madrugada", "la madrugada", None), 2), (("de madrugada", None, None), 1),
        (("bien de madrugada", None, None), 1), (("a la hora del almuerzo", None, None), 1),
    ]
    if sola:
        opciones += [(("esta tarde", None, None), 3), (("esta noche", None, None), 1)]
    return elegir(rng, opciones)


def franja(rng, forma="", sola=True):
    tramo, tras_para, _ = _franja(rng, sola)
    if forma == "para" and tras_para:
        return f"para {r('franja', tras_para)}"
    if forma == "para" and not tramo.startswith(("a ", "al ")):
        return f"para {r('franja', tramo)}"
    return r("franja", tramo)


def tiempo(rng, para=None, ahora_ok=True):
    """Fecha, hora y franja combinadas en un orden natural: «mañana a las 3», «el sábado en la tarde»."""
    if para is None:
        para = rng.random() < .30
    p = "para" if para else ""
    tipo = elegir(rng, [("F", 30), ("FH", 30), ("FJ", 17), ("H", 8), ("J", 5), ("FJH", 5),
                        ("A", 5 if ahora_ok and not para else 0)])
    if tipo == "A":
        return ahora(rng)
    if tipo == "F":
        return fecha(rng, p)
    if tipo == "H":
        return hora(rng, p)
    if tipo == "J":
        return franja(rng, p)
    if tipo == "FH":
        if not para and rng.random() < .15:
            return f"{hora(rng)} {fecha(rng, dia=True)}"
        return f"{fecha(rng, p, dia=True)} {hora(rng)}"
    if tipo == "FJ":
        return f"{fecha(rng, p)} {franja(rng, sola=False)}"
    tramo, _, periodo = elegir(rng, [(f, 1) for f in [
        ("en la mañana", None, "mañana"), ("por la mañana", None, "mañana"), ("en la tarde", None, "tarde"),
        ("por la tarde", None, "tarde"), ("en la noche", None, "noche")]])
    return f"{fecha(rng, p, dia=True)} {r('franja', tramo)} {hora(rng, periodo=periodo, sufijo=False)}"


def cita_ref(rng):
    """Referencia a una cita que ya existe: «del viernes a las 3», «con Andrés»."""
    tipo = elegir(rng, [("F", 50), ("FH", 18), ("H", 8), ("FJ", 7), ("B", 9), ("FB", 8)])
    if tipo == "F":
        return fecha(rng, "de", dia=True)
    if tipo == "FH":
        return f"{fecha(rng, 'de', dia=True)} {hora(rng)}"
    if tipo == "H":
        return hora(rng, "de")
    if tipo == "FJ":
        return f"de {r('fecha', rng.choice(['hoy', 'mañana']))} {franja(rng, sola=False)}"
    if tipo == "B":
        return f"con {b_nombre(rng)}"
    return f"{fecha(rng, 'de', dia=True)} con {b_nombre(rng)}"


def complementos(rng):
    """Lo que acompaña a una petición de reserva: cuándo, con quién y a nombre de quién."""
    t, b, n, d = tiempo(rng), barbero(rng), nombre(rng), s_detalle(rng)
    return elegir(rng, [(t, 34), (f"{t} {b}", 20), (f"{b} {t}", 11), (b, 8), (f"{t}, {n}", 9),
                        (f"{t} {b}, {n}", 6), ("", 12), (f"{t}, {d}", 10), (f"{t} {b}, {d}", 4),
                        (f"{t}, quiero {d}", 3)])


def con_quien(rng):
    return elegir(rng, [(barbero(rng), 45), (f", {nombre(rng)}", 10), ("", 45)])


RELLENOS = {
    "S": s_indef, "S0": s_para, "SD": s_def, "SDD": s_de, "SB": s_bare, "SO": s_otro, "S2": dos_servicios,
    "SV": s_verbo, "SR": s_verbo_inf, "SS": s_verbo_subj, "SE": s_verbo_se, "D": s_detalle, "D2": dos_detalles,
    "B": barbero, "BN": b_nombre, "BP": b_pila, "BL": b_libre, "N": nombre, "NN": lambda rng: n_solo(rng, True),
    "F": fecha, "FD": lambda rng: fecha(rng, "de", dia=True), "FH": f_habitual, "F2": dos_fechas,
    "H": hora, "J": franja,
    "T": tiempo, "T0": lambda rng: tiempo(rng, para=False),
    "TP": lambda rng: tiempo(rng, para=True, ahora_ok=False), "TD": cita_ref,
    "X": complementos, "XB": con_quien,
}


# --------------------------------------------------------------------------- marcos

RESERVAR = [
    # con el servicio como sustantivo
    "quiero {S} {X}", "quisiera {S} {X}", "necesito {S} {X}", "me gustaría agendar {S} {X}",
    "quiero agendar {S} {X}", "quiero reservar {S} {X}", "quiero pedir cita para {S0} {X}",
    "para agendar {S} {X}", "¿me agendas {S} {X}?", "me agenda {S} {X}", "agéndame {S} {X}",
    "agendame {S} {X}", "¿me puedes agendar {S} {X}?", "¿me puede agendar {S} {X}?",
    "¿será que me puedes agendar {S} {X}?", "¿me regalas una cita para {S0} {X}?",
    "me regala una cita para {S0} {X}", "¿me colaboras con una cita para {S0} {X}?",
    "me colabora con un turno para {S0} {X}", "quiero sacar cita para {S0} {X}",
    "quiero separar un turno para {S0} {X}", "necesito un turno para {S0} {X}",
    "necesito un cupo para {S0} {X}", "una cita para {S0} {X}", "cita para {S0} {X}", "{SB} {X}",
    "{T} quiero {S} {XB}", "{T} necesito {S} {XB}", "ando buscando {S} {X}", "me urge {S} {X}",
    "apártame un turno para {S0} {X}", "resérvame un turno para {S0} {X}", "anótame para {S0} {X}",
    "¿me anotas para {S0} {X}?", "ponme una cita para {S0} {X}", "¿me podés agendar {S} {X}?",
    # con el servicio como verbo
    "quiero {SV} {X}", "necesito {SV} {X}", "quisiera {SV} {X}", "quiero ir a {SV} {X}",
    "me quiero {SR} {X}", "me tengo que {SR} {X}, ¿me agendas?", "tengo que {SV} {X}, ¿me das una cita?",
    "me toca {SV} {X}, ¿me regalas un turno?", "necesito que me {SS} {X}", "para {SV} {X}",
    "cita para {SV} {X}", "quiero una cita para {SV} {X}", "voy a ir a {SV} {X}, sepárame el turno",
    # sin servicio
    "quiero una cita {X}", "necesito una cita {X}", "quiero agendar una cita {X}", "quiero reservar {X}",
    "quiero pedir una cita {X}", "quiero sacar una cita {X}", "¿me regalas una cita {X}?",
    "me regala un turno {X}", "necesito un turno {X}", "necesito agendar {X}", "quiero apartar un turno {X}",
    "agéndame una cita {X}", "¿me agendas {X}?", "¿me puedes dar una cita {X}?", "¿me das una cita {X}?",
    "me da un turno {X}", "necesito cita {X}", "para pedir una cita {X}", "quiero un turno {X}",
    "ponme una cita {X}", "anótame {X}", "apúntame {X}", "sepárame un cupo {X}", "resérvame un turno {X}",
    "¿me puedes anotar {X}?", "una cita {X}", "voy {T0}, ¿me apartas el turno?", "paso {T0}, ¿me agendas?",
    "{T0} puedo ir, agéndame",
    # solo el servicio, sin cuándo
    "necesito {S}", "quiero {S}", "necesito {SV}", "quiero {SV}", "me toca {SV}", "ya me toca {SV}",
    "toca {SV}", "ya necesito {S}", "necesito {S} urgente", "quisiera {S}",
    # cómo quiere el corte
    "quiero {D} {X}", "quiero {S}, {D} {X}", "me hace {D} {X}", "quiero {D2} {X}", "necesito {D} {X}",
    "dame una cita {X}, quiero {D}", "dame una cita {X}, quiero {D2}", "{S} {D} {X}", "agéndame {S} {X}, {D}",
    "quiero que me haga {D} {X}", "para {D} {X}", "¿me hace {D} {T0}?", "{T0} quiero {D}",
    "necesito una cita {X} para {D}", "¿me puede hacer {D} {T0}?", "un turno {X}, es {D}",
    # como se habla en Colombia
    "dame una cita {X}", "deme un turno {X}", "regáleme una cita para {S0} {X}",
    "hágame el favor y me agenda {S} {X}", "le caigo {T0} pa {SV}", "caigo {T0}, ¿me tiene turno?",
    "¿me puede [servicio : motilar] {T0}?", "¿me [servicio : motila] {T0}?", "sepáreme un espacio {X}", "guárdeme un cupito {X}",
    "voy a pasar {T0} a {SV}, ¿me guarda el cupo?", "toca {SV}, ¿me agenda {X}?", "me toca [servicio : motilada] {X}",
    "agéndeme {S} {X}", "¿me agenda {S} {X}?", "¿me da un cupito {X}?", "¿me hace el favor y me anota {X}?",
    "pa {SV} {X}", "¿será que me puede [servicio : peluquear] {T0}?", "dame un cupo {X}", "regálame un turnito {X}",
]

# Respuestas a una pregunta del agente: solo traen datos
FRAGMENTOS = [
    "{T0}", "{T0}", "{T}", "{F}", "{H}", "{J}", "{B}", "{BP}", "{SB}", "{SD}", "{N}", "{N}", "{NN}",
    "{NN}", "mejor {T0}",
    "sería {T0}", "que sea {T0}", "entonces {T0}", "puede ser {T0}", "prefiero {T0}", "{T0} mejor",
    "no, mejor {T0}", "{T0} me queda bien", "{T0} si se puede", "{SB} {T0}", "{SB} {B}", "{T0} {B}",
    "{SB} {B} {T0}", "mejor {B}", "que sea {B}", "prefiero {B}", "mejor {SD}", "solo {SD}", "{SD} nomás",
    "sí, {B}", "listo, {T0}", "dale, {T0}", "{T0} está bien", "{S} {T0}", "{F2}",
    # sin preferencia de barbero
    "{BL}", "{BL}", "{BL}", "con {BL}", "{BL}, me da igual", "me da igual, {BL}", "{BL} está bien",
    "{BL}, el que sea", "pues {BL}",
    # correcciones mientras agenda
    "no, la cita es para {F}", "la cita es para {F}", "no, es para {F}", "no, era para {F}", "es para {F}",
    "te dije que {F}", "no, te dije {T0}", "era {T0}", "no, {T0}", "corrijo, {T0}", "perdón, {T0}",
    "me equivoqué, {T0}", "uy no, {T0}", "nada, mejor {T0}", "no, el corte es {D}", "{D}", "{D}", "{D2}",
    "y {D}", "que sea {D}", "el corte {D}", "no, la cita es {T0}",
]

REPROGRAMAR = [
    "necesito cambiar mi cita {TD?} {TP?}", "quiero cambiar la cita {TD?} {TP?}",
    "quiero reprogramar mi cita {TD?} {TP?}", "necesito reprogramar la cita {TD?} {TP?}",
    "necesito mover mi cita {TD?} {TP?}", "¿puedo mover la cita {TD?} {TP?}?",
    "¿me puedes cambiar la cita {TD?} {TP?}?", "¿me puede correr la cita {TD?} {TP?}?",
    "¿será que me cambias la cita {TD?} {TP?}?", "necesito reagendar {TP?}",
    "quiero reagendar mi cita {TD?} {TP?}", "me toca cambiar la cita {TD?} {TP?}",
    "¿hay forma de cambiar mi cita {TD?} {TP?}?", "¿se puede cambiar la cita {TD?} {TP?}?",
    "quiero pasar mi cita {TD?} {TP}", "quiero aplazar mi cita {TD?} {TP?}",
    "necesito aplazar la cita {TD?} {TP?}", "¿me corres la cita {TD?} {TP?}?", "córreme la cita {TD?} {TP}",
    "pásame la cita {TD?} {TP}", "cámbiame la cita {TD?} {TP?}", "muéveme la cita {TD?} {TP}",
    "necesito cambiar la hora de mi cita {TD?}", "quiero cambiar el día de mi cita {TD?}",
    "necesito correr mi cita {TD?} {TP?}", "¿puedo cambiar mi turno {TD?} {TP?}?",
    "quiero cambiar mi turno {TD?} {TP?}", "me toca mover el turno {TD?} {TP?}", "reprogramar cita {TP?}",
    "cambiar cita {TD?} {TP?}", "tengo cita {T0} y no puedo ir, ¿me la cambias {TP}?",
    "tengo cita {T0} pero me salió algo, ¿la puedo pasar {TP}?",
    "tengo una cita {T0} y no alcanzo a llegar, ¿me la corres {TP}?", "ya no puedo {T0}, ¿me la pasas {TP}?",
    "ya no puedo ir {T0}, mejor {T0}", "no voy a poder {T0}, ¿la podemos dejar {TP}?",
    "la cita {TD} la necesito {TP}", "la cita {TD} pásamela {TP}", "cámbieme la {TD} {TP}",
    "cámbiame la {TD} {TP}", "¿puedo pasar la cita {TD} {TP}?", "¿me puedes correr la cita {TD} {TP}?",
    "necesito que me cambien la cita {TP}", "me surgió algo {T0}, ¿me cambias la cita {TP}?",
    "¿puedo adelantar mi cita {TP}?", "¿puedo atrasar la cita {TP}?", "quiero adelantar la cita {TP}",
    "quiero cambiar la cita para que me atienda {BN}", "¿puedo cambiar el barbero de mi cita? quiero {B}",
    "en mi cita {TD?} mejor quiero {S}", "¿puedo cambiar mi cita a {SB}?", "pásamela {TP}", "córremela {TP}",
    "muévemela {TP}", "mi cita {TD} cámbiala {TP}", "se me cruzó algo {T0}, toca mover la cita {TP}",
    "ya no me sirve {T0}, ¿me la cambias?", "¿me la puedes dejar {TP}?", "reagéndame {TP}",
]

CANCELAR = [
    "quiero cancelar mi cita {TD?}", "necesito cancelar la cita {TD?}", "cancela mi cita {TD?}",
    "cancélame la cita {TD?}", "¿me cancelas la cita {TD?}?", "me cancela la cita {TD?}",
    "cancelar cita {TD?}", "quiero anular mi cita {TD?}", "anúlame la cita {TD?}",
    "ya no voy a poder ir {T0?}", "no voy a poder asistir {T0?}", "no puedo ir a la cita {TD?}",
    "no alcanzo a llegar a la cita {TD?}", "ya no necesito la cita {TD?}", "ya no voy a ir {T0?}",
    "borra mi cita {TD?}", "elimina mi cita {TD?}", "quita mi cita {TD?}", "me toca cancelar la cita {TD?}",
    "toca cancelar la cita {TD?}", "no voy a poder ir {T0?}, cancélala",
    "me salió un imprevisto y no puedo ir {T0?}", "cancela el turno que tenía {T0?}",
    "ya no quiero la cita {TD?}", "necesito cancelar el turno {TD?}", "libera mi turno {TD?}",
    "cancela la {TD}", "la cita {TD} cancélala", "la cita {TD} ya no la necesito",
    "tengo cita {T0} pero ya no voy a ir", "tengo cita {T0} y no puedo ir, cancélala",
    "tenía cita {T0} pero cancélala", "al final no voy a ir {T0?}", "ya me motilé, cancela la cita {TD?}",
    "me enfermé y no puedo ir {T0?}", "no cuenten conmigo {T0}", "quiero cancelar", "cancela todo",
    "¿puedo cancelar mi cita {TD?}?", "¿cómo hago para cancelar la cita {TD?}?", "cancélame el turno {TD?}",
    "ya no puedo ir {T0}", "no voy {T0}, cancela", "necesito cancelar {SD}", "cancela {SD} {TD?}",
]

DISPONIBILIDAD = [
    "¿hay cupo {T}?", "¿tienen cupo {T}?", "¿tiene cupo {T}?", "¿hay turnos {T}?",
    "¿tienen disponibilidad {T}?", "¿hay disponibilidad {T}?", "¿qué horarios tienen {F}?",
    "¿qué horas hay disponibles {F}?", "¿qué turnos hay {F}?", "¿a qué horas hay cupo {F}?",
    "¿{BN} está libre {T0}?", "¿{BN} tiene cupo {T}?", "¿{BN} trabaja {FH}?", "¿{BN} atiende {FH}?",
    "¿{BN} está {F}?", "¿quién está disponible {T0}?", "¿quién atiende {F}?", "¿hay alguien libre {T0}?",
    "¿tienen espacio {T}?", "¿hay campo {T}?", "¿hay campito {T}?", "¿alcanzo a {SV} {T0}?",
    "¿para cuándo hay cupo?", "¿cuándo hay cita disponible?", "¿cuál es la cita más cercana?",
    "¿cuándo es lo más pronto que me pueden atender?", "¿tienen algo {T}?", "¿hay algo libre {T}?",
    "¿están atendiendo {F}?", "¿atienden {FH}?", "¿abren {FH}?", "¿hasta qué hora atienden {FH?}?",
    "¿a qué hora abren {FH?}?", "¿a qué hora cierran {FH?}?", "¿están abiertos {FH?}?",
    "¿cómo están de agenda {F}?", "¿qué tan llenos están {F}?", "¿hay cupo para {S0} {T}?",
    "¿tienen turno para {S0} {T}?", "¿cómo está la agenda de {BN} {F}?", "¿{F} hay cupo?", "¿{T0} hay algo?",
    "¿{T0} tienen cupo {B?}?", "¿hay cupo {B} {T}?", "¿me pueden atender {T0}?", "¿me atienden {T0}?",
    "¿hay chance {T}?", "¿qué días atiende {BN}?", "¿qué días trabaja {BN}?", "¿{BN} cuándo tiene cupo?",
    "¿a qué hora tiene libre {BN} {F}?", "¿qué disponibilidad tiene {BN} {F}?",
    "quiero saber si hay cupo {T}", "quería saber si tienen turnos {T}", "averiguando si hay cupo {T}",
    "¿si voy {T0} me atienden?", "¿hay mucha gente {T0?}?", "¿está muy lleno {T0?}?",
    "¿qué horario manejan {FH?}?", "¿hay cupo?", "¿tienen agenda {T}?", "¿les queda algún turno {T}?",
    # qué barberos hay
    "¿qué barberos hay?", "¿qué barberos hay disponibles {T0?}?", "¿qué barberos tienen?",
    "¿quiénes son los barberos?", "¿con quién puedo agendar {T0?}?", "¿con quién me puedo [servicio : motilar] {T0?}?",
    "¿quién está trabajando {F?}?", "¿cuántos barberos hay?", "¿quién me puede atender {T0}?",
    "¿qué barbero está libre {T0}?", "¿los barberos quiénes son?", "¿qué barberos están {F}?",
]

SERVICIOS_PRECIOS = [
    "¿cuánto vale {SD}?", "¿cuánto cuesta {SD}?", "¿qué precio tiene {SD}?", "¿cuánto cobran por {SD}?",
    "¿a cómo {SD}?", "¿a cómo está {SD}?", "¿cuánto sale {SD}?", "¿en cuánto queda {SD}?",
    "¿en cuánto sale {SD}?", "¿qué valor tiene {SD}?", "precio {SDD}", "¿cuánto vale {SE}?",
    "¿cuánto cobran por {SR}?", "¿qué servicios tienen?", "¿qué servicios ofrecen?", "¿qué hacen ahí?",
    "¿qué servicios manejan?", "¿me pasas la lista de precios?", "¿me regalas los precios?", "precios",
    "lista de precios", "¿cuáles son los precios?", "¿cuánto se demora {SD}?", "¿cuánto dura {SD}?",
    "¿cuánto tiempo toma {SD}?", "¿hacen {SO}?", "¿manejan {SO}?", "¿tienen servicio de {SO}?",
    "¿también hacen {SO}?", "¿ustedes hacen {SO}?", "¿qué incluye {SD}?", "¿{SD} incluye lavado?",
    "¿cuánto vale {SD} con {BN}?", "¿tienen promociones?", "¿hay descuento para estudiantes?",
    "¿tienen algún combo?", "¿cuánto me sale {S2}?", "¿qué diferencia hay entre {S2}?", "info de precios",
    "información de los servicios", "quiero saber los precios", "quería preguntar cuánto vale {SD}",
    "¿{SD} cuánto vale?", "¿{SD} qué precio tiene?", "¿{SD} en cuánto sale?", "¿y {SD} cuánto?",
    "¿me das el precio {SDD}?", "¿cuál es el valor {SDD}?", "¿cuánto es {SD}?", "¿cuánto cobran {FH}?",
    "¿cuánto vale {S}?", "¿qué vale {S}?", "¿cuánto me cobran por {S}?", "¿cuánto se demoran con {SD}?",
    "¿{SD} lo hace {BN}?", "¿qué servicios hace {BN}?", "¿me cuentas qué servicios tienen y los precios?",
]

CITAS = [
    "¿a qué hora es mi cita?", "¿cuándo es mi cita?", "¿tengo cita {F}?", "¿cuándo me toca?",
    "¿a qué hora me toca {F?}?", "¿qué citas tengo?", "¿tengo alguna cita agendada?",
    "¿me recuerdas mi cita?", "¿me recuerdas a qué hora es mi cita?", "¿me confirmas la hora de mi cita?",
    "¿para cuándo quedó mi cita?", "¿con quién quedó mi cita?", "¿con quién me toca {F?}?",
    "¿a qué hora quedé {F}?", "¿sí quedó agendada mi cita?", "¿mi cita sigue en pie?",
    "quiero ver mis citas", "mis citas", "ver mi reserva", "¿cuál es mi próxima cita?",
    "se me olvidó a qué hora era mi cita", "no me acuerdo cuándo tengo la cita", "¿mi cita era {F2}?",
    "¿tengo cita con {BN} {F?}?", "¿mi cita {TD} a qué hora es?", "¿sí quedé {F}?",
    "¿a qué hora tengo que llegar {F}?", "¿me puedes decir cuándo tengo cita?", "¿qué tengo agendado {F?}?",
    "¿sí tengo cita {F}?", "¿mi cita es {F}?", "¿mi cita es {H}?", "¿me recuerdas con quién tengo la cita?",
    "¿para qué servicio quedó mi cita?", "consultar mi cita", "revisar mi cita", "¿ya quedó mi cita {TD}?",
    "¿me aparece alguna cita?", "¿todavía tengo la cita {TD}?", "¿cómo quedó mi reserva?",
    "¿la cita {TD} sí quedó?", "necesito saber la hora de mi cita", "¿la cita de mi hijo cuándo es?",
    "¿la cita es {F}, cierto?", "¿mi cita {TD} con quién es?", "¿tengo turno {F} o me equivoco?",
    "¿a qué hora era lo mío {F?}?", "¿el turno {TD} sí está confirmado?",
]

PLANTILLAS = {
    "reservar": RESERVAR, "reprogramar": REPROGRAMAR, "cancelar": CANCELAR,
    "consultar_disponibilidad": DISPONIBILIDAD, "consultar_servicios": SERVICIOS_PRECIOS,
    "consultar_citas": CITAS,
}

AFIRMAR = [
    "sí", "sí", "si", "sip", "sii", "sí señor", "sí claro", "claro", "claro que sí", "dale", "dale pues",
    "listo", "listo pues", "de una", "hágale", "hágale pues", "confirmo", "confirmado", "confirmar",
    "correcto", "eso es", "así es", "perfecto", "ok", "okey", "oki", "vale", "va", "bueno", "bien",
    "está bien", "así está bien", "me sirve", "me parece bien", "todo bien", "obvio", "por supuesto",
    "exacto", "de acuerdo", "así déjalo", "todo correcto", "confírmala", "agéndala", "agéndala así",
    "breve", "eso", "ajá", "sí sí", "esa", "esa está bien", "esa me sirve", "súper", "está perfecto", "hecho",
    "va pues", "sí está bien", "sí correcto", "sí por favor", "sí porfa", "me gusta", "quedamos así",
    "así quedamos", "de una vez", "tal cual", "eso mismo", "sí, esa", "confirma", "sí, todo bien",
    "así mismo", "ya", "ya quedó", "sí, agéndala", "sí, confírmala",
    "sisas", "sisas", "melo", "de una parce", "hágale pues", "dele", "dele pues", "fijo", "va que va",
    "listo mi llave", "bacano", "así está melo", "listo, ahí estaré", "sí, así", "listo, quedamos",
]
AFIRMAR_2 = ["dale", "listo", "confirmo", "así está bien", "perfecto", "de una", "todo bien", "correcto",
             "eso es", "confírmala", "agéndala así", "así déjala", "me sirve", "esa me sirve", "está perfecto",
             "hágale"]
NEGAR = [
    "no", "no", "noo", "no no", "nop", "nel", "nah", "no señor", "no quiero", "ya no", "eso no",
    "no es eso", "no, así no", "para nada", "negativo", "no, nada", "dejémoslo así", "mejor dejémoslo así",
    "olvídalo", "no la confirmes", "no está bien", "está mal", "no es correcto", "incorrecto", "eso está mal",
    "nada", "ninguna", "ninguno", "ninguna de esas", "ninguno me sirve", "no me sirve", "no me queda bien",
    "no puedo a esa hora", "esa no", "no, esa no", "que no", "tampoco", "ahora no", "después te aviso",
    "luego miro", "lo pienso y te aviso", "mejor después", "mejor lo dejamos ahí", "de ninguna manera",
    "claro que no", "obvio no", "creo que no", "me equivoqué", "no era así", "no, otra cosa", "así no era",
    "no es lo que pedí", "no me entendiste", "no, no es eso", "no, ya no", "ya no quiero", "paila",
    "no por ahora", "no, mejor después", "no, qué pena", "qué pena pero no", "no va", "nones",
    "no, me equivoqué", "esa hora no", "ese día no", "no así", "no confirmes", "no, espera", "espera, no",
    "aún no", "no todavía", "no estoy seguro, mejor no",
    "nanay", "nel parce", "ni de riesgos", "qué va", "no mano", "no hermano", "no, déjelo así", "no me cuadra",
    "esa no me cuadra", "nanay cucas", "no, así no me sirve",
]
NEGAR_2 = ["gracias", "mejor no", "así no", "todavía no", "eso no", "déjalo así", "olvídalo", "no era eso",
           "por ahora no", "mejor después", "nada"]


def rellenar(plantilla, rng):
    def sub(m):
        if m.group(2) and rng.random() < .45:
            return ""
        return RELLENOS[m.group(1)](rng)
    return limpiar(re.sub(r"\{(\w+)(\?)?\}", sub, plantilla))


def limpiar(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([?,.!])", r"\1", s)
    s = re.sub(r",\s*([?,])", r"\1", s)
    s = re.sub(r"¿\s+", "¿", s)
    return s.strip(" ,")


def envolver(cuerpo, rng):
    """Añade saludo, entrada o cortesía alrededor del mensaje."""
    inicio = ""
    if rng.random() < .30:
        inicio = rng.choice(SALUDOS)
        if rng.random() < .25:
            inicio += " " + rng.choice(VOCATIVOS)
        inicio += rng.choice([", ", ", ", " ", ". "])
    if cuerpo.startswith("¿") and rng.random() < .12:
        inicio += rng.choice(ENTRADAS)
    s = inicio + cuerpo
    x = rng.random()
    if x < .28:
        cortesia = rng.choice(CORTESIAS)
        if s.endswith("?") and cortesia in CORTESIAS_DENTRO and rng.random() < .5:
            s = f"{s[:-1]} {cortesia}?"
        elif s.endswith("?"):
            s = f"{s} {cortesia}"
        else:
            s += rng.choice([" ", ", "] if s.rstrip("]").endswith(".") else [" ", ", ", ". "]) + cortesia
    elif x < .34:
        vocativo = rng.choice(VOCATIVOS)
        s = f"{s[:-1]} {vocativo}?" if s.endswith("?") else f"{s} {vocativo}"
    return s


def afirmar(rng):
    return _respuesta(rng, AFIRMAR, AFIRMAR_2, "sí", ["gracias", "muchas gracias", "porfa", "por favor"])


def negar(rng):
    return _respuesta(rng, NEGAR, NEGAR_2, "no", ["gracias", "muchas gracias", "gracias de todas formas"])


def _respuesta(rng, bases, segundas, palabra, cierres):
    base = rng.choice(bases)
    x = rng.random()
    if x < .50:
        s = base
    elif x < .65:
        s = f"{base}, {rng.choice(cierres)}"
    elif x < .77:
        s = f"{base} {rng.choice(VOCATIVOS)}"
    elif x < .90:
        s = f"{palabra}, {rng.choice(segundas)}"
    else:
        s = f"{base}, {rng.choice(segundas)}"
    return estilo(s, rng)


# --------------------------------------------------------------------------- estilo de escritura

ABREVIATURAS = [
    (r"\bpor favor\b", ["porfa", "xfa", "porfis", "pf", "plis"]), (r"\bqu[eé]\b", ["q"]), (r"\bpara\b", ["pa"]),
    (r"\bporque\b", ["pq"]), (r"\btambi[eé]n\b", ["tb", "tmb"]), (r"\bpor\b", ["x"]),
    (r"\bbuenas\b", ["bnas"]), (r"\bbien\b", ["bn"]), (r"\bmuchas gracias\b", ["mil gracias", "mcs gracias"]),
]
MALAS = {
    "necesito": "nesecito", "hay": "ay", "quiero": "kiero", "cita": "sita", "hacen": "asen", "hola": "ola",
    "vale": "bale", "voy": "boy", "hoy": "oy", "sábado": "savado", "sabado": "savado", "viernes": "biernes",
    "barba": "barva", "corte": "korte", "hora": "ora", "ahorita": "aorita", "quisiera": "quiciera",
    "agendar": "ajendar", "cancelar": "canselar", "gracias": "grasias", "favor": "fabor", "cabello": "cabeyo",
    "servicio": "servisio", "precio": "presio", "cambiar": "canbiar", "entonces": "entonses",
    "hacer": "aser", "tienen": "tienem", "disponible": "disponivle", "mañana": "manana",
    "miércoles": "miercoles", "haber": "aver",
}
ALARGABLES = {"hola", "porfa", "gracias", "si", "sí", "buenas", "dale", "listo", "no", "urgente", "porfis",
              "ya", "bueno"}


def sin_tildes(s):
    return s.translate(str.maketrans("áéíóúÁÉÍÓÚüÜ", "aeiouAEIOUuU"))


def _por_partes(anotado, fuera, dentro=None):
    """Aplica una función al texto de fuera de las ranuras y otra (o la misma) al valor de cada ranura."""
    dentro = dentro or fuera
    salida = []
    for parte in _PARTE.split(anotado):
        m = _RANURA.fullmatch(parte)
        salida.append(r(m.group(1), dentro(m.group(2))) if m else fuera(parte))
    return "".join(salida)


def _cambiar_palabra(anotado, rng, elegible, cambio, solo_fuera=False):
    """Cambia una sola palabra del mensaje, dentro o fuera de las ranuras."""
    partes = _PARTE.split(anotado)
    candidatos = []
    for i, parte in enumerate(partes):
        m = _RANURA.fullmatch(parte)
        if m and solo_fuera:
            continue
        base, texto = (m.start(2), m.group(2)) if m else (0, parte)
        for w in re.finditer(r"[^\W\d_]+", texto):
            if elegible(w.group()):
                candidatos.append((i, base + w.start(), base + w.end()))
    if not candidatos:
        return anotado
    i, a, b = rng.choice(candidatos)
    partes[i] = partes[i][:a] + cambio(partes[i][a:b]) + partes[i][b:]
    return "".join(partes)


def _tecleo(palabra, rng):
    i = rng.randrange(1, len(palabra) - 1)
    op = rng.choice(["cambia", "quita", "repite"])
    if op == "cambia":
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]
    if op == "quita":
        return palabra[:i] + palabra[i + 1:]
    return palabra[:i] + palabra[i] + palabra[i:]


def _mayuscula_inicial(anotado):
    partes = _PARTE.split(anotado)
    for i, parte in enumerate(partes):
        m = _RANURA.fullmatch(parte)
        texto = m.group(2) if m else parte
        letra = re.search(r"[^\W\d_]", texto)
        if letra:
            texto = texto[:letra.start()] + texto[letra.start()].upper() + texto[letra.start() + 1:]
            partes[i] = r(m.group(1), texto) if m else texto
            break
    return "".join(partes)


def estilo(anotado, rng):
    """Reescribe el mensaje como lo teclearía alguien con cuidado, de forma normal o a la carrera."""
    tipo = elegir(rng, [("cuidado", 20), ("normal", 45), ("rapido", 35)])
    s = anotado
    if tipo == "cuidado":
        s = _mayuscula_inicial(s)
        s = _por_partes(s, lambda t: re.sub(r"([.?!] )([a-zñáéíóú])", lambda m: m.group(1) + m.group(2).upper(), t),
                        lambda t: t)
        if s[-1] not in "?!." and rng.random() < .4:
            s += "."
        return s

    rapido = tipo == "rapido"
    if rng.random() < (.92 if rapido else .60):
        s = _por_partes(s, str.lower)
    if rng.random() < (.88 if rapido else .45):
        s = _por_partes(s, sin_tildes)
    if rapido or rng.random() < .80:
        s = s.replace("¿", "").replace("¡", "")
    if rapido:
        if rng.random() < .45:
            s = s.replace("?", "")
        if rng.random() < .50:
            s = _por_partes(s, lambda t: t.replace(",", ""), lambda t: t)
        for patron, opciones in ABREVIATURAS:
            if rng.random() < .45:
                s = _por_partes(s, lambda t: re.sub(patron, rng.choice(opciones), t, flags=re.I), lambda t: t)
        if rng.random() < .08:
            s = _cambiar_palabra(s, rng, lambda w: w.lower() in ALARGABLES,
                                 lambda w: w + w[-1] * rng.randint(1, 3), solo_fuera=True)
    if rng.random() < (.18 if rapido else .04):
        s = _cambiar_palabra(s, rng, lambda w: MALAS.get(w.lower(), w.lower()) != w.lower(),
                             lambda w: MALAS[w.lower()])
    if rng.random() < (.10 if rapido else .03):
        s = _cambiar_palabra(s, rng, lambda w: len(w) >= 5, lambda w: _tecleo(w, rng))
    s = limpiar(s)
    if rng.random() < (.12 if rapido else .05):
        s += " " + rng.choice(EMOJIS)
    return s


def mensaje(intencion, plantilla, rng):
    """Mensaje anotado de una intención a partir de un marco."""
    cuerpo = rellenar(plantilla, rng)
    if plantilla in RESERVAR and rng.random() < .12:      # «estoy muy mechudo, ...»: contexto que no se anota
        cuerpo = rng.choice(CONTEXTOS) + rng.choice([", ", " ", ". "]) + cuerpo
    return estilo(envolver(cuerpo, rng), rng)
