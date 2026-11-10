"""LLM de respaldo: interpreta los mensajes que el clasificador no entiende.

Recibe el mensaje y el punto de la conversación, y devuelve el mismo marco que el clasificador: una
intención y unas ranuras copiadas del mensaje. No conversa con el cliente ni tiene acceso a la agenda:
lo que devuelve pasa por el normalizador de fechas, por el catálogo y por la confirmación, igual que
lo que dice el clasificador. Si el servicio no responde devuelve None y el agente sigue con sus menús.

Usa un modelo abierto servido por Groq. La clave va en .env como GROQ_API_KEY. Desde noviembre de 2026 puede
consultar dos servidores MCP de solo lectura (herramientas.py): la barbería y el calendario. Con ellos interpreta
mejor y contesta preguntas abiertas sobre la barbería con datos reales; sigue sin poder escribir en la agenda.
"""
import json
import re
import time
import urllib.error
import urllib.request

from . import config

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELO = "openai/gpt-oss-120b"
INTENCIONES = ["reservar", "reprogramar", "cancelar", "consultar_disponibilidad", "consultar_servicios",
               "consultar_citas", "afirmar", "negar", "fuera_de_alcance"]
RANURAS = ["servicio", "barbero", "fecha", "hora", "franja", "nombre"]

# El esquema, descrito con palabras y sin ejemplos resueltos. Es el mismo de corpus/guia_anotacion.md.
ESQUEMA = """Eres el módulo de comprensión de un bot de Telegram que agenda citas en una barbería de Colombia. \
Lees un mensaje de un cliente y devuelves su intención y sus ranuras. No conversas ni le respondes.

Intenciones (elige una):
- reservar: pide una cita nueva. También cuando el mensaje solo trae datos de una cita (un día, una hora, un \
servicio, un barbero o un nombre) sin decir qué hacer con ellos, cuando acepta o rechaza algo pero añade un dato, \
o cuando corrige la cita que está agendando («no, la cita es para el 16»).
- reprogramar: cambia algo de una cita que ya tiene: el día, la hora, el barbero o el servicio.
- cancelar: quiere anular una cita que ya tiene, o avisa que no va a ir sin proponer otro momento.
- consultar_disponibilidad: pregunta por cupos, turnos libres, el horario de atención o qué barberos hay.
- consultar_servicios: pregunta por servicios, precios, duración o promociones.
- consultar_citas: pregunta por sus propias citas ya agendadas.
- afirmar: acepta o confirma, sin dar datos nuevos.
- negar: rechaza, sin dar datos nuevos.
- fuera_de_alcance: todo lo demás: saludos o agradecimientos sueltos, dirección, medios de pago, productos, \
empleo, quejas, consejos, otros negocios y otros temas.
Si un mensaje pregunta y además pide agendar, es reservar.

Ranuras: tramos copiados literalmente del mensaje, sin cambiar ni una letra.
- servicio: lo que quiere que le hagan, como sustantivo o como verbo con su complemento, sin el artículo. Dos \
servicios unidos por «y», «con», «más» o «+» van en un solo tramo. La descripción de cómo quiere el corte también \
es servicio y va completa, con el número de la guarda y su artículo: «solo las puntas», «el 7 con desvanecido», \
«degradado con el 2 a los lados». Un número que describe el corte nunca es fecha ni hora.
- barbero: el nombre o apodo del barbero, sin «con» ni «don»; o la expresión completa cuando no tiene \
preferencia («cualquiera», «cualquiera de los dos», «el que esté libre») o pide el de siempre.
- fecha: el día, con su artículo o determinante si lo tiene, pero sin «para» ni «de». Después de «del» o «pal» \
el tramo empieza en la palabra siguiente.
- hora: la hora de reloj con la partícula que la introduce («a las», «tipo», «como a las»), pero sin «para», \
«de», «desde» ni «hasta».
- franja: una parte del día o un intervalo, con su «en la» o «por la», pero sin «para».
- nombre: el nombre del cliente o de la persona para quien es la cita, sin «a nombre de» ni «soy».
Afirmar, negar y fuera_de_alcance no llevan ranuras. No anotes lo que no describe la cita («tengo matrimonio el \
sábado»), lo que el cliente niega («no el 7») ni expresiones vagas. El cliente escribe como se habla en Colombia: \
«oe parce», «sisas», «le caigo mañana», «estoy muy mechudo»."""

UNO = '\n\nResponde solo con JSON: {"intencion": "...", "ranuras": [{"tipo": "...", "valor": "..."}]}'


class SinRespuesta(Exception):
    def __init__(self, mensaje, cuerpo=""):
        super().__init__(mensaje)
        self.cuerpo = cuerpo            # el cuerpo completo del error de la API, si lo hubo


