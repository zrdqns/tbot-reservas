# Imagen del bot para Vercel Daemons: un proceso que corre siempre y le pregunta a Telegram por mensajes nuevos.
# Lleva solo el agente, el clasificador exportado y el tokenizador del corpus.
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY bot/requisitos.txt .
RUN pip install --no-cache-dir -r requisitos.txt
COPY corpus/esquema.py corpus/esquema.py
COPY modelo/entender.py modelo/entender.py
# El modelo va comprimido: Vercel no sube archivos de más de 100 MB y el .onnx pesa 105 MB
COPY modelo/modelo_tbot.zip /tmp/modelo_tbot.zip
RUN python -m zipfile -e /tmp/modelo_tbot.zip modelo/modelo_tbot && rm /tmp/modelo_tbot.zip
COPY bot bot
CMD ["python", "-m", "bot"]
