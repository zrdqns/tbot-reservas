"""Estado y política del agente.

El clasificador dice qué quiere el cliente y qué datos trae; aquí se decide el siguiente paso con reglas:
preguntar lo que falta, consultar la agenda, ofrecer opciones o pedir confirmación. La API solo se llama
para escribir después de que el cliente confirma, y lo que se le informa es lo que la API devolvió.

El agente no sabe nada de Telegram: recibe textos, botones y contactos, y devuelve respuestas. Así se
puede probar entero desde la consola o desde las pruebas.
"""
import json
import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from . import config, fechas
from . import formato as f
from .barberia import (EL_DE_SIEMPRE, ErrorAPI, buscar_barbero, buscar_servicio, detalle, inicio, libres_a,
                       turnos)

MENU = [[("✂️ Agendar una cita", "menu:reservar")], [("📅 Mis citas", "menu:citas"), ("💵 Precios", "menu:servicios")],
        [("🕘 Horario", "menu:horario"), ("📞 Hablar con el barbero", "menu:barbero")]]
AVISO = ("¡Hola! Soy TBot, el asistente de la barbería. Soy un programa, no una persona, pero te ayudo a agendar, "
         "cambiar o cancelar tus citas.\n\n"
         "Para atenderte guardo tu nombre, tu cuenta de Telegram y tus citas. La primera vez que agendes te pido "
         "tu celular y tu documento, que quedan en el sistema de la barbería. También guardo los mensajes, sin "
         "tu nombre, para aprender a entenderte mejor, y cuando no entiendo uno lo consulto con un modelo de lenguaje "
         "externo, también sin tu nombre. Puedes borrar tus datos cuando quieras con /borrar.\n\n"
         "¿Me autorizas a tratar estos datos? (Ley 1581 de 2012)")
AYUDA = ("Escríbeme normal, como le hablarías a tu barbero. Por ejemplo:\n"
         "• «Parce, ¿me agenda un corte con Andrés mañana tipo 3?»\n"
         "• «¿Tiene cupo el sábado en la tarde?»\n"
         "• «Quiero un desvanecido con el 2 a los lados el viernes»\n"
         "• «Cámbieme la del sábado para el lunes»\n"
         "• «Ya no puedo ir mañana»\n"
         "• «¿Cuánto vale la barba?»\n\n"
         "Antes de agendar, cambiar o cancelar siempre te muestro cómo queda para que me confirmes.")
SALUDO = (r"(hola+|buenas|buen dia|buenos dias|buenas tardes|buenas noches|que mas|que hubo|quiubo|hey|ey|oe+|oiga|"
          r"epa|ole|saludos|holi)( .{0,25})?")
DESPEDIDA = r"\b(chao|adios|nos vemos|hasta luego|bye|nos pillamos|hasta pronto)\b"
VACIO = {"servicio": [], "barbero": [], "fecha": [], "hora": [], "franja": [], "nombre": []}
# Lo que el cliente cuenta de sí y un barbero le contestaría antes de agendar
CHARLA = [(r"mechud|grenud|despeluc|peludo|melena|parezco un oso|hecho un oso|pelo (muy )?largo|pelo hecho",
           "¡Uy, sí, toca darle una arreglada a ese pelo! "),
          (r"matrimonio|boda|grado|entrevista|fiesta|cumplean|evento|reunion importante",
           "¡Hay que llegar bien presentado! "),
          (r"barba (ya )?(esta )?(muy )?larga|barbudo", "¡Esa barba ya pide arreglo! ")]
# El servicio nombrado o dado por hecho en el mensaje, cuando el clasificador no marcó la ranura
SERVICIO_IMPLICITO = [
    ("corte", r"\bcort[aeo]|\bmotil|\bpeluque|\bpelo\b|cabello|degrad|\bfade\b|desvanec|taper|\bpuntas\b|rapad|"
              r"mechud|grenud|despeluc|parezco un oso|hecho un oso|\bmelena\b"),
    ("barba", r"\bbarb|afeit"),
]
PEDIR_NUMERO = ("Toca el botón «📱 Compartir mi número» que te aparece abajo 👇\n"
                "(En el computador se abre con el ícono de los cuadritos, al lado del emoji.)")
CAMBIOS = [[("📅 Día", "cam:dia"), ("🕘 Hora", "cam:hora")], [("💈 Barbero", "cam:barbero"), ("✂️ Servicio", "cam:servicio")]]
# «La que tengas», «cualquier día», «la más tarde que tengas»: el cliente deja que el agente escoja el día o la hora
LA_QUE_SEA = (r"\bcualquier(a| hora| dia)?\b|\b(la|el) que (tengas|tenga|haya|sea|quieras|este libre|te quede|me des)\b|"
              r"\bme da igual\b|\bno importa\b|\bda lo mismo\b|\b(la|el|lo) (mas )?(pronto|temprano)\b|\b(la|el) primer[oa]?\b|"
              r"\bcuando (tengas|haya|puedas)\b")
LA_ULTIMA = r"\b(la|lo) (mas )?tarde (que|posible)\b|\bla ultima\b"
NO_SE = r"(no se|ni idea|no estoy seguro|no tengo idea|todavia no se|aun no se)( todavia| la verdad| bien)?"
PRONTO = (r"\blo (mas )?pronto( posible)?\b|\bcuanto antes\b|\blo antes posible\b|\bapenas (puedas|pueda|se pueda|haya)\b|"
          r"\bel primer (turno|espacio|cupo)\b|\blo primero que (tengas|haya)\b")
# «¿qué horas tienes?» mientras pide la cita: quiere ver los turnos libres
VER_HORAS = (r"\bque horas?\b|\bhoras? (libres|disponibles)\b|\bdisponib|\bturnos? (libres|disponibles)\b|"
             r"\bque (cupos|turnos|espacios)\b|\bcupo\b")
# «cancélala, quiero una cita para el lunes»: lo que sigue es una cita nueva
# («las citas que tengo agendadas» o «mi reserva» hablan de las que ya tiene, no de una nueva)
NUEVA = (r"\b((agend|reserv)(a(?= (me|una|otra|un|otro|para)\b)|(?!ad[ao]s?\b|a\b)\w*)|apart[ae]me|separ[ae]me|pideme|"
         r"(quiero|quisiera|necesito|dame|me (das|da|puedes dar|regalas)) (una |otra |un |otro )?"
         r"(cita|turno|corte|motilada|espacio|cupo))\b")
ANULA = r"\bcancel|\banul|\bborr|\bquit|\bya no (puedo|voy)|\bno (puedo|voy a poder)"
# «una hora más tarde», «media hora antes»: mover la cita sin decir la hora nueva
DESPLAZA = r"\b(media|una|un|dos|tres|\d) (hora|horas|horita)s? (mas )?(tarde|despues|antes|temprano)\b"
HUMANO = (r"\bhablar con\b|\b(llamar|escribir(le)?) a (la barberia|alguien|el barbero)\b|\btelefono\b|\bwhatsapp\b|"
          r"\bnumero de (la barberia|ustedes|contacto)\b|\bcontacto\b")
QUEJA = (r"\bme (dejaron|dejo|quedo) mal\b|\bmal (corte|motilado|hecho)\b|\bqueja\b|\breclamo\b|\bno me gusto\b|"
         r"\bme (cortaron|motilaron) mal\b")
RISA = r"(j[aeiou]){2,}j?|(ha){2,}h?|x+d+|lol|jsjs\w*"
RECUERDA = r"\brecuerd[ae](me|melo|mela|nos)\b|\bme (avisas|avisa|recuerdas|recuerda)\b"
# «espera un momento», «déjame pensar»: no hay nada que hacer todavía
ESPERA = (r"(ok |bueno |listo |dale )?(espera(me)?|un (momento|momentico|segundo|minuto)|dejame (pensar|ver|mirar|revisar)|"
          r"ya te (digo|confirmo|aviso)|ahorita te (digo|confirmo|aviso)|lo (pienso|consulto))\b.{0,25}")
# «mejor más tarde» con una hora ya escogida: los turnos siguientes (o los anteriores)
CORRIDA = (r"(mejor |un poco |algo |un poquito |y )*(mas (tarde|tardecito|temprano|tempranito)|despuesito)"
           r"( porfa| por favor| si se puede| si hay)?")
IDENTIDAD = (r"\b(eres|sos|es) (un |una )?(bot|robot|persona|humano|maquina|programa|ia|inteligencia artificial)\b|"
             r"\bcomo te llamas\b|\bquien eres\b|\bcon quien (hablo|estoy hablando)\b|\btu nombre\b")
DESCUENTO = r"\bdescuentos?\b|\bpromo(cion|ciones)?\b|\bofertas?\b|\bcupon\b|\b2x1\b|\bprecio especial\b"
DOMICILIO = r"\bdomicilio\b|\ba (la |mi )?casa\b|\bvan a (la casa|domicilio)\b"
VARIAS = r"\b(dos|2|tres|3) citas\b|\buna para mi y otra\b|\bpara mi y (para )?(mi|el|la)\b"
# «con cualquier barbero»: sin preferencia aunque el clasificador no lo marque
BARBERO_IGUAL = (r"\bcon (cualquiera|cualquier barbero|el que (este|sea|haya)( libre)?|quien sea|el que me toque)\b|"
                 r"\bcualquier barbero\b|\bcualquiera de los (dos|barberos)\b|\bel barbero que sea\b")
# «un 7 degradado», «desvanecido al 2»: el número de la guarda va con el estilo en la nota para el barbero
_ESTILO = r"(degradado|desvanecido|fade|taper|rapado)"
NUMERO_ESTILO = (rf"\b(?:(?:el|un|una) )?\d{{1,2}} (?:con )?(?:el |un )?{_ESTILO}\b|"
                 rf"\b{_ESTILO} (?:con el|al|en el|en) \d{{1,2}}\b")
# «cancela», «olvídalo» mientras arma una cita: deja esa cita, no busca otra
SUELTA = (r"(no |mejor |entonces |bueno )*(cancela(r|lo|la|le)?( todo)?|olvida(lo|la)?( eso)?|dejalo( asi)?|deja asi|"
          r"ya no( quiero)?|no quiero nada)( mejor| entonces| gracias| porfa| por favor)*")
# «que no sea el lunes», «cualquier día menos el 26»: días que el cliente descarta
_DESCARTA = r"(?:(?<!mas o )\bmenos|\bque no sea|\bexcepto|\bsalvo|\bsin contar|\bpero no)"
EVITA = (rf"{_DESCARTA}(?: ni)?(?: (?:el|los|este|esta))?(?: dias?)? (?P<dia>{fechas._DIA}s?|manana|hoy|pasado manana)\b|"
         rf"{_DESCARTA} el (?:dia )?(?P<fecha>\d{{1,2}}(?: de {fechas._MES})?)\b")
# «cancela todas menos la del sábado»: la cita que se queda
SALVO_LA = (rf"{_DESCARTA}(?: (?:la|las|el|los|cita|citas|de|del|para))* (?P<dia>{fechas._DIA}|manana|hoy|pasado manana)\b|"
            rf"{_DESCARTA}(?: (?:la|las|cita|citas|de|del|para))* (?:el )?(?P<fecha>\d{{1,2}})\b")
_Y_OTRO = (rf"(?: ni| y| o)(?:(?: (?:el|los))?(?: dias?)? (?P<dia>{fechas._DIA}s?|manana|hoy|pasado manana)|"
           rf" el (?:dia )?(?P<fecha>\d{{1,2}}(?: de {fechas._MES})?))\b")
# «el lunes no puedo» mientras agenda; fuera de una reserva puede ser que quiere cancelar, así que solo cuenta ahí
NO_PUEDE = (rf"\bno (?:puedo|me sirve|me queda)(?: (?:el|los|este))? (?P<dia>{fechas._DIA}s?|manana|hoy|pasado manana)\b|"
            rf"\b(?P<fecha>{fechas._DIA}|manana|hoy|pasado manana) no (?:puedo|me sirve|me queda)\b")
# «¿qué días tienes?»: quiere ver los días con turno libre
VER_DIAS = (r"\b(que|cuales|cual|en que) dias?\b(?! (atienden|abren|trabajan|cierran|descansan))|\bdias? (libres|disponibles)\b|"
            r"\bcuando (tienes|tiene|tienen|hay) (cupo|turno|espacio|agenda|disponib|libre)")
# «cancela las dos citas», «cancela mis citas»: todas las que nombra, no una
TODAS = r"\btodas\b|\btodo\b|\bambas\b|\blas (dos|2|tres|3|cuatro|4) (citas|que tengo)\b|(?<!una de )\bmis citas\b"
# «para el mismo día del corte», «justo después de mi cita»: la otra cita del cliente es la referencia
MISMO_DIA = r"\b(?:el |ese )?mismo dia\b|\bla misma fecha\b"
PEGADA = (r"\b(?:justo |inmediatamente |de una )?(?P<lado>despues|seguid[oa]|enseguida|antes) (?:de|del) (?:mi |la |el |esa )?"
          r"(?:otra |primera )?(?:cita|corte|barba|turno|motilada|arreglo|servicio)\b")
