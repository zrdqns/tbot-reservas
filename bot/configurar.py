"""Deja en Telegram la descripción y el menú de comandos del bot.

    py -m bot.configurar

Lee el token de .env. Se puede ejecutar las veces que haga falta: reemplaza lo que haya.
"""
import json
import urllib.request

from . import config

# Lo que se ve antes de pulsar Iniciar. Dice que es un programa y qué guarda (Ley 1581 de 2012).
DESCRIPCION = (
    "¡Qué más! 💈 Soy TBot, el asistente de la barbería. Soy un programa, no una persona.\n\n"
    "Escríbeme como le escribirías a tu barbero: «parce, ¿me agenda un desvanecido con Andrés mañana tipo 3?». "
    "Te agendo, te cambio o te cancelo la cita y te digo horarios y precios. "
    "No agendo nada sin que me lo confirmes.\n\n"
    "Guardo tu nombre, tu cuenta de Telegram, tus citas y los mensajes sin tu nombre. La primera vez la "
    "barbería te pide celular y documento. Puedes borrar tus datos con /borrar."
)
# Lo que se ve en el perfil del bot y al compartirlo
RESUMEN = "El asistente de la barbería: agenda, cambia o cancela tu cita. Escríbele como a tu barbero 💈"
COMANDOS = [
    ("start", "Empezar y ver qué puedo hacer"),
    ("miscitas", "Ver tus citas"),
    ("ayuda", "Cómo escribirme"),
    ("borrar", "Borrar tus datos"),
]


def llamar(token, metodo, **datos):
    pedido = urllib.request.Request(f"https://api.telegram.org/bot{token}/{metodo}",
                                    data=json.dumps(datos).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=20) as respuesta:
        return json.load(respuesta)["result"]


if __name__ == "__main__":
    token = config.leer_env("TELEGRAM_TOKEN")
    yo = llamar(token, "getMe")
    print(f"Bot: {yo['first_name']} (@{yo['username']})")
    llamar(token, "setMyDescription", description=DESCRIPCION)
    llamar(token, "setMyShortDescription", short_description=RESUMEN)
    llamar(token, "setMyCommands", commands=[{"command": c, "description": d} for c, d in COMANDOS])
    print("Descripción:", len(llamar(token, "getMyDescription")["description"]), "caracteres")
    print("Resumen:", llamar(token, "getMyShortDescription")["short_description"])
    print("Comandos:", ", ".join("/" + c["command"] for c in llamar(token, "getMyCommands")))
