"""Arranca el agente en Telegram.

    py -m bot

Necesita los dos microservicios de la barbería encendidos (puertos 8080 y 8081) y el token en .env.
Esta parte solo traduce: lo que llega de Telegram pasa al agente y sus respuestas vuelven como mensajes.

En Vercel corre igual, como daemon (ver Dockerfile y vercel.json); allá las direcciones, el token y
DATABASE_URL llegan por variables de entorno, y los perfiles y mensajes se guardan en la base de datos.
"""
import asyncio
import logging
import os
import threading
from datetime import datetime

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
                      ReplyKeyboardRemove)
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from . import config
from .agente import Agente
from .barberia import Barberia
from .comprension import entender
from .perfiles import Perfiles
from .respaldo import interpretar

if os.environ.get("DATABASE_URL"):
    from .almacen import PerfilesBD, RegistroBD
    perfiles, registro = PerfilesBD(os.environ["DATABASE_URL"]), RegistroBD(os.environ["DATABASE_URL"])
else:
    perfiles, registro = Perfiles(config.DATOS / "perfiles.json"), config.DATOS / "mensajes.jsonl"
agente = Agente(Barberia(), entender, perfiles, registro, respaldo=interpretar)
PRIVADO = filters.ChatType.PRIVATE
TURNO = threading.Lock()


def ahora(momento=None):
    """La hora de Colombia del mensaje: es la referencia para «mañana» o «el sábado»."""
    return (momento or datetime.now(config.ZONA)).astimezone(config.ZONA).replace(tzinfo=None)


async def mandar(bot, chat, texto, teclado):
    """Envía un mensaje. Si la conexión con Telegram falla un instante, lo intenta otra vez; si el envío pudo
    haber llegado (se agotó el tiempo de espera), no lo repite, para no mandarlo dos veces."""
    for intento in range(3):
        try:
            return await bot.send_message(chat, texto, reply_markup=teclado)
        except TimedOut:
            raise
        except NetworkError:
            if intento == 2:
                raise
            await asyncio.sleep(1 + intento)


async def enviar(bot, chat, respuestas, quitar_teclado=False):
    for r in respuestas:
        teclado = ReplyKeyboardRemove() if quitar_teclado else None
        if r.botones:
            teclado = InlineKeyboardMarkup([[InlineKeyboardButton(texto, callback_data=dato) for texto, dato in fila]
                                            for fila in r.botones])
        elif r.pedir_contacto:
            teclado = ReplyKeyboardMarkup([[KeyboardButton("📱 Compartir mi número", request_contact=True)]],
                                          resize_keyboard=True, one_time_keyboard=True, is_persistent=True)
        await mandar(bot, chat, r.texto, teclado)
        quitar_teclado = False


async def escribiendo(bot, chat):
    """«Escribiendo…» mientras el agente trabaja. Telegram lo quita a los cinco segundos, así que se repite; es solo
    un aviso: si Telegram no lo recibe, el mensaje se atiende igual."""
    while True:
        try:
            await bot.send_chat_action(chat, "typing")
        except TelegramError:
            pass
        await asyncio.sleep(4)


def en_turno(paso, *datos):
    """El agente hace una cosa a la vez: un mensaje, un recordatorio o la lectura del horario no se cruzan."""
    with TURNO:
        return paso(*datos)


async def pensar(bot, chat, paso, *datos):
    """Corre el agente aparte, con «escribiendo…» encendido: si un microservicio tarda en despertar, el cliente lo ve."""
    aviso = asyncio.create_task(escribiendo(bot, chat))
    try:
        return await asyncio.to_thread(en_turno, paso, *datos)
    finally:
        aviso.cancel()


async def al_texto(update, context):
    usuario, mensaje = update.effective_user, update.message
    respuestas = await pensar(context.bot, mensaje.chat_id, agente.texto, usuario.id, usuario.full_name, mensaje.text,
                              ahora(mensaje.date))
    await enviar(context.bot, mensaje.chat_id, respuestas)