# lo que el clasificador marca como barbero y no es un nombre («día menos», «que sea»)
NO_ES_NOMBRE = r"\b(dia|dias|menos|sea|que|hora|semana|excepto|salvo)\b"
COMBO = (r"(\b[ck]ort|\bmotil|\bpelo\b|\bcabello\b).{0,40}\by\b.{0,30}\bbar[bv]|"
         r"\bbar[bv].{0,40}\by\b.{0,30}(\b[ck]ort|\bmotil|\bpelo\b|\bcabello\b)")
FUERA = ("Eso no lo manejo por aquí 😅 Yo te ayudo con tus citas, los precios y el horario. Para lo demás, escríbele "
         f"o llama a la barbería al {config.TELEFONO}.")


@dataclass
class Respuesta:
    texto: str
    botones: list = field(default_factory=list)     # filas de (texto, dato)
    pedir_contacto: bool = False


@dataclass
class Estado:
    """Marco de la conversación en curso."""
    intencion: str | None = None        # reservar, reprogramar o cancelar
    servicio: dict | None = None
    barbero: dict | None = None
    cualquiera: bool = False            # el cliente no tiene preferencia de barbero
    dia: date | None = None
    rango: tuple | None = None          # dijo una semana o un fin de semana: falta escoger el día
    hora: time | None = None
    pedida: fechas.Hora | None = None   # hora que falta leer contra el horario del día
    quiso: time | None = None           # la hora que pidió y estaba ocupada: se reintenta si cambia de día o de barbero
    franja: fechas.Franja | None = None
    opciones: list | None = None        # dijo dos días o dos horas distintas: falta saber cuál
    detalle: str = ""                   # cómo quiere el corte; va a las observaciones de la cita
    nombre: str = ""                    # a nombre de quién, si no es el cliente
    cita: dict | None = None            # la cita que se cambia o se cancela
    espera: str | None = None           # confirmar, telefono, documento o borrar
    despues: str | None = None          # qué hacer cuando comparta el teléfono
    pregunta: str | None = None         # lo último que preguntó el agente: servicio, dia, hora o barbero
    pendiente: dict | None = None       # datos del mensaje mientras escoge de cuál cita habla
    telefono: str = ""
    aviso: str = ""                     # algo que hay que decirle antes de seguir
    pronto: bool = False                # «lo más pronto posible»: el primer día y los primeros turnos libres
    primer_dia: bool = False            # «cualquier día»: el primer día con turno, con todas sus horas
    evitar: set = field(default_factory=set)   # días que descartó: días de la semana (0 = lunes) o fechas
    ver_horas: bool = False             # preguntó qué horas hay: se le muestran apenas se sepa el servicio
    ver_dias: bool = False              # preguntó qué días hay: se le muestran los que tienen turno
    desplazar: int | None = None        # «una hora más tarde»: minutos que se mueve la cita
    siguiente: str = ""                 # «cancélala y agéndame el lunes»: la cita nueva, para después de cancelar
    todas: bool = False                 # «cancela todas mis citas»
    charlo: bool = False                # ya le contestó «¡Uy, sí, toca darle una arreglada!» en esta cita
    varias: list | None = None          # las citas que se cancelan juntas
    fallos: int = 0
    visto: datetime | None = None