def _pedir(cuerpo, espera, reintentos=0, tope_429=None):
    """Una llamada a la API de Groq. Devuelve la respuesta completa (JSON).

    Con un 429 (límite de tokens por minuto) se espera lo que pide el servicio y se reintenta, salvo que pida más de
    tope_429 segundos: en una conversación no se hace esperar al cliente más que eso."""
    pedido = urllib.request.Request(URL, data=json.dumps(cuerpo).encode("utf-8"), headers={
        "Authorization": "Bearer " + config.leer_env("GROQ_API_KEY"), "Content-Type": "application/json",
        "User-Agent": "tbot/1.0"})
    for intento in range(reintentos + 1):
        try:
            with urllib.request.urlopen(pedido, timeout=espera) as respuesta:
                return json.load(respuesta)
        except urllib.error.HTTPError as error:
            pausa = float(error.headers.get("retry-after", 20)) + 1
            if error.code == 429 and intento < reintentos and (tope_429 is None or pausa <= tope_429):
                time.sleep(pausa)                                   # límite por minuto: se espera lo que pide el servicio
                continue
            cuerpo_error = error.read().decode("utf-8", "replace")
            raise SinRespuesta(f"HTTP {error.code}: {cuerpo_error[:300]}", cuerpo_error) from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise SinRespuesta(type(error).__name__) from None