async def al_comando(update, context):
    usuario, mensaje = update.effective_user, update.message
    comando = mensaje.text.split()[0][1:].split("@")[0].lower()
    respuestas = await pensar(context.bot, mensaje.chat_id, agente.comando, usuario.id, usuario.full_name, comando,
                              ahora(mensaje.date))
    await enviar(context.bot, mensaje.chat_id, respuestas)


async def al_boton(update, context):
    toque = update.callback_query
    try:
        await toque.answer()
    except TelegramError:                       # un botón viejo o un corte de conexión: el toque se atiende igual
        pass
    # los botones sirven una sola vez: se quitan y en su lugar queda lo que el cliente escogió, como en un chat
    marcado = toque.message.reply_markup
    escogido = next((b.text for fila in (marcado.inline_keyboard if marcado else []) for b in fila
                     if b.callback_data == toque.data), None)
    try:
        if escogido and toque.message.text:
            await toque.edit_message_text(f"{toque.message.text}\n\n👉 {escogido}")
        else:
            await toque.edit_message_reply_markup(None)
    except TelegramError:
        pass
    respuestas = await pensar(context.bot, toque.message.chat_id, agente.boton, toque.from_user.id,
                              toque.from_user.full_name, toque.data, ahora())
    await enviar(context.bot, toque.message.chat_id, respuestas)


async def al_contacto(update, context):
    usuario, mensaje = update.effective_user, update.message
    if mensaje.contact.user_id != usuario.id:            # Telegram garantiza que ese número es de quien lo comparte
        await mensaje.reply_text("Necesito tu propio número. Toca el botón «Compartir mi número».")
        return
    respuestas = await pensar(context.bot, mensaje.chat_id, agente.contacto, usuario.id, usuario.full_name,
                              mensaje.contact.phone_number, ahora(mensaje.date))
    await enviar(context.bot, mensaje.chat_id, respuestas, quitar_teclado=True)


async def a_lo_demas(update, context):
    await update.message.reply_text("Solo entiendo mensajes de texto. Escríbeme lo que necesitas.")


async def recordar(context):
    for chat, respuesta in await asyncio.to_thread(en_turno, agente.recordatorios, ahora()):
        await enviar(context.bot, chat, [respuesta])


async def leer_horario(context):
    """El horario de atención lo guarda api-citas; se lee al arrancar y cada media hora por si cambió."""
    if not await asyncio.to_thread(en_turno, agente.api.leer_horario):
        logging.warning("api-citas no respondió: sigo con el horario de config.py")


async def al_error(update, context):
    logging.error("Error atendiendo un mensaje", exc_info=context.error)
    if update and update.effective_chat:
        try:
            await mandar(context.bot, update.effective_chat.id, "Uy, se me fue la señal un momento 😅 ¿Me lo repites?", None)
        except TelegramError:
            pass                                # si Telegram tampoco responde, no hay a quién avisarle


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)     # sus mensajes incluyen la dirección con el token
    app = Application.builder().token(config.leer_env("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(PRIVADO & filters.COMMAND, al_comando))
    app.add_handler(MessageHandler(PRIVADO & filters.TEXT, al_texto))
    app.add_handler(MessageHandler(PRIVADO & filters.CONTACT, al_contacto))
    app.add_handler(MessageHandler(PRIVADO, a_lo_demas))     # fotos, stickers y cualquier otra cosa
    app.add_handler(CallbackQueryHandler(al_boton))
    app.add_error_handler(al_error)
    app.job_queue.run_repeating(leer_horario, interval=1800, first=0)
    app.job_queue.run_repeating(recordar, interval=1800, first=20)
    logging.info("TBot atendiendo. Ctrl+C para detenerlo.")
    app.run_polling()


if __name__ == "__main__":
    main()
