# TBot Reservas

Proyecto de Sistemas Inteligentes · Universidad de Ibagué

Un bot de Telegram que agenda, cambia y cancela citas de barbería con mensajes escritos como los escribe
la gente, sobre el sistema de gestión de [barberia-microservicios](https://github.com/zrdqns/barberia-microservicios).
Está en Telegram como [@tbot_reservas_barberia_bot](https://t.me/tbot_reservas_barberia_bot).

| Carpeta | Qué hay |
|---|---|
| [`bot/`](bot/README.md) | El agente: comprensión, estado de la conversación, política, conexión con Telegram y los dos servidores MCP (barbería y calendario) que usa el LLM |
| [`corpus/`](corpus/README.md) | Los 2 600 mensajes anotados con intención y ranuras, y el generador que los arma |
| `modelo/` | El cuaderno con que entrené el clasificador en Colab y el modelo exportado a ONNX |
| [`evaluacion/`](evaluacion/README.md) | Medición del clasificador, del normalizador de fechas y simulación de conversaciones |

El corpus y los conjuntos de evaluación también están en
[Google Drive](https://drive.google.com/drive/folders/13CE5FX7xPDhZwVOx0EO4CKg-UwjZjUGE), junto con el
[video de presentación](https://drive.google.com/file/d/1PZ35j_t8C61ZvlkmDbQH_Nu6VtbnAG0n/view).

## Cómo ejecutarlo en el computador

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m bot
```

Necesita un archivo `.env` en la raíz con `TELEGRAM_TOKEN` y, para el LLM de respaldo, `GROQ_API_KEY`, y los
microservicios de la barbería encendidos. El modelo va comprimido en `modelo/modelo_tbot.zip` y se descomprime
solo la primera vez. Las pruebas corren con `.venv\Scripts\python.exe -m pytest bot/tests`.

## Despliegue

El bot se enciende a mano en el computador, junto con los dos microservicios de la barbería, y guarda los perfiles
y el registro de mensajes en la base de datos de Supabase (ver [bot/README.md](bot/README.md#despliegue)). Estuvo
como daemon en Vercel, pero el plan gratuito solo da 420 GB-hora de memoria al mes para daemons y un proceso
encendido todo el día los gasta en unos nueve días.