class Agente:
    def __init__(self, api, entender, perfiles, registro=None, respaldo=None, semilla=None):
        self.api, self.entender, self.perfiles, self.registro = api, entender, perfiles, registro
        self.respaldo = respaldo        # LLM que interpreta lo que el clasificador no entiende; puede no estar
        self.estados, self.sin_leer = {}, {}
        self.azar = random.Random(semilla)   # varía las muletillas para que no suene repetido

    def _una(self, *opciones):
        return self.azar.choice(opciones)

    # ----------------------------------------------------------------------- entradas

    def comando(self, uid, nombre, comando, ahora):
        perfil, e = self.perfiles.de(uid), self._estado(uid, ahora)
        if not perfil["acepta"]:
            return [Respuesta(AVISO, [[("Sí, acepto", "acepto")]])]
        if comando == "start":
            return [Respuesta(self._saludo(perfil), MENU)]
        if comando == "ayuda":
            return [Respuesta(AYUDA)]
        if comando == "miscitas":
            return self._seguro(lambda: self._mis_citas(e, perfil, ahora))
        if comando == "borrar":
            e.espera = "borrar"
            return [Respuesta("¿Borro tu perfil de este chat? Las citas que tengas agendadas siguen en la agenda de la "
                              "barbería; si no vas a ir, cancélalas antes.", [[("Sí, borrar", "borrar"), ("No", "no")]])]
        return [Respuesta("Ese comando no lo conozco 😅 Esto es lo que puedo hacer:", MENU)]

    def texto(self, uid, nombre, texto, ahora):
        perfil, e = self.perfiles.de(uid), self._estado(uid, ahora)
        if not perfil["acepta"]:
            self.sin_leer[uid] = texto
            return [Respuesta(AVISO, [[("Sí, acepto", "acepto")]])]
        if e.espera == "documento":
            return self._seguro(lambda: self._documento(uid, nombre, e, perfil, texto, ahora))
        if e.espera == "telefono":
            if re.search(r"\b(no|cancel\w*|despues|luego)\b", fechas.limpiar(texto)):
                self.estados.pop(uid, None)
                return [Respuesta("Listo, no registré nada. Cuando quieras, me escribes.")]
            if e.despues == "ejecutar" or re.fullmatch(r"[\d\s+().-]{7,}", texto.strip()):
                return [Respuesta(PEDIR_NUMERO, pedir_contacto=True)]
            e = self.estados[uid] = Estado(visto=ahora)    # el número era para buscar sus citas y siguió con otra cosa
        resultado = self.entender(texto)
        self._registrar(texto, resultado, ahora)
        return self._seguro(lambda: self._decidir(uid, nombre, e, perfil, texto, resultado, ahora))

    def boton(self, uid, nombre, dato, ahora):
        perfil, e = self.perfiles.de(uid), self._estado(uid, ahora)
        if dato == "acepto":
            perfil["acepta"] = True
            self.perfiles.guardar()
            pendiente = self.sin_leer.pop(uid, None)
            if pendiente:
                return self.texto(uid, nombre, pendiente, ahora)
            return [Respuesta("¡Gracias! " + self._saludo(perfil), MENU)]
        if not perfil["acepta"]:
            return [Respuesta(AVISO, [[("Sí, acepto", "acepto")]])]
        return self._seguro(lambda: self._boton(uid, nombre, e, perfil, dato, ahora))

    def contacto(self, uid, nombre, telefono, ahora):
        perfil, e = self.perfiles.de(uid), self._estado(uid, ahora)
        return self._seguro(lambda: self._contacto(uid, nombre, e, perfil, telefono, ahora))

    def recordatorios(self, ahora):
        """Mensajes para quienes tienen cita mañana y todavía no han recibido el recordatorio."""
        if not time(8) <= ahora.time() <= time(20):
            return []
        try:
            citas = self.api.citas()
        except ErrorAPI:
            return []
        manana, salida = ahora.date() + timedelta(days=1), []
        for uid, perfil in self.perfiles.todos():
            for c in citas:
                if c["clienteId"] == perfil["cliente_id"] and c["estado"] == "PROGRAMADA" \
                        and inicio(c).date() == manana and c["id"] not in perfil["recordadas"]:
                    perfil["recordadas"].append(c["id"])
                    salida.append((int(uid), Respuesta(
                        f"¡Hola! Te recuerdo que mañana tienes cita 💈\n{f.cita(c)}\n¿Cuento contigo?",
                        [[("👍 Ahí estaré", f"rec:ok:{c['id']}")],
                         [("Cambiarla", f"rec:cambiar:{c['id']}"), ("Cancelarla", f"rec:cancelar:{c['id']}")]])))
        if salida:
            self.perfiles.guardar()
        return salida

    # ----------------------------------------------------------------------- comprensión

    def _decidir(self, uid, nombre, e, perfil, texto, resultado, ahora):
        s = fechas.limpiar(texto)
        if not s and e.espera == "confirmar" and set(texto) & set("👍👌✅🙌💯🤝"):
            return self._confirmar(uid, nombre, e, perfil, ahora)      # el pulgar arriba también confirma
        if re.fullmatch(ESPERA, s):
            return [Respuesta(self._una("Dale, tranqui, aquí te espero 👍", "Listo, sin afán. Aquí te espero 👍"))]
        if e.intencion in ("reservar", "reprogramar") and e.dia and e.hora and len(s.split()) <= 8:
            # con una hora ya escogida: «mejor una hora más tarde» la corre; «mejor más tarde» busca las siguientes
            if m := re.search(DESPLAZA, s):
                e.hora = (datetime.combine(e.dia, e.hora) + timedelta(minutes=_minutos(m))).time()
                e.espera = e.quiso = None
                return self._avanzar(uid, nombre, e, perfil, ahora)
            if re.fullmatch(CORRIDA, s):
                despues = (datetime.combine(e.dia, e.hora) + timedelta(minutes=config.PASO)).time()
                e.franja = fechas.Franja(desde=despues) if re.search(r"tard|despues", s) else fechas.Franja(hasta=e.hora)
                e.hora = e.espera = e.quiso = None
                return self._avanzar(uid, nombre, e, perfil, ahora)
        elegido = self._sin_preferencia(uid, nombre, e, perfil, s, ahora)
        if elegido:
            return elegido
        # «recuérdame mañana» pide un recordatorio; «me recuerdas mi cita» pregunta cuándo es (eso sigue de largo)
        if re.search(RECUERDA, s) and not re.search(r"\bmis? citas?\b|\bcuando\b|\bque (dia|hora)\b|\ba que hora\b", s):
            return self._y_seguimos(uid, nombre, e, perfil, [Respuesta(self._recuerdo(perfil, ahora))], ahora)
        intencion = resultado["intencion"]
        datos = self._leer(resultado["ranuras"], ahora)
        if not datos["fecha"] and (m := re.search(r"\b(en|dentro de) \w+ (dias?|semanas?)\b", s)) \
                and (rescatada := fechas.fecha(m.group(0), ahora.date())):
            datos["fecha"].append(rescatada)        # «corte en ocho días»: el clasificador lo dejó dentro del servicio
        if not datos["barbero"] and re.search(BARBERO_IGUAL, s):
            datos["barbero"].append("cualquiera")
        for m in re.finditer(NUMERO_ESTILO, s):
            frase, estilo = m.group(0), m.group(1) or m.group(2)
            if not any(frase in fechas.limpiar(x) for x in datos["servicio"]):
                datos["servicio"] = [x for x in datos["servicio"] if fechas.limpiar(x) != estilo] + [frase]
        junto = None
        if intencion == "reservar" and e.intencion in (None, "reservar") \
                and (ref := re.search(PEGADA, s) or re.search(MISMO_DIA, s)):
            # «una barba para el mismo día del corte»: el corte nombra la otra cita, no es parte del servicio que pide
            junto = self._junto(perfil, s, ref, ahora)
            if junto:
                datos["fecha"] = []
                datos["servicio"] = [x for x in datos["servicio"] if fechas.limpiar(x) not in s[ref.start():]]
            else:
                e.aviso += "No veo otra cita tuya programada para tomarla de referencia. "
        evitar = _evitados(EVITA, s, ahora.date()) | (_evitados(NO_PUEDE, s, ahora.date()) if e.intencion == "reservar" else set())
        if evitar and e.intencion != "cancelar" and not re.search(r"\bcancel|\banul|\bborr|\bquit", s):
            # «que no sea el lunes» es parte de pedir (o mover) la cita aunque el clasificador lo lea como cancelar: ese día
            # no es el que pide, y lo que marcó como barbero («día menos») tampoco es un nombre
            if "reprogramar" not in (intencion, e.intencion):
                intencion = "reservar"
            datos["fecha"] = [x for x in datos["fecha"] if not (x.dia and _evitado(evitar, x.dia))]
            datos["barbero"] = [x for x in datos["barbero"] if not re.search(NO_ES_NOMBRE, fechas.limpiar(x))]
        else:
            evitar = set()
        un_dia = any(x.dia and not x.hasta for x in datos["fecha"])
        ver_dias = bool(re.search(VER_DIAS, s)) and not un_dia and e.intencion in (None, "reservar") \
            and intencion in ("reservar", "consultar_disponibilidad")
        if ver_dias:
            intencion = "reservar"                  # «¿qué días tienes?»: los días con turno para lo que se va a hacer
        con_datos = any(datos.values())
        dudoso = (resultado["confianza"] < config.UMBRAL or intencion == "fuera_de_alcance") \
            and not (evitar or ver_dias or junto)
        # hablar con alguien, una queja, descuentos, domicilios o quién es el bot: tiene respuesta fija
        aparte = self._aparte(s) if (dudoso and not con_datos) or intencion.startswith("consultar") else None
        if aparte:
            return self._y_seguimos(uid, nombre, e, perfil, aparte, ahora)
        solo_numero = e.pregunta and re.fullmatch(r"\d{1,2}([:.]\d{2})?", texto.strip())
        # «cualquiera» después de «¿con quién?»: si el mensaje contesta lo que se acaba de preguntar, esa lectura
        # gana sobre la del clasificador cuando este duda o no ve una tarea distinta
        directa = self._respuesta_directa(e, texto, ahora) if e.pregunta else None
        if directa and (dudoso or intencion in ("afirmar", "negar") or (intencion == "reservar" and not con_datos)) \
                and not solo_numero:
            datos, intencion, dudoso, con_datos = directa, "reservar", False, True
        descartado = False
        if dudoso and not solo_numero and self.respaldo and not (self._cortesia(texto) and not con_datos):
            # El clasificador duda: el mensaje pasa al LLM, que devuelve el mismo marco. Lo que diga sigue el
            # camino de siempre: normalizador, catálogo y confirmación antes de escribir.
            segundo = self.respaldo(texto, self._contexto(e))
            descartado = bool(segundo) and segundo["intencion"] == "fuera_de_alcance"
            if segundo and not descartado:
                intencion, datos, dudoso = segundo["intencion"], self._leer(segundo["ranuras"], ahora), False
                con_datos = any(datos.values())
        if solo_numero or (dudoso and not (e.intencion and con_datos)):
            directa = self._respuesta_directa(e, texto, ahora)
            if directa is None and con_datos and not e.intencion and not descartado:
                # marcó datos de una cita pero no es claro qué quiere: no se actúa, se le ofrecen opciones
                e.pendiente, e.espera = datos, "duda"
                return [Respuesta("No te entendí del todo 😅 ¿Quieres que te agende una cita?",
                                  [[("Sí, agendar", "duda:reservar"), ("Ver precios", "duda:precios")], [("Otra cosa", "duda:menu")]])]
            if directa is None:
                # entendido pero fuera de lo que atiende el agente (lo confirmó el LLM, o no hay LLM y el clasificador
                # está seguro): se le dice qué sí hace; si no, se le pide que lo diga de otra forma
                fuera = descartado or (not self.respaldo and resultado["intencion"] == "fuera_de_alcance")
                return self._no_entendi(uid, nombre, e, perfil, texto, ahora, fuera)
            datos, intencion = directa, "reservar"
        elif e.intencion and con_datos and (dudoso or intencion in ("afirmar", "negar")):
            intencion = "reservar"      # «no, pasado mañana» trae un dato: es parte de la tarea en curso
        elif e.intencion == "reservar" and con_datos and (e.espera == "confirmar" or e.pregunta) \
                and intencion in ("reprogramar", "consultar_citas", "consultar_disponibilidad"):
            # «no bro, la cita es para el 16» mientras agenda: corrige la cita que se está armando, no otra
            intencion = "reservar"
        e.fallos = 0

        if intencion == "afirmar":
            if e.espera == "duda":
                return self._boton(uid, nombre, e, perfil, "duda:reservar", ahora)
            if e.espera == "confirmar":
                return self._confirmar(uid, nombre, e, perfil, ahora)
            return self._avanzar(uid, nombre, e, perfil, ahora) if e.intencion else [Respuesta("¿Qué te hacemos?", MENU)]
        if intencion == "negar":
            return self._dejar(uid, e)
        if intencion == "consultar_servicios":
            if not datos["servicio"] and e.servicio and e.intencion in ("reservar", "reprogramar"):
                datos["servicio"] = [e.servicio["nombre"]]      # «¿cuánto vale?» mientras agenda: el que lleva
            return self._y_seguimos(uid, nombre, e, perfil, self._servicios(datos), ahora)
        if intencion == "consultar_citas":
            return self._y_seguimos(uid, nombre, e, perfil, self._mis_citas(e, perfil, ahora), ahora)
        if intencion == "consultar_disponibilidad":
            return self._y_seguimos(uid, nombre, e, perfil, self._disponibilidad(e, datos, texto, ahora), ahora)

        if intencion == "cancelar" and e.intencion == "reservar" and re.fullmatch(SUELTA, s):
            return self._dejar(uid, e)              # «cancela» mientras arma una cita: se deja esa cita

        siguiente = ""
        if intencion == "cancelar" and (partes := self._partir(s)):
            # «cancélala, quiero una cita para el lunes»: primero se cancela y después se agenda la nueva
            primera, siguiente = partes
            datos = self._leer(self.entender(primera)["ranuras"], ahora)

        # Un mensaje que solo trae datos se clasifica como reservar, pero pertenece a la tarea en curso
        nueva = e.intencion is None
        if intencion in ("reprogramar", "cancelar") and e.intencion != intencion:
            e = self.estados[uid] = Estado(intencion=intencion, visto=ahora)
        elif e.intencion is None:
            e.intencion = "reservar"
        e.espera = None
        e.siguiente = siguiente or e.siguiente
        e.todas = e.intencion == "cancelar" and bool(re.search(TODAS, s))
        if e.intencion == "reprogramar" and (m := re.search(DESPLAZA, s)):
            e.desplazar = _minutos(m)
        if e.intencion in ("reprogramar", "cancelar"):
            alto = self._ubicar(uid, e, datos, perfil, ahora, nombre, s)
            if alto:
                return alto
            if e.intencion == "reprogramar" and re.search(r"\botro dia\b", s):
                e.evitar.add(inicio(e.cita).date())     # «pásamela a otro día»: el de ahora no
        limpio = s[:junto[2]] if junto else s       # «…del corte» habla de la otra cita, no de lo que pide
        if re.search(r"\blo (mismo )?de siempre\b|\blo mismo de la (otra|ultima) vez\b", limpio) \
                and not any(re.search(EL_DE_SIEMPRE, fechas.limpiar(x)) for x in datos["servicio"]):
            datos["servicio"] = ["lo de siempre"]   # «quiero lo de siempre» aunque el clasificador lo parta
            if not datos["barbero"]:
                datos["barbero"] = ["el de siempre"]   # lo de siempre también es con el barbero de siempre
        elif e.intencion == "reservar" and re.search(COMBO, limpio):
            # «un corte y de una vez la barba»: el clasificador marcó solo uno de los dos
            datos["servicio"] = ["corte y barba"] + [x for x in datos["servicio"] if detalle([x])]
        elif e.intencion == "reservar" and e.servicio is None and not datos["servicio"]:
            # el clasificador no marcó el servicio pero el mensaje lo nombra («un corte», «una afeitada»), o lo
            # da por hecho («me motila mañana», «estoy muy mechudo»): un barbero entiende de qué se trata
            nombrados = [nombre for nombre, patron in SERVICIO_IMPLICITO if re.search(patron, limpio)]
            if nombrados:
                datos["servicio"] = [" y ".join(nombrados)]
        if e.intencion in ("reservar", "reprogramar"):
            e.evitar |= evitar
            e.primer_dia = e.primer_dia or (bool(re.search(r"\bcualquier dia\b|\bel dia que (sea|tengas|quieras)\b", limpio))
                                            and not datos["fecha"] and not junto)
        if e.intencion == "reservar" and ver_dias:  # el día que traía no cuenta: quiere ver cuáles hay
            e.ver_dias, e.dia, e.hora, e.quiso, e.pronto, e.primer_dia = True, None, None, None, False, False
        self._aplicar(e, datos, perfil, ahora)
        if e.intencion in ("reservar", "reprogramar") and e.dia and _evitado(e.evitar, e.dia):
            e.dia = e.hora = e.quiso = None         # «que no sea el lunes» cuando ya iba para el lunes
        if e.intencion == "reservar":
            if junto:
                cita, lado, _ = junto
                e.dia, e.rango, e.opciones = inicio(cita).date(), None, None
                if lado != "mismo" and e.servicio:  # «justo después de mi corte»: la hora pegada a esa cita
                    e.hora, e.pedida, e.franja = _pegada(cita, lado, e.servicio["duracionMinutos"]), None, None
            e.pronto = e.pronto or (bool(re.search(PRONTO, limpio)) and not (datos["fecha"] or datos["hora"]))
            e.ver_horas = e.ver_horas or bool(re.search(VER_HORAS, limpio))
            if nueva and re.search(VARIAS, limpio):
                e.aviso += "Te las agendo una por una: empecemos con la tuya y después hacemos la otra. "
        respuestas = self._avanzar(uid, nombre, e, perfil, ahora)
        frase = self._charla(texto) if e.intencion == "reservar" and not e.charlo else ""
        e.charlo = e.charlo or bool(frase)          # una vez por cita
        # «Hola, buenas noches, necesito…»: se devuelve el saludo antes de lo demás
        respuestas[0].texto = (_saludo_de_vuelta(s, perfil["nombre"]) if nueva else "") + frase + respuestas[0].texto
        return respuestas

    def _leer(self, ranuras, ahora):
        """Pasa las ranuras de tiempo por el normalizador. Servicio, barbero y nombre siguen como texto."""
        lectores = {"fecha": lambda v: fechas.fecha(v, ahora.date()), "hora": fechas.hora, "franja": fechas.franja}
        datos = {clave: [] for clave in VACIO}
        ranuras = [dict(r) for r in ranuras]
        for i, r in enumerate(ranuras):
            s = fechas.limpiar(r["valor"])
            if r["tipo"] == "servicio" and s in fechas.DIAS and i + 1 < len(ranuras) and ranuras[i + 1]["tipo"] == "fecha":
                # «el marte 13 de octubre»: el día de la semana mal escrito quedó como servicio; va con la fecha
                ranuras[i + 1]["valor"] = r["valor"] + " " + ranuras[i + 1]["valor"]
                r["tipo"] = None
            elif r["tipo"] == "servicio" and s in {"lo", "la", "el", "de", "un", "una", "me"}:
                r["tipo"] = None                     # un pedazo suelto de «lo de siempre»
        for r in ranuras:
            if r["tipo"] is None:
                continue
            if r["tipo"] not in lectores:
                datos[r["tipo"]].append(r["valor"])
                continue
            # si el clasificador confundió el tipo («sábado» como hora), se prueba con los otros dos
            for tipo in dict.fromkeys([r["tipo"], "fecha", "hora", "franja"]):
                valor = lectores[tipo](r["valor"])
                if valor is not None:
                    datos[tipo].append(valor)
                    break
        return datos

    def _sin_preferencia(self, uid, nombre, e, perfil, s, ahora):
        """«La que tengas», «cualquier día», «la más tarde», «no sé»: contesta el día o la hora sin escoger uno."""
        if e.intencion not in ("reservar", "reprogramar") or e.pregunta not in ("dia", "hora"):
            return None
        if re.fullmatch(NO_SE, s):
            return [Respuesta(self._una("Tranqui 😄", "Fresco 😄") + " Mira lo que tengo y escoge lo que te quede mejor.")] \
                + self._avanzar(uid, nombre, e, perfil, ahora)
        if e.pregunta == "hora" and re.search(LA_ULTIMA, s):
            e.pedida = fechas.Hora(especial="ultima")
        elif re.search(LA_QUE_SEA, s) and not re.search(rf"\d|\b(tarde|noche|manana|mediodia|hoy|pasado)\b|{fechas._DIA}|{fechas._MES}", s):
            if e.pregunta == "dia":                 # «lo más pronto»: los primeros turnos; «cualquier día»: todo el día
                e.pronto, e.primer_dia = bool(re.search(PRONTO, s)), not re.search(PRONTO, s)
            else:
                e.pedida = fechas.Hora(especial="primera")
        else:
            return None
        e.hora = e.quiso = None
        return self._avanzar(uid, nombre, e, perfil, ahora)

    def _y_seguimos(self, uid, nombre, e, perfil, respuestas, ahora):
        """Una consulta en medio de la reserva («¿cuánto vale?», «¿hasta qué hora abren?»): se contesta y se retoma."""
        pendiente = e.intencion in ("reservar", "reprogramar") and (e.espera == "confirmar" or e.pregunta)
        if not pendiente or any(r.pedir_contacto for r in respuestas):
            return respuestas
        for r in respuestas:                        # los botones de agendar sobran: ya está agendando
            filas = [[(t, d) for t, d in fila if not d.startswith(("srv:", "menu:reservar"))] for fila in r.botones]
            r.botones = [fila for fila in filas if fila]
        if any(r.botones for r in respuestas):
            return respuestas
        if e.espera == "confirmar":
            botones = [[("Sí, cámbiala" if e.cita else "Sí, agéndala", "ok"), ("Cambiar algo", "cambiar")]]
            return respuestas + [Respuesta("¿Le doy?" if e.cita else "¿Te la agendo así?", botones)]
        return respuestas + self._avanzar(uid, nombre, e, perfil, ahora)

    def _recuerdo(self, perfil, ahora):
        """«Recuérdame»: el recordatorio sale el día anterior a la cita; si es para hoy o mañana, se le dice cuándo es."""
        proxima = next(iter(self._mias(perfil, ahora)), None) if perfil["cliente_id"] is not None else None
        if proxima is None:
            return "¡Claro! Cuando agendes una cita, te escribo el día anterior para recordártela 👍"
        dia, faltan = inicio(proxima).date(), (inicio(proxima).date() - ahora.date()).days
        if faltan > 1:
            return (f"¡Claro! El {f.DIAS[(dia - timedelta(days=1)).weekday()]} te escribo para recordarte tu cita del "
                    f"{f.dia(dia)} 👍")
        cuando = "hoy" if faltan == 0 else "mañana"
        return f"¡De una! Tu cita es {cuando} a {f.las(inicio(proxima).time())}: aquí te espero 💈"

    def _aparte(self, s):
        """Lo que no es de citas pero tiene respuesta fija: quién es el bot, hablar con alguien, quejas, descuentos."""
        if re.search(IDENTIDAD, s):
            return [Respuesta("Soy TBot, el asistente de la barbería 🤖 Soy un programa, no una persona: te ayudo a agendar, "
                              "cambiar o cancelar tus citas y te digo precios y horarios. Si prefieres hablar con alguien, "
                              f"llama a la barbería al {config.TELEFONO}.")]
        if re.search(QUEJA, s):
            return [Respuesta(f"Uy, qué pena 😕 Cuéntaselo a la barbería al {config.TELEFONO} para que te lo arreglen.")]
        if re.search(HUMANO, s):
            return [Respuesta(f"¡Claro! Puedes escribirle o llamar a la barbería al {config.TELEFONO}.")]
        if re.search(DESCUENTO, s):
            return [Respuesta(f"Las promociones te las cuentan en la barbería: escríbeles o llama al {config.TELEFONO}.")]
        if re.search(DOMICILIO, s):
            return [Respuesta("Por ahora solo atendemos en la barbería 💈 Si necesitas algo especial, pregúntales al "
                              f"{config.TELEFONO}.")]
        return None

    def _partir(self, s):
        """«Cancélala, quiero una cita para el lunes» -> («cancélala», «quiero una cita para el lunes»)."""
        m = re.search(NUEVA, s)
        if m and m.start() > 0 and re.search(ANULA, s[:m.start()]):
            return s[:m.start()], s[m.start():]
        return None

    def _junto(self, perfil, s, ref, ahora):
        """La cita del cliente a la que se refiere «el mismo día del corte» o «justo después de mi cita» (la que nombra,
        o la próxima), si la nueva va el mismo día, justo después o justo antes, y dónde empieza esa referencia en el
        mensaje. None si no tiene citas."""
        mias = self._mias(perfil, ahora) if perfil["cliente_id"] is not None else []
        cola = s[ref.start():]
        semana = {fechas.DIAS.index(x) for x in re.findall(fechas._DIA, cola)}       # «antes de mi cita del sábado»
        nombrado = buscar_servicio(cola, self.api.servicios())                     # «el mismo día del corte»
        cita = next((c for c in mias if inicio(c).weekday() in semana), None) \
            or next((c for c in mias if nombrado and c["servicioId"] == nombrado["id"]), mias[0] if mias else None)
        lado = ref.groupdict().get("lado")
        return cita and (cita, "antes" if lado == "antes" else "despues" if lado else "mismo", ref.start())

    def _respuesta_directa(self, e, texto, ahora):
        """Lee el mensaje como respuesta a lo que el agente acaba de preguntar, sin pasar por el clasificador."""
        datos = {clave: [] for clave in VACIO}
        if e.pregunta == "servicio" and buscar_servicio(texto, self.api.servicios()):
            datos["servicio"] = [texto]
        elif e.pregunta == "barbero" and buscar_barbero(texto, self.api.barberos()):
            datos["barbero"] = [texto]
        elif e.pregunta in ("dia", "opcion") and fechas.fecha(texto, ahora.date()):
            datos["fecha"] = [fechas.fecha(texto, ahora.date())]
        elif e.pregunta in ("hora", "opcion") and fechas.hora(texto):
            datos["hora"] = [fechas.hora(texto)]
        elif e.pregunta == "hora" and fechas.franja(texto):
            datos["franja"] = [fechas.franja(texto)]
        else:
            return None
        return datos

    def _aplicar(self, e, datos, perfil, ahora):
        """Lleva al marco los datos del mensaje. Un valor nuevo reemplaza al anterior."""
        hoy = ahora.date()
        if datos["servicio"]:
            texto, catalogo, antes = " y ".join(datos["servicio"]), self.api.servicios(), e.servicio
            if re.search(EL_DE_SIEMPRE, fechas.limpiar(texto)):
                servicio = self._habitual(perfil, "servicios", catalogo)
                e.servicio = servicio or e.servicio
                e.aviso += "" if servicio else "Todavía no sé qué es lo de siempre para ti. "
            else:
                servicio = buscar_servicio(texto, catalogo)
                if servicio is None:
                    e.aviso += f"«{texto}» no lo hacemos por acá 😅 "
                elif not servicio["activo"]:
                    e.aviso += f"Por ahora no estamos haciendo {servicio['nombre'].lower()}. "
                else:
                    e.servicio = servicio
            # «el 7 con desvanecido» describe el corte: se guarda para el barbero; si cambió de servicio, se olvida
            nuevo = detalle(datos["servicio"])
            e.detalle = nuevo or (e.detalle if e.servicio == antes else "")
        actual = e.cita["barberoId"] if e.cita else None
        for texto in datos["barbero"]:
            # «con el 2 a los lados»: el número es de la guarda, no un barbero; «cualquier día» habla del día
            if re.search(r"\d", texto) or re.search(r"\b(dia|dias|hora|horas|semana|fecha)\b", fechas.limpiar(texto)):
                continue
            catalogo = self.api.barberos()
            barbero = buscar_barbero(texto, catalogo)
            if barbero == "habitual":
                barbero = self._habitual(perfil, "barberos", catalogo) or "cualquiera"
            if barbero == "cualquiera":
                e.barbero, e.cualquiera = None, True
            elif barbero is None:
                if not re.search(NO_ES_NOMBRE, fechas.limpiar(texto)):     # «que sea» no es alguien que no existe
                    e.aviso += f"No encuentro a «{texto}» entre los barberos. "
            elif not barbero["activo"]:
                e.aviso += f"{f.pila(barbero['nombre'])} no está atendiendo por ahora. "
            elif barbero["id"] != actual:        # el barbero de la cita que se cambia no es un dato nuevo
                e.barbero, e.cualquiera = barbero, False
        dias = [x for x in datos["fecha"] if x.dia]
        distintos = list(dict.fromkeys(x.dia for x in dias if not x.hasta))
        if e.intencion == "reservar" and len(distintos) > 1:
            # «para el 16 ... y el 7 con desvanecido»: dos días en la misma petición; se pregunta en vez de adivinar
            e.dia, e.rango, e.opciones = None, None, [("dia", d) for d in distintos]
        elif dias:
            ultima = dias[-1]
            e.dia, e.rango = (None, (ultima.dia, ultima.hasta)) if ultima.hasta else (ultima.dia, None)
            e.opciones = None
        if datos["franja"]:
            e.franja = datos["franja"][-1]
            if e.franja.hoy and not dias:
                e.dia = hoy
            if not datos["hora"]:
                e.hora = e.pedida = None
        horas = list({(h.hora, h.minuto, h.definida): h for h in datos["hora"] if h.hora is not None}.values())
        if e.intencion == "reservar" and len(horas) > 1 and not e.opciones:
            e.hora = e.pedida = None                # «a las 5, no a las 3»: se pregunta cuál
            e.opciones = [("hora", h) for h in horas]
        elif datos["hora"]:
            if e.opciones and e.opciones[0][0] == "hora":
                e.opciones = None
            pedida = datos["hora"][-1]
            e.hora = e.pedida = None
            if pedida.en_minutos is not None:      # «ahorita», «en media hora»
                cuando = ahora + timedelta(minutes=pedida.en_minutos)
                cuando += timedelta(minutes=-cuando.minute % config.PASO, seconds=-cuando.second,
                                    microseconds=-cuando.microsecond)
                e.dia, e.hora = (cuando.date(), cuando.time()) if not dias else (e.dia, cuando.time())
            else:
                e.pedida = pedida
        if datos["nombre"]:
            e.nombre = datos["nombre"][-1]
        if datos["hora"] or datos["franja"]:
            e.quiso = None
        elif e.quiso and e.hora is None and (dias or datos["barbero"]):
            e.hora = e.quiso                       # «mejor con Julián»: la misma hora, con otro barbero

    def _habitual(self, perfil, clave, catalogo):
        """El barbero o el servicio que el cliente más ha pedido, si sigue activo en el catálogo."""
        veces = perfil[clave]
        activos = [x for x in catalogo if x["activo"] and str(x["id"]) in veces]
        return max(activos, key=lambda x: veces[str(x["id"])], default=None)

    # ----------------------------------------------------------------------- reservar y reprogramar

    def _avanzar(self, uid, nombre, e, perfil, ahora):
        if e.intencion == "cancelar":
            e.espera = "confirmar"
            if e.varias:
                lista = "\n\n".join(f.cita(c) for c in e.varias)
                return [Respuesta(f"¿Seguro que te cancelo estas {len(e.varias)} citas?\n\n{lista}",
                                  [[("Sí, cancélalas", "ok"), ("No, déjalas", "no")]])]
            return [Respuesta(f"¿Seguro que te cancelo esta cita?\n{f.cita(e.cita)}",
                              [[("Sí, cancélala", "ok"), ("No, déjala", "no")]])]
        if e.intencion == "reprogramar":
            antes = inicio(e.cita)
            if e.desplazar:                         # «una hora más tarde»: el mismo día, corrida esos minutos
                movida = antes + timedelta(minutes=e.desplazar)
                e.dia, e.hora, e.pedida, e.desplazar = movida.date(), movida.time(), None, None
            if not (e.servicio or e.barbero or e.cualquiera or e.dia or e.rango or e.hora or e.pedida or e.franja
                    or e.primer_dia):
                sin = f" Estos días tengo turno, sin contar {_dias_texto(e.evitar)}." if e.evitar else ""
                return self._preguntar(e, "dia", f"Tu cita está así:\n{f.cita(e.cita)}\n¿Para cuándo te la paso?{sin}",
                                       self._dias(e, ahora))
            # lo que el cliente no cambió se conserva de la cita actual
            e.servicio = e.servicio or self._del_catalogo(self.api.servicios(), e.cita["servicioId"])
            if not e.barbero and not e.cualquiera:
                e.barbero = self._del_catalogo(self.api.barberos(), e.cita["barberoId"])
            if not e.rango and not e.opciones and not e.primer_dia and not _evitado(e.evitar, antes.date()):
                e.dia = e.dia or antes.date()       # «para cualquier día menos el lunes» sí cambia el día
            if not (e.hora or e.pedida or e.franja or e.opciones):
                e.hora = antes.time()
            e.detalle = e.detalle or e.cita.get("observaciones") or ""
        return self._agendar(uid, e, perfil, ahora)

    def _agendar(self, uid, e, perfil, ahora):
        """Pregunta lo que falta, de a una cosa, y cuando el turno está libre muestra el resumen para confirmar."""
        servicios = [s for s in self.api.servicios() if s["activo"]]
        barberos = [b for b in self.api.barberos() if b["activo"]]
        aviso, e.aviso = e.aviso, ""
        hoy = ahora.date()
        if e.servicio is None:
            pregunta = self._una("¿Qué te vas a hacer? ✂️", "¿Qué te hacemos? ✂️")
            if e.ver_dias:                          # «¿qué días tienes?»: también depende de cuánto dura el servicio
                pregunta = "Claro, te digo qué días tengo. Primero dime qué te vas a hacer, así sé cuánto tiempo apartarte ✂️"
            elif e.ver_horas:                       # «¿qué horas tienes?»: los turnos dependen de cuánto dura el servicio
                cuando = f" el {f.dia(e.dia)}" if e.dia and e.dia >= hoy else ""
                pregunta = (f"Claro, te digo qué horas tengo{cuando}. Primero dime qué te vas a hacer, así sé cuánto "
                            "tiempo apartarte ✂️")
            return self._preguntar(e, "servicio", aviso + pregunta,
                                   [[(f"{s['nombre']} · {f.precio(s['precio'])}", f"srv:{s['id']}")] for s in servicios])
        if e.opciones and e.opciones[0][0] == "dia":
            dias = [d for _, d in e.opciones]
            nombres = " o el ".join(f.dia(d) for d in dias)
            return self._preguntar(e, "opcion", f"{aviso}Me nombraste dos fechas: ¿te anoto el {nombres}?",
                                   [[(f.dia_corto(d, hoy), f"dia:{d.isoformat()}") for d in dias]])
        if e.dia is not None and e.dia < hoy:
            aviso, e.dia = aviso + "Ese día ya pasó 😅 ", None
        if e.dia is not None and e.dia.weekday() not in config.HORARIO:
            aviso, e.dia = aviso + f.horario(e.dia.weekday()) + " ", None
        if e.dia is None and e.rango and len(unico := self._dias_lista(ahora, e.rango)) == 1:
            e.dia, e.rango = unico[0], None         # «el fin de semana»: el domingo no se atiende, queda el sábado
        escogido = e.dia is None and (e.pronto or e.primer_dia)    # el agente escoge el día
        if escogido:
            e.dia = self._primer_dia(e, ahora)
        if e.dia is None:
            dias = self._dias_libres(e, ahora)
            if not dias and (e.rango or e.franja or e.evitar):
                aviso += "Uy, así no me quedan turnos en los próximos días 😕 "
                e.rango, e.franja, e.evitar = None, None, set()
                dias = self._dias_libres(e, ahora)
            if not dias:
                return [Respuesta(f"{aviso}Uy, en las próximas dos semanas no me quedan turnos 😕 Llama a la barbería al "
                                  f"{config.TELEFONO} y te buscan un espacio.")]
            if e.ver_dias or e.evitar or e.franja:  # «¿qué días tienes en la mañana, que no sea el lunes?»
                quien = f" con {f.pila(e.barbero['nombre'])}" if e.barbero and not e.cualquiera else ""
                sin = f", sin contar {_dias_texto(e.evitar)}" if e.evitar else ""
                pregunta = (f"Para {e.servicio['nombre'].lower()}{quien}{_en_franja(e.franja)} tengo turno estos "
                            f"días{sin}. ¿Cuál te sirve?")
            else:
                pregunta = "¿Para qué día te la paso?" if e.cita else self._una("¿Para qué día te anoto?", "¿Qué día te queda bien?")
            return self._preguntar(e, "dia", aviso + pregunta, self._botones_dias(dias, ahora))

        apertura, cierre = config.HORARIO[e.dia.weekday()]
        duracion = e.servicio["duracionMinutos"]
        # con «cualquiera» el barbero que se le asignó no amarra el turno: se escoge de nuevo con cada cambio
        elegido = None if e.cualquiera else e.barbero
        candidatos = [elegido] if elegido else barberos
        citas = self.api.citas()
        excepto = e.cita["id"] if e.cita else None
        libres = turnos(e.dia, duracion, candidatos, citas, ahora, excepto)
        con_quien = f" con {f.pila(elegido['nombre'])}" if elegido else ""
        borde = None                               # «primeras» o «ultimas»: la hora pedida cae antes de abrir o después de cerrar

        # el cliente tampoco puede tener dos citas que se crucen, aunque sean con barberos distintos (la API lo rechaza)
        propias = [c for c in citas if perfil["cliente_id"] is not None and c["clienteId"] == perfil["cliente_id"]
                   and c["estado"] == "PROGRAMADA" and c["id"] != excepto]

        def choca(t):
            desde = datetime.combine(e.dia, t)
            hasta = desde + timedelta(minutes=duracion)
            return next((c for c in propias
                         if desde < inicio(c) + timedelta(minutes=c["duracionMinutos"]) and inicio(c) < hasta), None)

        libres = {t: quienes for t, quienes in libres.items() if not choca(t)}

        if e.opciones and e.opciones[0][0] == "hora":
            horas = list(dict.fromkeys(t for _, h in e.opciones for t in fechas.en_horario(h, apertura, cierre)[:1]))
            if len(horas) > 1:
                return self._preguntar(e, "opcion", f"{aviso}Me dijiste dos horas: ¿cuál te sirve?", self._horas(horas))
            e.opciones, e.hora = None, horas[0] if horas else None

        if e.pedida:
            pedida, e.pedida = e.pedida, None
            if pedida.especial:                    # «a primera hora», «a última hora»
                posibles = [t for t in libres if not e.franja or fechas.dentro(t, e.franja)]
                e.hora = (posibles[0] if pedida.especial == "primera" else posibles[-1]) if posibles else None
                if e.hora:                          # el agente escogió la hora: se dice cuál antes de seguir
                    cual = "primera" if pedida.especial == "primera" else "última"
                    aviso += f"La {cual} hora que tengo{con_quien} es a {f.las(e.hora)} "
            else:
                abiertas, cerrada = fechas.resolver(pedida, apertura, cierre, e.franja)
                e.franja = None                    # la hora dice más que la franja y ya la tuvo en cuenta
                if len(abiertas) == 2:             # el horario no alcanza para decidir: se pregunta
                    return self._preguntar(e, "hora", aviso + "¿Esa hora es de la mañana o de la tarde?",
                                           self._horas(abiertas))
                if abiertas and not _en_punto(abiertas[0], apertura):
                    # «a las 9:52»: se atiende, pero los turnos van en punto y a la media hora
                    pedida_hora, e.quiso = abiertas[0], None
                    cercanos = _cercanas(libres, pedida_hora)
                    texto = (f"{aviso}Las citas son {CADA} ({_ejemplo(apertura)}), así que a {f.las(pedida_hora)} "
                             "no te la puedo dar.")
                    if not cercanos:
                        return self._sin_turnos(e, texto + " ", con_quien, ahora)
                    return self._preguntar(e, "hora", f"{texto} Lo más cerca que tengo{con_quien} es:",
                                           self._horas(cercanos))
                if abiertas:
                    e.hora = abiertas[0]
                elif cerrada is not None and cerrada < apertura:
                    aviso += f"A {f.las(cerrada)} todavía no hemos abierto 😅 Abrimos a {f.las(apertura)} "
                    borde = "primeras"
                elif cerrada is not None:
                    aviso += f"A {f.las(cerrada)} ya cerramos 😕 Atendemos hasta {f.las(cierre)} "
                    borde = "ultimas"
                else:                              # «a las 8»: ni las 8 de la mañana ni las 8 de la noche
                    aviso += (f"A {f.las(fechas.lecturas(pedida)[0], corta=True)} no estamos atendiendo; abrimos de "
                              f"{f.hora(apertura)} a {f.hora(cierre)} ")

        if e.hora is None:
            posibles = [t for t in libres if not e.franja or fechas.dentro(t, e.franja)]
            if borde == "primeras":
                posibles = posibles[:4]
            elif borde == "ultimas":
                posibles = posibles[-4:]
            if not posibles and libres and e.franja:
                if e.franja.hasta is not None and e.franja.hasta <= apertura:
                    aviso += f"A esa hora todavía no hemos abierto 😅 Abrimos a {f.las(apertura)} "
                    posibles = list(libres)[:4]
                elif e.franja.desde is not None and e.franja.desde >= cierre:
                    aviso += f"A esa hora ya cerramos; atendemos hasta {f.las(cierre)} "
                    posibles = list(libres)[-4:]
                else:
                    aviso += "En esa franja ya no me quedan turnos. "
                    posibles = list(libres)
                e.franja = None
            if not posibles:
                return self._sin_turnos(e, aviso, con_quien, ahora)
            if e.pronto:                            # «lo más pronto posible»: los primeros turnos que quedan
                return self._preguntar(e, "hora", aviso + f"Lo más pronto que tengo{con_quien} es el {f.dia(e.dia)} "
                                       "a estas horas. ¿Cuál te sirve?", self._horas(posibles[:4]))
            mostradas = _repartidas(posibles, 8)
            otra = next((c for c in propias if inicio(c).date() == e.dia), None)
            if otra and (seguida := _pegada(otra, "despues", duracion)) in posibles:
                # ese día ya viene a otra cita: lo natural es atenderlo apenas termine
                mostradas = sorted(set(mostradas) | {seguida})
                texto = (f"{aviso}El {f.dia(e.dia)} ya tienes {otra['servicioNombre'].lower()} a "
                         f"{f.las(inicio(otra).time())}: te puedo atender seguido, a {f.las(seguida)}, o a otra de "
                         f"estas horas{con_quien}. ¿Cuál te sirve?")
            elif escogido:
                texto = f"{aviso}Lo primero que tengo{con_quien} es el {f.dia(e.dia)}. ¿A qué hora te sirve?"
            else:
                texto = f"{aviso}El {f.dia(e.dia)} tengo libre{con_quien} a estas horas. ¿Cuál te sirve?"
            if len(mostradas) < len(posibles):      # no caben todas: que sepa que puede pedir otra
                texto += " Hay más horas entre esas; si quieres otra, escríbemela."
            return self._preguntar(e, "hora", texto, self._horas(mostradas))

        cuando = datetime.combine(e.dia, e.hora)
        quienes = libres_a(cuando, duracion, candidatos, citas, ahora, excepto)
        propia = choca(e.hora)
        if not quienes or propia:
            fin = (cuando + timedelta(minutes=duracion)).time()
            if propia:
                motivo = (f"A esa hora ya tienes una cita: {propia['servicioNombre'].lower()} con "
                          f"{f.pila(propia['barberoNombre'])} a {f.las(inicio(propia).time())}")
            elif cuando <= ahora:
                motivo = "Esa hora ya pasó."
            elif e.hora < apertura:
                motivo = f"A esa hora todavía no hemos abierto; abrimos a {f.las(apertura)}"
            elif fin > cierre or fin < e.hora:
                motivo = (f"A {f.las(e.hora)} no alcanzamos: {e.servicio['nombre'].lower()} dura {duracion} minutos "
                          f"y cerramos a {f.las(cierre)}")
            elif elegido and any(c["barberoId"] == elegido["id"] and inicio(c) == cuando for c in citas):
                motivo = f"{f.pila(elegido['nombre'])} ya tiene una cita a {f.las(e.hora, corta=True)}."
            elif elegido:
                motivo = f"{f.pila(elegido['nombre'])} no alcanza a atenderte a {f.las(e.hora, corta=True)} porque tiene otra cita."
            else:
                motivo = f"A {f.las(e.hora, corta=True)} ya no me queda turno."
            cercanos, e.quiso, e.hora = _cercanas(libres, e.hora), e.hora, None
            if not cercanos:
                return self._sin_turnos(e, aviso + motivo + " ", con_quien, ahora)
            return self._preguntar(e, "hora", f"{aviso}{motivo} ¿Te sirve alguna de estas?", self._horas(cercanos))

        if elegido is None:
            if not e.cualquiera and len(quienes) > 1:
                # «¿a las 10 no tienes?»: primero se le contesta que sí hay, y con quiénes (si el agente escogió la
                # hora, ya la dijo en el aviso)
                nombres = _y([f.pila(b["nombre"]) for b in quienes])
                hay = (f"{aviso.rstrip()}, con {nombres}. " if f.las(e.hora) in aviso
                       else f"{aviso}El {f.dia(e.dia)} a {f.las(e.hora)} tengo turno con {nombres}. ")
                return self._preguntar(e, "barbero", hay + "¿Con quién te quieres atender? Si te da igual, dime «cualquiera».",
                                       [[(f.pila(b["nombre"]), f"bar:{b['id']}") for b in quienes],
                                        [("Me da igual", "bar:0")]])
            e.barbero = self._habitual(perfil, "barberos", quienes) or quienes[0]

        if e.cita and (e.servicio["id"], e.barbero["id"], cuando) == (e.cita["servicioId"], e.cita["barberoId"], inicio(e.cita)):
            e.dia = e.hora = None
            return self._preguntar(e, "dia", aviso + "Así es como está tu cita ahora. ¿Para cuándo te la paso?",
                                   self._dias(e, ahora))
        e.espera, e.pregunta = "confirmar", None
        resumen = (f"✂️ {e.servicio['nombre']} con {f.pila(e.barbero['nombre'])}\n📅 {f.dia(e.dia)}, {f.hora(e.hora)}\n"
                   f"💵 {f.precio(e.servicio['precio'])} · {duracion} min")
        if e.detalle:
            resumen += f"\n📝 {e.detalle}"
        if self._nota(e, perfil):
            resumen += f"\n👤 {self._nota(e, perfil)}"
        if e.cita:
            resumen = (f"Te la cambio así:\nAntes: {f.dia(inicio(e.cita).date())}, {f.hora(inicio(e.cita).time())}\n"
                       f"Ahora:\n{resumen}\n¿Le doy?")
            botones = [[("Sí, cámbiala", "ok"), ("Cambiar algo", "cambiar")]]
        else:
            resumen = f"{self._una('Mira cómo te queda:', 'Te quedaría así:', 'Así te la dejo:')}\n{resumen}\n¿Te la agendo así?"
            botones = [[("Sí, agéndala", "ok"), ("Cambiar algo", "cambiar")]]
        return [Respuesta(aviso + resumen, botones)]

    def _sin_turnos(self, e, aviso, con_quien, ahora):
        dia, e.dia = e.dia, None
        return self._preguntar(e, "dia", f"{aviso}Uy, el {f.dia(dia)} ya no me quedan turnos{con_quien} 😕 "
                               "¿Te sirve otro día?", self._dias(e, ahora, saltar=dia))

    def _preguntar(self, e, que, texto, botones):
        e.pregunta, e.espera = que, None
        return [Respuesta(texto, botones)]

    def _dias_lista(self, ahora, rango, saltar=None):
        """Los próximos días en que se atiende (o los del intervalo que dijo el cliente), sin los que ya cerraron."""
        hoy = ahora.date()
        desde, hasta = (max(rango[0], hoy), rango[1]) if rango else (hoy, hoy + timedelta(days=13))
        dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
        return [d for d in dias if d.weekday() in config.HORARIO and d != saltar
                and (d > hoy or ahora.time() < config.HORARIO[d.weekday()][1])]

    def _dias_libres(self, e, ahora, saltar=None, horas=()):
        """Los próximos días (o los del intervalo que dijo) con algún turno libre para lo que lleva la cita: el servicio,
        el barbero y la franja (o una de `horas`), sin los días que descartó. Así no se ofrece un día que ya está lleno."""
        activos = [s for s in self.api.servicios() if s["activo"]]
        duracion = (e.servicio or e.cita or {}).get("duracionMinutos") \
            or min((s["duracionMinutos"] for s in activos), default=config.PASO)
        candidatos = [e.barbero] if e.barbero and not e.cualquiera else [b for b in self.api.barberos() if b["activo"]]
        citas, excepto = self.api.citas(), e.cita["id"] if e.cita else None
        return [d for d in self._dias_lista(ahora, e.rango, saltar) if not _evitado(e.evitar, d)
                and any((t in horas) if horas else (not e.franja or fechas.dentro(t, e.franja))
                        for t in turnos(d, duracion, candidatos, citas, ahora, excepto))]

    def _botones_dias(self, dias, ahora):
        botones = [(f.dia_corto(d, ahora.date()), f"dia:{d.isoformat()}") for d in dias[:6]]
        return [botones[i:i + 3] for i in range(0, len(botones), 3)]

    def _dias(self, e, ahora, saltar=None):
        """Botones con los próximos días que tienen turno libre para la cita que se arma."""
        return self._botones_dias(self._dias_libres(e, ahora, saltar), ahora)

    def _primer_dia(self, e, ahora):
        """«Lo más pronto», «cualquier día»: el primer día, desde hoy, con algún turno libre para esa cita. Si ya dijo la
        hora («cualquier día a las 3», o la de la cita que mueve), el primero en que esa hora está libre."""
        horas = [e.hora] if e.hora else fechas.lecturas(e.pedida) if e.pedida and e.pedida.hora is not None else []
        return next(iter((horas and self._dias_libres(e, ahora, horas=horas)) or self._dias_libres(e, ahora)), None)

    def _horas(self, horas):
        botones = [(f.hora(t), f"hor:{t.strftime('%H:%M')}") for t in horas]
        return [botones[i:i + 3] for i in range(0, len(botones), 3)]

    def _del_catalogo(self, catalogo, identificador):
        return next((x for x in catalogo if x["id"] == identificador), None)

    def _nota(self, e, perfil):
        """«A nombre de Samuel» cuando la cita es para otra persona."""
        if e.nombre and fechas.limpiar(e.nombre).split()[0] not in fechas.limpiar(perfil["nombre"] or "").split():
            return f"A nombre de {e.nombre}"
        return ""

    # ----------------------------------------------------------------------- confirmar y escribir en la agenda

    def _confirmar(self, uid, nombre, e, perfil, ahora):
        if e.espera != "confirmar":
            return [Respuesta("No tengo nada pendiente por confirmar. ¿Qué te hacemos?", MENU)]
        if perfil["cliente_id"] is None:
            e.espera, e.despues = "telefono", "ejecutar"
            return [Respuesta("Para dejarla a tu nombre necesito tu número de celular. " + PEDIR_NUMERO,
                              pedir_contacto=True)]
        return self._ejecutar(uid, nombre, e, perfil, ahora)

    def _ejecutar(self, uid, nombre, e, perfil, ahora):
        """La única parte del agente que escribe en la agenda. Solo se llega aquí después de confirmar."""
        try:
            if e.intencion == "cancelar":
                for otra in (e.varias or [])[1:]:   # «cancela todas»: las demás primero, la del marco al final
                    self.api.cancelar_cita(otra["id"])
                cita = self.api.cancelar_cita(e.cita["id"])
                self.estados.pop(uid, None)
                hecho = f"Listo, cancelé tu cita del {f.dia(inicio(cita).date())} a {f.las(inicio(cita).time())}"
                if e.varias:
                    hecho = f"Listo, cancelé tus {len(e.varias)} citas."
                if not e.siguiente:
                    return [Respuesta(f"{hecho} Cuando quieras volver, aquí estamos 💈")]
                # «cancélala, quiero una cita para el lunes»: sigue la cita nueva, con el mismo servicio si aún se ofrece
                nueva = self._estado(uid, ahora)
                servicio = self._del_catalogo(self.api.servicios(), cita["servicioId"])
                if servicio and servicio["activo"]:
                    nueva.servicio = servicio
                    nueva.aviso = f"Te busco turno para {servicio['nombre'].lower()}, como la que cancelaste. "
                return [Respuesta(f"{hecho} 👌")] + self._decidir(uid, nombre, nueva, perfil, e.siguiente,
                                                                 self.entender(e.siguiente), ahora)
            observaciones = ". ".join(x for x in (e.detalle, self._nota(e, perfil)) if x)
            datos = (perfil["cliente_id"], e.servicio["id"], e.barbero["id"], datetime.combine(e.dia, e.hora),
                     observaciones)
            if e.intencion == "reprogramar":
                cita, hecho = self.api.mover_cita(e.cita["id"], *datos), "¡Listo, te cambié la cita!"
            else:
                cita, hecho = self.api.crear_cita(*datos), self._una("¡Listo, quedó agendada! 💈", "¡Hecho, quedó agendada! 💈")
        except ErrorAPI as error:
            if error.estado == 0:
                raise
            if e.intencion == "cancelar":
                self.estados.pop(uid, None)
                return [Respuesta(error.mensaje)]
            if error.estado == 404 and "cliente" in error.mensaje:
                # el cliente que recordaba el perfil ya no está en la barbería: se vuelve a buscar por el número
                perfil["cliente_id"] = None
                self.perfiles.guardar()
                e.espera, e.despues = "telefono", "ejecutar"
                return [Respuesta("No encontré tu ficha en la barbería. " + PEDIR_NUMERO, pedir_contacto=True)]
            # la agenda cambió mientras conversábamos: se explica y se vuelve a ofrecer
            e.espera = e.hora = None
            e.aviso = error.mensaje + " "
            return self._avanzar(uid, nombre, e, perfil, ahora)

        # se informa lo que quedó en la agenda, tal como lo devolvió la API
        for clave, identificador in (("barberos", cita["barberoId"]), ("servicios", cita["servicioId"])):
            perfil[clave][str(identificador)] = perfil[clave].get(str(identificador), 0) + 1
        faltan = (inicio(cita).date() - ahora.date()).days
        if faltan <= 1:
            perfil["recordadas"].append(cita["id"])
        self.perfiles.guardar()
        self.estados.pop(uid, None)
        cierre = (f"Te escribo el {f.DIAS[(inicio(cita).date() - timedelta(days=1)).weekday()]} para recordártela."
                  if faltan > 1 else "Te espero.")
        nota = f"\n📝 {cita['observaciones']}" if cita.get("observaciones") else ""
        return [Respuesta(f"{hecho}\n{f.cita(cita)}{nota}\n{cierre}")]

    def _dejar(self, uid, e):
        """El cliente dijo que no."""
        intencion, pendiente = e.intencion, e.espera == "confirmar" or e.intencion
        self.estados.pop(uid, None)
        if not pendiente:
            return [Respuesta("Bueno, aquí estoy si necesitas algo 👍")]
        return [Respuesta({"cancelar": "Tranquilo, tu cita sigue en pie.",
                           "reprogramar": "Listo, tu cita queda como estaba."}.get(
            intencion, "Listo, no agendé nada. Cuando quieras, me escribes."))]

    # ----------------------------------------------------------------------- citas del cliente

    def _mias(self, perfil, ahora):
        return sorted((c for c in self.api.citas() if c["clienteId"] == perfil["cliente_id"]
                       and c["estado"] == "PROGRAMADA" and inicio(c) > ahora), key=inicio)

    def _mis_citas(self, e, perfil, ahora):
        if perfil["cliente_id"] is None:
            e.espera, e.despues = "telefono", "citas"
            return [Respuesta("Todavía no has agendado por este chat. Si ya eres cliente de la barbería, comparte tu "
                              "número y busco tus citas. " + PEDIR_NUMERO, pedir_contacto=True)]
        citas = self._mias(perfil, ahora)
        if not citas:
            if not e.intencion:                     # si ya está agendando, la cita en curso sigue como iba
                e.espera, e.pendiente = "duda", {clave: [] for clave in VACIO}   # un «sí» arranca la cita
            return [Respuesta("No tienes citas programadas. ¿Te agendo una?", [[("✂️ Agendar una cita", "menu:reservar")]])]
        return [Respuesta("Estas son tus citas:\n\n" + "\n\n".join(f.cita(c) for c in citas))]

    def _ubicar(self, uid, e, datos, perfil, ahora, nombre="", s=""):
        """Decide de cuál cita habla el cliente. Devuelve una respuesta si hay que detenerse a preguntar."""
        if perfil["cliente_id"] is None:
            e.espera, e.despues, e.pendiente = "telefono", "ubicar", datos
            return [Respuesta("No encuentro citas tuyas en este chat. Si ya eres cliente de la barbería, comparte tu "
                              "número y las busco. " + PEDIR_NUMERO, pedir_contacto=True)]
        citas = self._mias(perfil, ahora)
        if not citas and e.siguiente:
            # «cancela mi cita y agéndame una para el viernes» sin citas: no hay qué cancelar, se sigue con la nueva
            siguiente = e.siguiente
            nueva = self.estados[uid] = Estado(visto=ahora)
            return [Respuesta("No tienes citas programadas para cancelar, así que vamos con la nueva 👇")] + \
                self._decidir(uid, nombre, nueva, perfil, siguiente, self.entender(siguiente), ahora)
        if not citas:
            intencion = e.intencion
            e = self.estados[uid] = Estado(visto=ahora)
            if intencion == "reprogramar" and any(datos.values()):
                # no tiene cita que cambiar, pero dijo cuándo: lo más probable es que quiera una nueva
                e.pendiente, e.espera = datos, "duda"
                return [Respuesta("No tienes citas programadas para cambiar. ¿Te agendo una nueva con lo que me dijiste?",
                                  [[("Sí, agéndala", "duda:reservar"), ("No", "no")]])]
            e.espera, e.pendiente = "duda", {clave: [] for clave in VACIO}   # un «sí» arranca la cita
            return [Respuesta("No tienes citas programadas. ¿Te agendo una?", [[("✂️ Agendar una cita", "menu:reservar")]])]
        dias = {x.dia for x in datos["fecha"] if x.dia and not x.hasta}
        # «la del jueves» cuando este jueves no tiene cita: es la del jueves que viene
        semana = {fechas.DIAS.index(x) for x in re.findall(fechas._DIA, s)}
        dias = {d + timedelta(days=7) if d.weekday() in semana and all(inicio(c).date() != d for c in citas) else d
                for d in dias}
        salvo = _evitados(SALVO_LA, s, ahora.date()) if e.todas else set()    # «todas menos la del sábado»
        dias = {d for d in dias if not _evitado(salvo, d)}
        por_dia = [c for c in citas if inicio(c).date() in dias]
        varias_dias = e.intencion == "cancelar" and len(dias) > 1 and len(por_dia) > 1
        if e.cita is None and (e.todas or varias_dias):
            # «cancela todas mis citas», «cancela las dos del martes», «cancela la del martes y la del jueves»
            grupo = [c for c in (por_dia or citas) if not _evitado(salvo, inicio(c).date())]
            if len(grupo) > 1:
                e.varias, e.cita = grupo, grupo[0]
                return None
            if not grupo and salvo:
                self.estados.pop(uid, None)
                return [Respuesta("Aparte de esa no tienes más citas programadas, así que no cancelo nada 👍")]
            e.cita = grupo[0] if grupo else None
        if e.cita is None:
            horas = {t for h in datos["hora"] for t in fechas.lecturas(h)}
            por_hora = [c for c in (por_dia or citas) if inicio(c).time() in horas]
            unica = citas if len(citas) == 1 else por_hora if len(por_hora) == 1 else por_dia if len(por_dia) == 1 else None
            if unica is None:
                e.pendiente = datos
                botones = [[(f.cita_corta(c), f"cita:{c['id']}")] for c in citas]
                if e.intencion == "cancelar":
                    botones.append([(f"Cancelar las {len(citas)}", "cita:todas")])
                return [Respuesta("¿De cuál de tus citas me hablas?", botones)]
            e.cita = unica[0]
        # lo que nombra la cita actual («la del sábado», «la de las 3») no es un dato nuevo
        cuando = inicio(e.cita)
        datos["fecha"] = [x for x in datos["fecha"] if x.dia != cuando.date()]
        datos["hora"] = [h for h in datos["hora"] if cuando.time() not in fechas.lecturas(h)]
        return None

    # ----------------------------------------------------------------------- consultas

    def _servicios(self, datos):
        catalogo = self.api.servicios()
        lista = "\n".join(f"• {s['nombre']}: {f.precio(s['precio'])} · {s['duracionMinutos']} min"
                          for s in catalogo if s["activo"])
        agendar = [[("✂️ Agendar una cita", "menu:reservar")]]
        if not datos["servicio"]:
            return [Respuesta(f"Esto es lo que hacemos 💈\n{lista}", agendar)]
        texto = " y ".join(datos["servicio"])
        servicio = buscar_servicio(texto, catalogo)
        if servicio and servicio["activo"]:
            return [Respuesta(f"El {servicio['nombre'].lower()} vale {f.precio(servicio['precio'])} y dura como "
                              f"{servicio['duracionMinutos']} minutos. {servicio['descripcion']}.",
                              [[("✂️ Agendar uno", f"srv:{servicio['id']}")]])]
        motivo = (f"Por ahora no estamos haciendo {servicio['nombre'].lower()}." if servicio
                  else f"«{texto}» no lo hacemos por acá 😅")
        return [Respuesta(f"{motivo} Esto es lo que manejamos:\n{lista}", agendar)]

    def _disponibilidad(self, e, datos, texto, ahora):
        hoy, s = ahora.date(), fechas.limpiar(texto)
        por_horario = re.search(r"abren|cierran|hasta que hora|horario|abiert", s)
        ultima = datos["fecha"][-1] if datos["fecha"] else None
        franja = datos["franja"][-1] if datos["franja"] else None
        pedida = datos["hora"][-1] if datos["hora"] else None
        if ultima and ultima.habitual:
            dia_semana = fechas.DIAS.index(ultima.habitual) if ultima.habitual in fechas.DIAS else None
            return [Respuesta(f.horario(dia_semana))]
        if ultima is None and ((franja and franja.hoy) or (pedida and pedida.en_minutos is not None)):
            ultima = fechas.Fecha(hoy)
        if ultima is None and not por_horario and re.search(r"\bbarber|\bquien(es)?\b", s):
            return self._barberos(e)
        if ultima is None:
            if por_horario:
                return [Respuesta(f.horario())]
            e.pregunta = "dia"
            return [Respuesta(f"{f.horario()}\n¿Para qué día quieres mirar turnos?", self._dias(e, ahora))]

        barberos = [b for b in self.api.barberos() if b["activo"]]
        barbero = buscar_barbero(datos["barbero"][-1], barberos) if datos["barbero"] else None
        barbero = barbero if isinstance(barbero, dict) else None
        servicios = [x for x in self.api.servicios() if x["activo"]]
        servicio = buscar_servicio(" y ".join(datos["servicio"]), servicios) if datos["servicio"] else None
        duracion = servicio["duracionMinutos"] if servicio else min(x["duracionMinutos"] for x in servicios)
        citas, candidatos = self.api.citas(), [barbero] if barbero else barberos
        con_quien = f" con {f.pila(barbero['nombre'])}" if barbero else ""

        if ultima.hasta:                            # «esta semana», «el fin de semana»
            dias = [d for d in (ultima.dia + timedelta(days=i) for i in range((ultima.hasta - ultima.dia).days + 1))
                    if d >= hoy and turnos(d, duracion, candidatos, citas, ahora)]
            if not dias:
                return [Respuesta(f"Uy, en esos días ya no me quedan turnos{con_quien} 😕", self._dias(e, ahora))]
            e.rango = (ultima.dia, ultima.hasta)
            return [Respuesta(f"Tengo turnos{con_quien} estos días. ¿Cuál quieres mirar?",
                              [[(f.dia_corto(d, hoy), f"dia:{d.isoformat()}") for d in dias[:6]]])]

        dia = ultima.dia
        if dia.weekday() not in config.HORARIO:
            return [Respuesta(f.horario(dia.weekday()) + " ¿Miramos otro día?", self._dias(e, ahora))]
        apertura, cierre = config.HORARIO[dia.weekday()]
        # el contexto queda listo para agendar con un toque
        e.dia, e.rango, e.barbero, e.servicio = dia, None, barbero or e.barbero, servicio or e.servicio
        libres = turnos(dia, duracion, candidatos, citas, ahora)
        inicio_texto = f"El {f.dia(dia)} atendemos de {f.hora(apertura)} a {f.hora(cierre)} " if por_horario else ""
        if re.search(r"\bcuanto (cuesta|vale|valen|cobran|sale)\b|\bprecios?\b", s):
            # «¿cuánto cuesta y tienen cupo mañana?»: las dos respuestas en una
            precios = [f"el {x['nombre'].lower()} vale {f.precio(x['precio'])}" for x in ([servicio] if servicio else servicios)]
            inicio_texto = (", ".join(precios[:-1]) + " y " if len(precios) > 1 else "") + precios[-1] + ". " + inicio_texto
            inicio_texto = inicio_texto[0].upper() + inicio_texto[1:]
        lecturas, cerrada = [], None
        if pedida and pedida.hora is not None:
            lecturas, cerrada = fechas.resolver(pedida, apertura, cierre, franja)
            franja = None                           # la hora dice más que la franja
            if cerrada is not None:
                inicio_texto += (f"A {f.las(cerrada)} todavía no hemos abierto 😅 " if cerrada < apertura
                                 else f"A {f.las(cerrada)} ya cerramos 😕 ")
        if pedida and pedida.en_minutos is not None:
            franja = fechas.Franja(desde=(ahora + timedelta(minutes=pedida.en_minutos)).time())
        if lecturas and not _en_punto(lecturas[0], apertura):
            cercanos = _cercanas(libres, lecturas[0])
            if cercanos:
                return [Respuesta(f"{inicio_texto}Las citas son {CADA} ({_ejemplo(apertura)}). Lo más cerca de "
                                  f"{f.las(lecturas[0])} que tengo{con_quien} es:", self._horas(cercanos))]
            lecturas = []
        if lecturas:
            hora = lecturas[0]
            quienes = libres.get(hora) or libres_a(datetime.combine(dia, hora), duracion, candidatos, citas, ahora)
            if quienes:
                nombres = _y([f.pila(b["nombre"]) for b in quienes])
                return [Respuesta(f"{inicio_texto}¡Sí! El {f.dia(dia)} a {f.las(hora)} hay turno con {nombres}.",
                                  [[(f"Agendar a {f.las(hora)}", f"hor:{hora.strftime('%H:%M')}")]])]
            cercanos = _cercanas(libres, hora)
            if cercanos:
                return [Respuesta(f"{inicio_texto}A {f.las(hora)} ya no hay turno{con_quien}, pero cerca tengo estos:",
                                  self._horas(cercanos))]
        posibles = [t for t in libres if not franja or fechas.dentro(t, franja)]
        if not posibles:
            donde = " a esa hora" if franja else ""
            return [Respuesta(f"{inicio_texto}Uy, el {f.dia(dia)} ya no quedan turnos{donde}{con_quien} 😕 ¿Miramos otro día?",
                              self._dias(e, ahora, saltar=dia))]
        if pedida and pedida.en_minutos is not None:  # «¿ahorita me pueden atender?»: los primeros que quedan
            return [Respuesta(f"{inicio_texto}Lo más pronto que tengo{con_quien} hoy es a estas horas. Toca una y te la agendo:",
                              self._horas(posibles[:4]))]
        cuando = "Tengo" if por_horario else f"El {f.dia(dia)} tengo"   # el día ya lo dijo el horario
        mas = " Hay más horas entre esas; si quieres otra, escríbemela." if len(posibles) > 9 else ""
        return [Respuesta(f"{inicio_texto}{cuando} libre{con_quien} a estas horas.{mas} Toca una y te la agendo:",
                          self._horas(_repartidas(posibles, 9)))]

    def _barberos(self, e):
        """«¿Qué barberos hay?»: los que están atendiendo, con un botón para agendar con cada uno."""
        activos = [b for b in self.api.barberos() if b["activo"]]
        if not activos:
            return [Respuesta(f"Ahora mismo no hay barberos atendiendo. Puedes llamar a la barbería al {config.TELEFONO}.")]
        e.pregunta = "barbero"
        return [Respuesta(f"Estamos {_y([f.pila(b['nombre']) for b in activos])} 💈 ¿Con quién te quieres agendar?",
                          [[(f"Con {f.pila(b['nombre'])}", f"bar:{b['id']}") for b in activos]])]

    # ----------------------------------------------------------------------- botones

    def _boton(self, uid, nombre, e, perfil, dato, ahora):
        clave, _, valor = dato.partition(":")
        if clave == "ok":
            return self._confirmar(uid, nombre, e, perfil, ahora)
        if clave == "no":
            return self._dejar(uid, e)
        if clave == "cambiar":
            e.espera, e.pregunta = None, "cambio"
            return [Respuesta("Claro, ¿qué le cambiamos? Tócalo o escríbeme cómo lo quieres.", CAMBIOS)]
        if clave == "cam":
            # se borra lo que quiere cambiar y el agente lo vuelve a preguntar; lo demás se conserva
            if valor == "dia":
                e.quiso, e.dia, e.rango, e.hora = e.hora, None, None, None
                e.pronto = e.primer_dia = False     # ahora escoge él: no se vuelve a poner el primer día libre
            elif valor == "hora":
                e.hora = e.pedida = e.quiso = None
                e.franja = None
            elif valor == "barbero":
                e.barbero, e.cualquiera = None, False
            elif valor == "servicio":
                e.servicio, e.detalle = None, ""
            e.opciones, e.espera = None, None
            return self._avanzar(uid, nombre, e, perfil, ahora)
        if clave == "borrar":
            self.perfiles.borrar(uid)
            self.estados.pop(uid, None)
            return [Respuesta("Listo, borré tu perfil de este chat. ¡Que estés bien!")]
        if clave == "menu":
            return self._menu(uid, nombre, valor, perfil, ahora)
        if clave == "duda":
            datos, e.pendiente, e.espera = e.pendiente or {c: [] for c in VACIO}, None, None
            if valor == "precios":
                return self._servicios(datos)
            if valor != "reservar":
                return [Respuesta("¿Qué te hacemos?", MENU)]
            e.intencion = "reservar"
            self._aplicar(e, datos, perfil, ahora)
            return self._avanzar(uid, nombre, e, perfil, ahora)
        if clave == "rec":
            return self._recordatorio(uid, nombre, valor, perfil, ahora)
        if clave == "cita" and valor == "todas" and e.intencion == "cancelar":
            e.varias, e.pendiente = self._mias(perfil, ahora), None
            if not e.varias:
                return [Respuesta("Ya no tienes citas programadas. ¿Qué te hacemos?", MENU)]
            e.cita = e.varias[0]
            return self._avanzar(uid, nombre, e, perfil, ahora)
        if clave == "cita":
            cita = next((c for c in self._mias(perfil, ahora) if valor.isdigit() and c["id"] == int(valor)), None)
            if cita is None or e.intencion not in ("reprogramar", "cancelar"):
                return [Respuesta("Esa cita ya no está programada. ¿Qué te hacemos?", MENU)]
            e.cita, datos, e.pendiente = cita, e.pendiente or {clave: [] for clave in VACIO}, None
            self._ubicar(uid, e, datos, perfil, ahora)
            self._aplicar(e, datos, perfil, ahora)
            return self._avanzar(uid, nombre, e, perfil, ahora)

        # los demás botones llenan una ranura del marco
        if clave == "srv":
            e.servicio = self._del_catalogo(self.api.servicios(), int(valor))
        elif clave == "bar":
            e.barbero, e.cualquiera = (self._del_catalogo(self.api.barberos(), int(valor)), False) if valor != "0" else (None, True)
        elif clave == "dia":
            e.dia, e.rango = date.fromisoformat(valor), None
            if e.opciones and e.opciones[0][0] == "dia":
                e.opciones = None
            if e.intencion is None:                 # venía de preguntar por cupos
                return self._disponibilidad(e, {**{c: [] for c in VACIO}, "fecha": [fechas.Fecha(e.dia)]}, "", ahora)
        elif clave == "hor":
            e.hora, e.pedida, e.quiso = time.fromisoformat(valor), None, None
            if e.opciones and e.opciones[0][0] == "hora":
                e.opciones = None
        else:
            return [Respuesta("Ese botón ya no sirve 😅 ¿Qué te hacemos?", MENU)]
        if e.hora is None and not e.pedida and e.quiso:
            e.hora = e.quiso
        e.intencion = e.intencion or "reservar"
        e.fallos = 0
        return self._avanzar(uid, nombre, e, perfil, ahora)

    def _menu(self, uid, nombre, opcion, perfil, ahora):
        e = self.estados[uid] = Estado(visto=ahora)
        if opcion == "reservar":
            e.intencion = "reservar"
            return self._avanzar(uid, nombre, e, perfil, ahora)
        if opcion == "citas":
            return self._mis_citas(e, perfil, ahora)
        if opcion == "servicios":
            return self._servicios({clave: [] for clave in VACIO})
        if opcion == "horario":
            return [Respuesta(f.horario())]
        return [Respuesta(f"¡Claro! Puedes escribirle o llamar a la barbería al {config.TELEFONO}.")]

    def _recordatorio(self, uid, nombre, valor, perfil, ahora):
        accion, _, identificador = valor.partition(":")
        cita = next((c for c in self._mias(perfil, ahora) if c["id"] == int(identificador)), None)
        if cita is None:
            return [Respuesta("Esa cita ya no está programada.")]
        if accion == "ok":
            return [Respuesta("¡Listo, te espero! 💈")]
        e = self.estados[uid] = Estado(intencion="reprogramar" if accion == "cambiar" else "cancelar", cita=cita, visto=ahora)
        return self._avanzar(uid, nombre, e, perfil, ahora)

    # ----------------------------------------------------------------------- registro del cliente

    def _contacto(self, uid, nombre, e, perfil, telefono, ahora):
        numero = re.sub(r"\D", "", telefono)[-10:]
        cliente = next((c for c in self.api.clientes() if c["telefono"] == numero), None)
        despues, e.espera, e.despues = e.despues, None, None
        if cliente is None:
            if despues != "ejecutar":
                return [Respuesta("No encuentro un cliente con ese número. Cuando agendes tu primera cita quedas registrado.")]
            e.telefono, e.espera = numero, "documento"
            return [Respuesta("Veo que es tu primera vez con nosotros 🙌 Escríbeme tu número de documento para crearte "
                              "la ficha en la barbería.")]
        perfil["cliente_id"], perfil["nombre"] = cliente["id"], cliente["nombre"]
        self.perfiles.guardar()
        hallado = [Respuesta(f"¡Te encontré, {f.pila(cliente['nombre'])}! 🙌")]
        if despues == "ejecutar":
            return hallado + self._ejecutar(uid, nombre, e, perfil, ahora)
        if despues == "citas":
            return hallado + self._mis_citas(e, perfil, ahora)
        if despues == "ubicar":
            datos, e.pendiente = e.pendiente or {clave: [] for clave in VACIO}, None
            alto = self._ubicar(uid, e, datos, perfil, ahora)
            if alto:
                return hallado + alto
            self._aplicar(e, datos, perfil, ahora)
            return hallado + self._avanzar(uid, nombre, e, perfil, ahora)
        return hallado

    def _documento(self, uid, nombre, e, perfil, texto, ahora):
        numero = re.sub(r"[\s.,-]", "", texto)
        if not re.fullmatch(r"\d{6,10}", numero):
            if re.search(r"\b(no|cancel\w*|despues|luego)\b", fechas.limpiar(texto)):
                self.estados.pop(uid, None)
                return [Respuesta("Listo, no registré nada. Cuando quieras, me escribes.")]
            return [Respuesta("El documento tiene entre 6 y 10 números. Escríbelo sin puntos ni espacios, porfa.")]
        limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ' ]", "", nombre or "").strip()
        try:
            cliente = self.api.crear_cliente(limpio or e.nombre or "Cliente de Telegram", numero, e.telefono)
        except ErrorAPI as error:
            if error.estado != 409:
                raise
            self.estados.pop(uid, None)
            return [Respuesta(f"{error.mensaje} Para aclararlo, comunícate con la barbería al {config.TELEFONO}.")]
        perfil["cliente_id"], perfil["nombre"] = cliente["id"], cliente["nombre"]
        self.perfiles.guardar()
        e.espera = "confirmar"
        return [Respuesta(f"¡Ya quedaste registrado como {cliente['nombre']}! 🙌")] + self._ejecutar(uid, nombre, e, perfil, ahora)

    # ----------------------------------------------------------------------- apoyo

    def _no_entendi(self, uid, nombre, e, perfil, texto, ahora, fuera=False):
        s = fechas.limpiar(texto)
        pendiente = e.intencion in ("reservar", "reprogramar") and (e.espera == "confirmar" or e.pregunta)
        if re.fullmatch(SALUDO, s):
            if pendiente:                           # «hola» a mitad de la reserva: se saluda y se sigue donde iba
                quien = f", {f.pila(perfil['nombre'])}" if perfil["nombre"] else ""
                return self._y_seguimos(uid, nombre, e, perfil, [Respuesta(f"¡Qué más{quien}! 💈")], ahora)
            return [Respuesta(self._saludo(perfil), MENU)]
        if re.search(r"\bgracias\b", s):
            return self._y_seguimos(uid, nombre, e, perfil, [Respuesta(
                self._una("¡Con gusto! Aquí estoy para lo que necesites 💈", "¡A la orden! 💈"))], ahora)
        if re.search(DESPEDIDA, s):
            return [Respuesta("¡Nos vemos! Que estés bien 👋")]
        if re.search(r"\bbarberos\b|\bque barberos?\b|\bquienes (atienden|trabajan|son)\b", s):
            return self._barberos(e)
        aparte = self._aparte(s)
        if aparte:
            return aparte
        if re.fullmatch(RISA, s.replace(" ", "")) or (not s and not e.intencion):
            # «jajaja», «👍»: no hay nada que entender
            return [Respuesta(self._una("😄 ¿Te ayudo con algo más?", "😄 Aquí estoy si necesitas algo."))]
        if fuera:
            if e.intencion:
                return [Respuesta(FUERA)] + self._avanzar(uid, nombre, e, perfil, ahora)
            return [Respuesta(FUERA, MENU)]
        e.fallos += 1
        if e.espera == "confirmar" and e.fallos < 2:
            return [Respuesta("No te entendí bien 😅 Toca «Sí, agéndala» para dejarla así, o dime qué le cambio.")]
        if e.intencion and e.fallos < 2:
            return [Respuesta("Uy, no te entendí bien 😅")] + self._avanzar(uid, nombre, e, perfil, ahora)
        if e.fallos < 2:
            return [Respuesta("Uy, no te entendí bien 😅 ¿Me lo dices de otra forma? También puedes tocar una opción:", MENU)]
        # dos turnos sin avanzar: menú con las acciones posibles y la opción de hablar con el barbero
        return [Respuesta("Creo que no te estoy entendiendo. Te dejo las opciones, o si prefieres habla directo con "
                          "el barbero:", MENU)]

    def _cortesia(self, texto):
        s = fechas.limpiar(texto)
        return bool(re.fullmatch(SALUDO, s) or re.search(r"\bgracias\b", s) or re.search(DESPEDIDA, s))

    def _saludo(self, perfil):
        nombre = f", {f.pila(perfil['nombre'])}" if perfil["nombre"] else ""
        return self._una(f"¡Qué más{nombre}! 💈 ¿Qué te hacemos hoy?", f"¡Hola{nombre}! 💈 ¿En qué te ayudo?",
                         f"¡Buenas{nombre}! 💈 ¿Qué te hacemos hoy?")

    def _charla(self, texto):
        """Lo que un barbero le contestaría a «estoy muy mechudo» antes de agendar."""
        s = fechas.limpiar(texto)
        return next((frase for patron, frase in CHARLA if re.search(patron, s)), "")

    def _contexto(self, e):
        """En qué punto va la conversación, para que el LLM lea el mensaje como lo leería una persona."""
        partes = [{"reservar": "El cliente está agendando una cita.", "reprogramar": "El cliente está cambiando una cita que ya tiene.",
                   "cancelar": "El cliente está cancelando una cita."}.get(e.intencion, "")]
        lleva = [x for x in (e.servicio and e.servicio["nombre"], e.dia and f.dia(e.dia), e.hora and f.hora(e.hora),
                             e.barbero and f.pila(e.barbero["nombre"])) if x]
        if lleva:
            partes.append("Lleva: " + ", ".join(lleva) + ".")
        if e.espera == "confirmar":
            partes.append("El agente mostró el resumen y espera que el cliente confirme o corrija algo.")
        elif e.pregunta:
            partes.append("El agente acaba de preguntar " + {
                "servicio": "qué servicio quiere.", "dia": "para qué día.", "hora": "a qué hora.",
                "barbero": "con qué barbero.", "opcion": "cuál de dos opciones prefiere.",
                "cambio": "qué quiere cambiar de la cita que está agendando."}[e.pregunta])
        return " ".join(p for p in partes if p)

    def _estado(self, uid, ahora):
        e = self.estados.get(uid)
        if e is None or (e.visto and ahora - e.visto > timedelta(hours=2)):
            e = self.estados[uid] = Estado()
        e.visto = ahora
        return e

    def _seguro(self, paso):
        try:
            return paso()
        except ErrorAPI as error:
            return [Respuesta(error.mensaje)]

    def _registrar(self, texto, resultado, ahora):
        """Guarda el mensaje sin nada que identifique a quien lo escribió, para medir y mejorar el clasificador."""
        if not self.registro:
            return
        dato = {"fecha": ahora.isoformat(timespec="minutes"), "texto": texto, **resultado}
        if callable(self.registro):             # en Vercel: una tabla de la base de datos (almacen.RegistroBD)
            self.registro(dato)
            return
        self.registro.parent.mkdir(exist_ok=True)
        with open(self.registro, "a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(dato, ensure_ascii=False) + "\n")


CADA = "cada media hora" if config.PASO == 30 else f"cada {config.PASO} minutos"


def _minutos(m):
    """«Una hora más tarde» -> 60, «media hora antes» -> -30. `m` es un resultado de DESPLAZA."""
    cantidad = {"media": 30, "una": 60, "un": 60, "dos": 120, "tres": 180}.get(m.group(1)) or 60 * int(m.group(1))
    return cantidad if m.group(4) in ("tarde", "despues") else -cantidad


def _en_punto(hora, apertura):
    """La hora cae en un turno: desde la apertura, de PASO en PASO minutos (9:00, 9:30, 10:00…)."""
    return (hora.hour * 60 + hora.minute - apertura.hour * 60 - apertura.minute) % config.PASO == 0


def _ejemplo(apertura):
    """«9:00, 9:30, 10:00…»: los primeros turnos del día, para explicar cómo van."""
    primero = datetime.combine(date.min, apertura)
    return ", ".join(f.hora((primero + timedelta(minutes=config.PASO * i)).time())[:-6] for i in range(3)) + "…"


def _cercanas(libres, hora, cuantas=3):
    """Los turnos libres más cercanos a la hora pedida; si empatan, primero el de después."""
    minutos = lambda t: t.hour * 60 + t.minute
    return sorted(sorted(libres, key=lambda t: (abs(minutos(t) - minutos(hora)), t < hora))[:cuantas])


def _evitados(patron, s, hoy):
    """«Que no sea el lunes» -> {0}; «menos el 26» -> {date(…, 26)}: días de la semana o fechas que descarta."""
    salida = set()
    for m in re.finditer(patron, s):
        textos, fin = [m.group("dia") or m.group("fecha")], m.end()
        while sigue := re.match(_Y_OTRO, s[fin:]):     # «menos hoy ni mañana», «menos el lunes y el martes»
            textos.append(sigue.group("dia") or sigue.group("fecha"))
            fin += sigue.end()
        for texto in textos:
            if semana := re.fullmatch(rf"{fechas._DIA}s?", texto):
                salida.add(fechas.DIAS.index(semana.group(1)))
            elif (leida := fechas.fecha(("el " if texto[0].isdigit() else "") + texto, hoy)) and leida.dia:
                salida.add(leida.dia)
    return salida


def _evitado(evitar, dia):
    return dia in evitar or dia.weekday() in evitar


def _dias_texto(evitar):
    """{0, date(2026, 10, 30)} -> «el lunes ni el 30»."""
    semana = [f"el {f.DIAS[x]}" for x in sorted(x for x in evitar if isinstance(x, int))]
    fechas_ = [f"el {x.day}" for x in sorted(x for x in evitar if isinstance(x, date))]
    return " ni ".join(semana + fechas_)


def _en_franja(franja):
    """« en la mañana», « en la tarde», « después de las 4:00 p. m.»: la franja para decirla en una frase."""
    if franja is None:
        return ""
    if franja.desde is None and franja.hasta and franja.hasta <= time(12):
        return " temprano" if franja.hasta <= time(10, 30) else " en la mañana"
    if franja.desde is not None and franja.desde >= time(18) and franja.hasta is None:
        return " en la noche"
    if (franja.desde, franja.hasta) == (time(12), time(18)):
        return " en la tarde"
    if franja.desde is not None and franja.hasta is not None:
        return f" entre {f.las(franja.desde)} y {f.las(franja.hasta)}"
    return f" después de {f.las(franja.desde)}" if franja.desde is not None else f" antes de {f.las(franja.hasta)}"


def _pegada(cita, lado, duracion):
    """La hora en la grilla de turnos justo después de otra cita, o la que termina justo cuando esa empieza."""
    apertura = config.HORARIO.get(inicio(cita).weekday(), (time(0),))[0]
    if lado == "antes":
        cuando = inicio(cita) - timedelta(minutes=duracion)
        corrida = -((cuando.hour * 60 + cuando.minute - apertura.hour * 60 - apertura.minute) % config.PASO)
    else:
        cuando = inicio(cita) + timedelta(minutes=cita["duracionMinutos"])
        corrida = -(cuando.hour * 60 + cuando.minute - apertura.hour * 60 - apertura.minute) % config.PASO
    return (cuando + timedelta(minutes=corrida)).time()


def _y(nombres):
    """[«Andrés», «Julián», «Felipe»] -> «Andrés, Julián y Felipe»."""
    return " y ".join(", ".join(nombres).rsplit(", ", 1))


def _saludo_de_vuelta(s, nombre):
    """«Hola, buenas noches, necesito…» -> «¡Buenas noches, Carlos! ». Vacío si el mensaje no saluda."""
    m = re.match(r"(?:(?:hola+|ola|hey|oe+)\s+)?(buen(?:os|as)? (?:dias|tardes|noches)|buen dia|buenas|hola+|que mas|quiubo)\b", s)
    if not m:
        return ""
    dicho = m.group(1)
    saludo = ("Hola" if dicho.startswith("hola") else "Qué más" if dicho == "que mas" else "Quiubo" if dicho == "quiubo"
              else "Buenos días" if "dia" in dicho else dicho.capitalize())
    return f"¡{saludo}{', ' + f.pila(nombre) if nombre else ''}! "


def _repartidas(horas, cuantas):
    """Hasta `cuantas` horas repartidas a lo largo del día, para no llenar el chat de botones."""
    if len(horas) <= cuantas:
        return list(horas)
    paso = (len(horas) - 1) / (cuantas - 1)
    return [list(horas)[round(i * paso)] for i in range(cuantas)]