def chat(sistema, usuario, esfuerzo="low", espera=20, reintentos=0, maximo=1500):
    """Una pregunta al modelo, sin herramientas. Devuelve el JSON de la respuesta y los tokens que gastó."""
    cuerpo = {"model": MODELO, "temperature": 0, "reasoning_effort": esfuerzo, "max_completion_tokens": maximo,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    datos = _pedir(cuerpo, espera, reintentos)
    try:
        return json.loads(datos["choices"][0]["message"]["content"]), datos["usage"]["total_tokens"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise SinRespuesta(type(error).__name__) from None


def validar(marco, texto):
    """Deja solo lo que cumple el esquema: una intención conocida y ranuras que estén tal cual en el mensaje."""
    if not isinstance(marco, dict) or marco.get("intencion") not in INTENCIONES:
        return None
    ranuras = []
    if marco["intencion"] not in ("afirmar", "negar", "fuera_de_alcance"):
        for r in marco.get("ranuras") or []:
            if isinstance(r, dict) and r.get("tipo") in RANURAS and isinstance(r.get("valor"), str):
                donde = texto.lower().find(r["valor"].lower().strip())
                if r["valor"].strip() and donde >= 0:
                    ranuras.append({"tipo": r["tipo"], "valor": texto[donde:donde + len(r["valor"].strip())]})
    return {"intencion": marco["intencion"], "confianza": 1.0, "ranuras": ranuras}


def interpretar(texto, contexto="", herramientas=None):
    """El marco del mensaje según el LLM, o None si no hay clave, no responde o lo que devuelve no sirve.

    Con herramientas (los servidores MCP de herramientas.py), el LLM puede consultar el catálogo, los turnos y el
    calendario antes de contestar, y el marco puede traer una «respuesta» para el cliente.
    """
    if not config.leer_env("GROQ_API_KEY", obligatoria=False):
        return None
    usuario = (f"Contexto: {contexto}\n" if contexto else "") + f"Mensaje: {texto}"
    try:
        if herramientas is not None and herramientas.disponibles:
            return con_herramientas(texto, usuario, herramientas)
        marco, _ = chat(ESQUEMA + UNO, usuario, espera=6)
    except SinRespuesta:
        return None
    return validar(marco, texto)


# Con herramientas MCP: lo que se añade al esquema
HERRAMIENTAS = """

Tienes herramientas de solo lectura, conectadas por MCP: «barberia» (servicios y precios, barberos, horario y turnos \
libres) y «calendario» (la fecha de hoy y la lectura de fechas y horas). Úsalas cuando te ayuden a leer el mensaje \
(por ejemplo, para saber si un nombre es el de un barbero o qué servicio existe) o a contestar una pregunta sobre la \
barbería. No calcules fechas tú: pregúntale al calendario. Nunca inventes precios, barberos, horarios ni turnos: lo \
que digas de eso tiene que salir de una herramienta.

Cuando termines, entrega el resultado llamando a la función «responder» con la intención, las ranuras y la respuesta.
«respuesta» es un mensaje corto para el cliente (máximo tres frases, en tuteo y con el tono amable de un barbero \
colombiano, sin markdown, con precios como «$38.000» y horas como «3:00 p. m.») solo cuando el mensaje es una pregunta sobre la barbería (precios, servicios, barberos, \
horario o turnos libres) y la contestaste con las herramientas. En cualquier otro caso es null. Nunca digas que \
agendaste, cambiaste o cancelaste una cita: tú no puedes hacerlo; si el cliente quiere eso, la respuesta es null."""
RONDAS = 4                    # máximo de veces que el LLM pide herramientas antes de contestar
# No es una herramienta MCP: es como el LLM entrega su resultado (gpt-oss tiende a «llamar» al JSON final como si fuera
# una herramienta, y Groq rechaza la llamada si esa herramienta no existe)
RESPONDER = {"type": "function", "function": {
    "name": "responder", "description": "Entrega el resultado final: la intención, las ranuras y la respuesta o null.",
    "parameters": {"type": "object", "required": ["intencion", "ranuras"], "properties": {
        "intencion": {"type": "string", "enum": INTENCIONES},
        "ranuras": {"type": "array", "items": {"type": "object", "required": ["tipo", "valor"], "properties": {
            "tipo": {"type": "string", "enum": RANURAS}, "valor": {"type": "string"}}}},
        "respuesta": {"type": ["string", "null"]}}}}}
PROMETE = re.compile(r"\b(te )?(agend[eé]|reserv[eé]|cancel[eé]|cambi[eé]|qued[oó] (agendad|reservad|lista))", re.I)


PRECIO_DICHO = re.compile(r"\$\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,6})|\b(\d{1,3}(?:[.,]\d{3})+|\d{4,6})\s*pesos|\b(\d{1,3})\s*mil\b", re.I)
PRECIO_DATO = re.compile(r'"precio":\s*(\d+)')


def precios_respaldados(respuesta, resultados):
    """Cada precio que el LLM le dice al cliente tiene que salir de una herramienta: un precio del catálogo o la suma
    de hasta tres («$50.000» por dos cortes de $25.000). Un precio inventado descarta la respuesta."""
    precios = {int(p) for texto in resultados for p in PRECIO_DATO.findall(texto)}
    validos = {a + b + c for a in precios | {0} for b in precios | {0} for c in precios | {0}} - {0}
    for m in PRECIO_DICHO.finditer(respuesta):
        cifra, en_pesos, en_miles = m.groups()
        valor = int(en_miles) * 1000 if en_miles else int(re.sub(r"[.,]", "", cifra or en_pesos))
        if valor not in validos:
            return False
    return True


def _entrega_rechazada(error):
    """gpt-oss a veces entrega el resultado «llamando» a una herramienta que no existe («json», «response») y Groq
    rechaza la llamada con tool_use_failed; el rechazo trae lo que generó, y si es el resultado se aprovecha."""
    try:
        generado = json.loads(json.loads(error.cuerpo)["error"]["failed_generation"])
        argumentos = generado.get("arguments", generado)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return argumentos if isinstance(argumentos, dict) and "intencion" in argumentos else None


def con_herramientas(texto, usuario, herramientas, espera=8, reintentos=1, tope_429=8):
    """El LLM lee el mensaje con las herramientas MCP a mano. Devuelve el marco validado, con las herramientas que
    usó y, si aplica, la respuesta para el cliente."""
    mensajes = [{"role": "system", "content": ESQUEMA + HERRAMIENTAS}, {"role": "user", "content": usuario}]
    usadas, crudo = [], None
    for ronda in range(RONDAS + 1):
        # el plan gratuito de Groq da 8 000 tokens por minuto y cuenta el máximo pedido: se pide poco
        cuerpo = {"model": MODELO, "temperature": 0, "reasoning_effort": "low", "max_completion_tokens": 700,
                  "messages": mensajes}
        if ronda < RONDAS:
            cuerpo["tools"] = herramientas.lista + [RESPONDER]
        else:
            cuerpo["response_format"] = {"type": "json_object"}      # última vuelta: tiene que contestar
        try:
            mensaje = _pedir(cuerpo, espera, reintentos, tope_429)["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise SinRespuesta("respuesta vacía") from None
        except SinRespuesta as error:
            crudo = _entrega_rechazada(error)
            if crudo is None:
                raise
            break
        llamadas = mensaje.get("tool_calls") or []
        if not llamadas:
            break
        mensajes.append({"role": "assistant", "content": mensaje.get("content") or "", "tool_calls": llamadas})
        for llamada in llamadas:
            nombre = llamada["function"]["name"]
            try:
                argumentos = json.loads(llamada["function"].get("arguments") or "{}")
            except ValueError:
                argumentos = {}
            argumentos = argumentos if isinstance(argumentos, dict) else {}
            if nombre.lower() in ("responder", "json"):
                crudo = argumentos
                break
            usadas.append(nombre)
            mensajes.append({"role": "tool", "tool_call_id": llamada["id"], "content": herramientas.llamar(nombre, argumentos)})
        if crudo is not None:
            break
    if crudo is None:
        contenido = (mensaje.get("content") or "").strip()
        if contenido.startswith("```"):
            contenido = contenido.strip("`").removeprefix("json").strip()
        try:
            crudo = json.loads(contenido)
        except ValueError:
            return None
    marco = validar(crudo, texto)
    if marco is None:
        return None
    marco["herramientas"] = usadas
    respuesta = crudo.get("respuesta")
    resultados = [m["content"] for m in mensajes if m["role"] == "tool"]
    if isinstance(respuesta, str) and respuesta.strip() and usadas and not PROMETE.search(respuesta) \
            and precios_respaldados(respuesta, resultados) \
            and marco["intencion"] in ("consultar_disponibilidad", "consultar_servicios", "fuera_de_alcance"):
        marco["respuesta"] = respuesta.strip()[:700]
    return marco
