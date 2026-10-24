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
            return [Respuesta(PEDIR_NUMERO, pedir_contacto=True)]
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
        intencion = resultado["intencion"]
        datos = self._leer(resultado["ranuras"], ahora)
        con_datos = any(datos.values())
        dudoso = resultado["confianza"] < config.UMBRAL or intencion == "fuera_de_alcance"
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
                return self._no_entendi(uid, nombre, e, perfil, texto, ahora)
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
            return self._servicios(datos)
        if intencion == "consultar_citas":
            return self._mis_citas(e, perfil, ahora)
        if intencion == "consultar_disponibilidad":
            return self._disponibilidad(e, datos, texto, ahora)

        # Un mensaje que solo trae datos se clasifica como reservar, pero pertenece a la tarea en curso
        nueva = e.intencion is None
        if intencion in ("reprogramar", "cancelar") and e.intencion != intencion:
            e = self.estados[uid] = Estado(intencion=intencion, visto=ahora)
        elif e.intencion is None:
            e.intencion = "reservar"
        e.espera = None
        if e.intencion in ("reprogramar", "cancelar"):
            alto = self._ubicar(uid, e, datos, perfil, ahora)
            if alto:
                return alto
        limpio = fechas.limpiar(texto)
        if re.search(r"\blo (mismo )?de siempre\b|\blo mismo de la (otra|ultima) vez\b", limpio) \
                and not any(re.search(EL_DE_SIEMPRE, fechas.limpiar(s)) for s in datos["servicio"]):
            datos["servicio"] = ["lo de siempre"]   # «quiero lo de siempre» aunque el clasificador lo parta
        elif e.intencion == "reservar" and e.servicio is None and not datos["servicio"]:
            # el clasificador no marcó el servicio pero el mensaje lo nombra («un corte», «una afeitada»), o lo
            # da por hecho («me motila mañana», «estoy muy mechudo»): un barbero entiende de qué se trata
            nombrados = [nombre for nombre, patron in SERVICIO_IMPLICITO if re.search(patron, limpio)]
            if nombrados:
                datos["servicio"] = [" y ".join(nombrados)]
        self._aplicar(e, datos, perfil, ahora)
        respuestas = self._avanzar(uid, nombre, e, perfil, ahora)
        if nueva and e.intencion == "reservar":
            respuestas[0].texto = self._charla(texto) + respuestas[0].texto
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
            if re.search(r"\d", texto):            # «con el 2 a los lados»: el número es de la guarda, no un barbero
                continue
            catalogo = self.api.barberos()
            barbero = buscar_barbero(texto, catalogo)
            if barbero == "habitual":
                barbero = self._habitual(perfil, "barberos", catalogo) or "cualquiera"
            if barbero == "cualquiera":
                e.barbero, e.cualquiera = None, True
            elif barbero is None:
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
            return [Respuesta(f"¿Seguro que te cancelo esta cita?\n{f.cita(e.cita)}",
                              [[("Sí, cancélala", "ok"), ("No, déjala", "no")]])]
        if e.intencion == "reprogramar":
            antes = inicio(e.cita)
            if not (e.servicio or e.barbero or e.cualquiera or e.dia or e.rango or e.hora or e.pedida or e.franja):
                return self._preguntar(e, "dia", f"Tu cita está así:\n{f.cita(e.cita)}\n¿Para cuándo te la paso?",
                                       self._dias(ahora, None))
            # lo que el cliente no cambió se conserva de la cita actual
            e.servicio = e.servicio or self._del_catalogo(self.api.servicios(), e.cita["servicioId"])
            if not e.barbero and not e.cualquiera:
                e.barbero = self._del_catalogo(self.api.barberos(), e.cita["barberoId"])
            if not e.rango and not e.opciones:
                e.dia = e.dia or antes.date()
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
            return self._preguntar(e, "servicio", aviso + self._una("¿Qué te vas a hacer? ✂️", "¿Qué te hacemos? ✂️"),
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
        if e.dia is None:
            return self._preguntar(e, "dia", aviso + self._una("¿Para qué día te anoto?", "¿Qué día te queda bien?"),
                                   self._dias(ahora, e.rango))

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
                    texto = (f"{aviso}Las citas son {CADA} ({_ejemplo(apertura)}), así que a las {f.hora(pedida_hora)} "
                             "no te la puedo dar.")
                    if not cercanos:
                        return self._sin_turnos(e, texto + " ", con_quien, ahora)
                    return self._preguntar(e, "hora", f"{texto} Lo más cerca que tengo{con_quien} es:",
                                           self._horas(cercanos))
                if abiertas:
                    e.hora = abiertas[0]
                elif cerrada is not None and cerrada < apertura:
                    aviso += f"A las {f.hora(cerrada)} todavía no hemos abierto 😅 Abrimos a las {f.hora(apertura)} "
                    borde = "primeras"
                elif cerrada is not None:
                    aviso += f"A las {f.hora(cerrada)} ya cerramos 😕 Atendemos hasta las {f.hora(cierre)} "
                    borde = "ultimas"
                else:                              # «a las 8»: ni las 8 de la mañana ni las 8 de la noche
                    aviso += (f"A las {f.hora(fechas.lecturas(pedida)[0])[:-6]} no estamos atendiendo; abrimos de "
                              f"{f.hora(apertura)} a {f.hora(cierre)} ")

        if e.hora is None:
            posibles = [t for t in libres if not e.franja or fechas.dentro(t, e.franja)]
            if borde == "primeras":
                posibles = posibles[:4]
            elif borde == "ultimas":
                posibles = posibles[-4:]
            if not posibles and libres and e.franja:
                if e.franja.hasta is not None and e.franja.hasta <= apertura:
                    aviso += f"A esa hora todavía no hemos abierto 😅 Abrimos a las {f.hora(apertura)} "
                    posibles = list(libres)[:4]
                elif e.franja.desde is not None and e.franja.desde >= cierre:
                    aviso += f"A esa hora ya cerramos; atendemos hasta las {f.hora(cierre)} "
                    posibles = list(libres)[-4:]
                else:
                    aviso += "En esa franja ya no me quedan turnos. "
                    posibles = list(libres)
                e.franja = None
            if not posibles:
                return self._sin_turnos(e, aviso, con_quien, ahora)
            return self._preguntar(e, "hora", aviso + f"El {f.dia(e.dia)} tengo libre{con_quien} a estas horas. "
                                   "¿Cuál te sirve?", self._horas(_repartidas(posibles, 8)))

        cuando = datetime.combine(e.dia, e.hora)
        quienes = libres_a(cuando, duracion, candidatos, citas, ahora, excepto)
        if not quienes:
            fin = (cuando + timedelta(minutes=duracion)).time()
            if cuando <= ahora:
                motivo = "Esa hora ya pasó."
            elif e.hora < apertura or fin > cierre or fin < e.hora:
                motivo = f"A esa hora no alcanzamos a atenderte; abrimos de {f.hora(apertura)} a {f.hora(cierre)}"
            elif elegido and any(c["barberoId"] == elegido["id"] and inicio(c) == cuando for c in citas):
                motivo = f"{f.pila(elegido['nombre'])} ya tiene una cita a las {f.hora(e.hora)[:-6]}."
            elif elegido:
                motivo = f"{f.pila(elegido['nombre'])} no alcanza a atenderte a las {f.hora(e.hora)[:-6]} porque tiene otra cita."
            else:
                motivo = f"A las {f.hora(e.hora)[:-6]} ya no me queda turno."
            cercanos, e.quiso, e.hora = _cercanas(libres, e.hora), e.hora, None
            if not cercanos:
                return self._sin_turnos(e, aviso + motivo + " ", con_quien, ahora)
            return self._preguntar(e, "hora", f"{aviso}{motivo} ¿Te sirve alguna de estas?", self._horas(cercanos))

        if elegido is None:
            if not e.cualquiera and len(quienes) > 1:
                return self._preguntar(e, "barbero", aviso + "¿Con quién te quieres atender? Si te da igual, dime "
                                       "«cualquiera».", [[(f.pila(b["nombre"]), f"bar:{b['id']}") for b in quienes],
                                                         [("Me da igual", "bar:0")]])
            e.barbero = self._habitual(perfil, "barberos", quienes) or quienes[0]

        if e.cita and (e.servicio["id"], e.barbero["id"], cuando) == (e.cita["servicioId"], e.cita["barberoId"], inicio(e.cita)):
            e.dia = e.hora = None
            return self._preguntar(e, "dia", aviso + "Así es como está tu cita ahora. ¿Para cuándo te la paso?",
                                   self._dias(ahora, None))
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
                               "¿Te sirve otro día?", self._dias(ahora, None, saltar=dia))

    def _preguntar(self, e, que, texto, botones):
        e.pregunta, e.espera = que, None
        return [Respuesta(texto, botones)]

    def _dias(self, ahora, rango, saltar=None):
        """Botones con los próximos días en que se atiende (o los del intervalo que dijo el cliente)."""
        hoy = ahora.date()
        desde, hasta = (max(rango[0], hoy), rango[1]) if rango else (hoy, hoy + timedelta(days=13))
        dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
        dias = [d for d in dias if d.weekday() in config.HORARIO and d != saltar
                and (d > hoy or ahora.time() < config.HORARIO[d.weekday()][1])][:6]
        botones = [(f.dia_corto(d, hoy), f"dia:{d.isoformat()}") for d in dias]
        return [botones[i:i + 3] for i in range(0, len(botones), 3)]

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
                cita = self.api.cancelar_cita(e.cita["id"])
                self.estados.pop(uid, None)
                return [Respuesta(f"Listo, cancelé tu cita del {f.dia(inicio(cita).date())} a las "
                                  f"{f.hora(inicio(cita).time())} Cuando quieras volver, aquí estamos 💈")]
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
            return [Respuesta("No tienes citas programadas. ¿Te agendo una?", [[("✂️ Agendar una cita", "menu:reservar")]])]
        return [Respuesta("Estas son tus citas:\n\n" + "\n\n".join(f.cita(c) for c in citas))]

    def _ubicar(self, uid, e, datos, perfil, ahora):
        """Decide de cuál cita habla el cliente. Devuelve una respuesta si hay que detenerse a preguntar."""
        if perfil["cliente_id"] is None:
            e.espera, e.despues, e.pendiente = "telefono", "ubicar", datos
            return [Respuesta("No encuentro citas tuyas en este chat. Si ya eres cliente de la barbería, comparte tu "
                              "número y las busco. " + PEDIR_NUMERO, pedir_contacto=True)]
        citas = self._mias(perfil, ahora)
        if not citas:
            intencion = e.intencion
            e = self.estados[uid] = Estado(visto=ahora)
            if intencion == "reprogramar" and any(datos.values()):
                # no tiene cita que cambiar, pero dijo cuándo: lo más probable es que quiera una nueva
                e.pendiente, e.espera = datos, "duda"
                return [Respuesta("No tienes citas programadas para cambiar. ¿Te agendo una nueva con lo que me dijiste?",
                                  [[("Sí, agéndala", "duda:reservar"), ("No", "no")]])]
            return [Respuesta("No tienes citas programadas. ¿Te agendo una?", [[("✂️ Agendar una cita", "menu:reservar")]])]
        if e.cita is None:
            dias = {x.dia for x in datos["fecha"] if x.dia and not x.hasta}
            horas = {t for h in datos["hora"] for t in fechas.lecturas(h)}
            por_dia = [c for c in citas if inicio(c).date() in dias]
            por_hora = [c for c in (por_dia or citas) if inicio(c).time() in horas]
            unica = citas if len(citas) == 1 else por_hora if len(por_hora) == 1 else por_dia if len(por_dia) == 1 else None
            if unica is None:
                e.pendiente = datos
                return [Respuesta("¿De cuál de tus citas me hablas?", [[(f.cita_corta(c), f"cita:{c['id']}")] for c in citas])]
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
            return [Respuesta(f"{f.horario()}\n¿Para qué día quieres mirar turnos?", self._dias(ahora, None))]

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
                return [Respuesta(f"Uy, en esos días ya no me quedan turnos{con_quien} 😕", self._dias(ahora, None))]
            e.rango = (ultima.dia, ultima.hasta)
            return [Respuesta(f"Tengo turnos{con_quien} estos días. ¿Cuál quieres mirar?",
                              [[(f.dia_corto(d, hoy), f"dia:{d.isoformat()}") for d in dias[:6]]])]

        dia = ultima.dia
        if dia.weekday() not in config.HORARIO:
            return [Respuesta(f.horario(dia.weekday()), self._dias(ahora, None))]
        apertura, cierre = config.HORARIO[dia.weekday()]
        # el contexto queda listo para agendar con un toque
        e.dia, e.rango, e.barbero, e.servicio = dia, None, barbero or e.barbero, servicio or e.servicio
        libres = turnos(dia, duracion, candidatos, citas, ahora)
        inicio_texto = f"El {f.dia(dia)} atendemos de {f.hora(apertura)} a {f.hora(cierre)} " if por_horario else ""
        lecturas, cerrada = [], None
        if pedida and pedida.hora is not None:
            lecturas, cerrada = fechas.resolver(pedida, apertura, cierre, franja)
            franja = None                           # la hora dice más que la franja
            if cerrada is not None:
                inicio_texto += (f"A las {f.hora(cerrada)} todavía no hemos abierto 😅 " if cerrada < apertura
                                 else f"A las {f.hora(cerrada)} ya cerramos 😕 ")
        if pedida and pedida.en_minutos is not None:
            franja = fechas.Franja(desde=(ahora + timedelta(minutes=pedida.en_minutos)).time())
        if lecturas and not _en_punto(lecturas[0], apertura):
            cercanos = _cercanas(libres, lecturas[0])
            if cercanos:
                return [Respuesta(f"{inicio_texto}Las citas son {CADA} ({_ejemplo(apertura)}). Lo más cerca de las "
                                  f"{f.hora(lecturas[0])} que tengo{con_quien} es:", self._horas(cercanos))]
            lecturas = []
        if lecturas:
            hora = lecturas[0]
            quienes = libres.get(hora) or libres_a(datetime.combine(dia, hora), duracion, candidatos, citas, ahora)
            if quienes:
                nombres = " y ".join(f.pila(b["nombre"]) for b in quienes)
                return [Respuesta(f"{inicio_texto}¡Sí! El {f.dia(dia)} a las {f.hora(hora)} hay turno con {nombres}.",
                                  [[(f"Agendar a las {f.hora(hora)}", f"hor:{hora.strftime('%H:%M')}")]])]
            cercanos = _cercanas(libres, hora)
            if cercanos:
                return [Respuesta(f"{inicio_texto}A las {f.hora(hora)} ya no hay turno{con_quien}, pero cerca tengo estos:",
                                  self._horas(cercanos))]
        posibles = [t for t in libres if not franja or fechas.dentro(t, franja)]
        if not posibles:
            donde = " a esa hora" if franja else ""
            return [Respuesta(f"{inicio_texto}Uy, el {f.dia(dia)} ya no quedan turnos{donde}{con_quien} 😕 ¿Miramos otro día?",
                              self._dias(ahora, None, saltar=dia))]
        return [Respuesta(f"{inicio_texto}El {f.dia(dia)} tengo libre{con_quien} a estas horas. Toca una y te la agendo:",
                          self._horas(_repartidas(posibles, 9)))]

    def _barberos(self, e):
        """«¿Qué barberos hay?»: los que están atendiendo, con un botón para agendar con cada uno."""
        activos = [b for b in self.api.barberos() if b["activo"]]
        if not activos:
            return [Respuesta(f"Ahora mismo no hay barberos atendiendo. Puedes llamar a la barbería al {config.TELEFONO}.")]
        nombres = " y ".join(", ".join(f.pila(b["nombre"]) for b in activos).rsplit(", ", 1))
        e.pregunta = "barbero"
        return [Respuesta(f"Estamos {nombres} 💈 ¿Con quién te quieres agendar?",
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
        if clave == "cita":
            cita = next((c for c in self._mias(perfil, ahora) if c["id"] == int(valor)), None)
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

    def _no_entendi(self, uid, nombre, e, perfil, texto, ahora):
        s = fechas.limpiar(texto)
        if re.fullmatch(SALUDO, s):
            return [Respuesta(self._saludo(perfil), MENU)]
        if re.search(r"\bgracias\b", s):
            return [Respuesta(self._una("¡Con gusto! Aquí estoy para lo que necesites 💈", "¡A la orden! 💈"))]
        if re.search(DESPEDIDA, s):
            return [Respuesta("¡Nos vemos! Que estés bien 👋")]
        if re.search(r"\bbarberos\b|\bque barberos?\b|\bquienes (atienden|trabajan|son)\b", s):
            return self._barberos(e)
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


def _repartidas(horas, cuantas):
    """Hasta `cuantas` horas repartidas a lo largo del día, para no llenar el chat de botones."""
    if len(horas) <= cuantas:
        return list(horas)
    paso = (len(horas) - 1) / (cuantas - 1)
    return [list(horas)[round(i * paso)] for i in range(cuantas)]
