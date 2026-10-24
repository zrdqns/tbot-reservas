"""LLM de respaldo: interpreta los mensajes que el clasificador no entiende.

Recibe el mensaje y el punto de la conversación, y devuelve el mismo marco que el clasificador: una
intención y unas ranuras copiadas del mensaje. No conversa con el cliente ni tiene acceso a la agenda:
lo que devuelve pasa por el normalizador de fechas, por el catálogo y por la confirmación, igual que
lo que dice el clasificador. Si el servicio no responde devuelve None y el agente sigue con sus menús.

Usa un modelo abierto servido por Groq. La clave va en .env como GROQ_API_KEY.
"""
import json
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
    pass


def chat(sistema, usuario, esfuerzo="low", espera=20, reintentos=0, maximo=1500):
    """Una pregunta al modelo. Devuelve el JSON de la respuesta y los tokens que gastó."""
    cuerpo = {"model": MODELO, "temperature": 0, "reasoning_effort": esfuerzo, "max_completion_tokens": maximo,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    pedido = urllib.request.Request(URL, data=json.dumps(cuerpo).encode("utf-8"), headers={
        "Authorization": "Bearer " + config.leer_env("GROQ_API_KEY"), "Content-Type": "application/json",
        "User-Agent": "tbot/1.0"})
    for intento in range(reintentos + 1):
        try:
            with urllib.request.urlopen(pedido, timeout=espera) as respuesta:
                datos = json.load(respuesta)
            return json.loads(datos["choices"][0]["message"]["content"]), datos["usage"]["total_tokens"]
        except urllib.error.HTTPError as error:
            if error.code == 429 and intento < reintentos:        # límite por minuto: se espera lo que pide el servicio
                time.sleep(float(error.headers.get("retry-after", 20)) + 1)
                continue
            raise SinRespuesta(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
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


def interpretar(texto, contexto=""):
    """El marco del mensaje según el LLM, o None si no hay clave, no responde o lo que devuelve no sirve."""
    if not config.leer_env("GROQ_API_KEY", obligatoria=False):
        return None
    try:
        marco, _ = chat(ESQUEMA + UNO, (f"Contexto: {contexto}\n" if contexto else "") + f"Mensaje: {texto}", espera=6)
    except SinRespuesta:
        return None
    return validar(marco, texto)
