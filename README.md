# TBot Reservas

Proyecto de Sistemas Inteligentes · Universidad de Ibagué

Un bot de Telegram que agenda, cambia y cancela citas de barbería con mensajes escritos como los escribe
la gente, sobre el sistema de gestión de [barberia-microservicios](https://github.com/zrdqns/barberia-microservicios).
Está en Telegram como [@tbot_reservas_barberia_bot](https://t.me/tbot_reservas_barberia_bot).

| Carpeta | Qué hay |
|---|---|
| [`bot/`](bot/README.md) | El agente: comprensión, estado de la conversación, política y conexión con Telegram |
| [`corpus/`](corpus/README.md) | Los 2 600 mensajes anotados con intención y ranuras, y el generador que los arma |
| `modelo/` | El cuaderno con que entrené el clasificador en Colab y el modelo exportado a ONNX |
| [`evaluacion/`](evaluacion/README.md) | Medición del clasificador, del normalizador de fechas y simulación de conversaciones |

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

El bot corre en Vercel como daemon y usa los microservicios desplegados y la base de datos de Supabase (ver
[bot/README.md](bot/README.md#en-vercel)). Cada push a `main` que cambie el bot o el modelo se publica solo.
Mientras esté desplegado no hay que encenderlo en el computador: Telegram entrega los mensajes a un solo
proceso a la vez.
