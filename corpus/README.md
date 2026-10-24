# Corpus de mensajes de reserva en español colombiano

Proyecto SI-TBot Reservas · Sistemas Inteligentes · Universidad de Ibagué

Son 2 600 mensajes como los que un cliente le escribe a una barbería por chat, cada uno con su intención y
sus ranuras. Con ellos se ajusta y se prueba el clasificador conjunto del agente (Sección IV del informe).

| | Mensajes | Origen |
|---|---|---|
| Entrenamiento (`datos/train.jsonl`) | 1 901 | 485 redactados y 1 416 generados |
| Validación (`datos/val.jsonl`) | 329 | 83 redactados y 246 generados |
| Prueba (`datos/test.jsonl`) | 370 | 354 redactados y 16 mensajes reales |

El detalle por intención y por ranura está en [datos/resumen.md](datos/resumen.md), que se escribe cada vez
que se arma el corpus. Las reglas de etiquetado están en [guia_anotacion.md](guia_anotacion.md).

## Versiones

- **Primera versión (2 000 mensajes).** Con ella se entrenó el primer modelo del agente.
- **Segunda versión (2 600 mensajes).** Al probar el bot en Telegram aparecieron mensajes que no entendía:
  «oe bro estoy muy mechudo dame una cita para el 16 en la madrugada, quiero solo las puntas y el 7 con
  desvanecido» terminó agendado para el 7 de noviembre, «no bro, la cita es para el 16» se leyó como una
  consulta de citas y «cualquiera» como un mensaje fuera de alcance. Agregué al generador el registro
  colombiano («oe», «quiubo», «mi llave», «sisas», «le caigo», «me motila»), la descripción del corte con
  el número de la guarda, las correcciones mientras se agenda, las respuestas sin preferencia de barbero,
  la pregunta por los barberos, la madrugada y los días del mes con letras. También escribí 124 mensajes
  nuevos para entrenamiento y 54 para la prueba, y pasé a la prueba los 16 mensajes reales de esas
  conversaciones.

La prueba queda en tres bloques, que se reportan por separado: los 300 mensajes de la primera versión, los
16 reales y los 54 nuevos.

## Cómo lo construí

1. **Esquema.** Nueve intenciones (reservar, reprogramar, cancelar, consultar disponibilidad, consultar
   servicios y precios, consultar mis citas, afirmar, negar y fuera de alcance) y seis ranuras (servicio,
   barbero, fecha, hora, franja del día y nombre), en formato BIO.
2. **Situaciones.** Partí de lo que se puede hacer con la API de la barbería y de los diálogos del dominio
   Services de SGD: pedir una cita con o sin barbero, preguntar por cupos, cambiarla, cancelarla y
   contestar las preguntas del agente. El catálogo es el real: corte clásico, arreglo de barba, corte y
   barba, y tinte, con Andrés, Julián y Felipe. Añadí servicios que la barbería no ofrece y otros nombres
   para que el modelo no se aprenda la lista de memoria.
3. **Mensajes redactados.** 924 mensajes escritos uno a uno con un LLM, ya anotados
   (`redactados/prueba.txt` y `redactados/entrenamiento.txt`). Los de prueba se escribieron primero y aparte.
4. **Generador.** `generador.py` rellena 479 marcos («¿me puedes agendar {servicio} {cuándo}?») con
   distintas maneras de decir cada ranura y después reescribe el mensaje con un estilo: cuidado, normal o a
   la carrera, que quita tildes y signos, abrevia («q», «pa», «xfa») y mete errores de tecleo. Como el
   estilo se aplica por separado dentro y fuera de cada ranura, las etiquetas no se dañan.
5. **Partición.** La prueba no tiene ningún mensaje salido del generador. Los marcos de validación no se
   usan en entrenamiento. Ningún mensaje se repite entre las tres partes, ni siquiera cambiando
   mayúsculas, tildes o signos.
6. **Revisión.** `esquema.revisar` comprueba cada registro: intención y ranuras válidas, tramos que
   coinciden con las palabras, artículos y preposiciones donde la guía los pone, y ninguna ranura en
   afirmar, negar o fuera de alcance. Aparte busqué fechas, horas, servicios y nombres sin etiquetar, y
   leí uno por uno los mensajes de reservar, reprogramar y cancelar que podían confundirse entre sí, que
   es donde Sahu *et al.* encontraron que los datos generados fallan más.

## Formato

Una línea JSON por mensaje:

```json
{"id": "test-0006", "texto": "corte mañana 3pm", "intencion": "reservar",
 "ranuras": [{"tipo": "servicio", "valor": "corte", "inicio": 0, "fin": 5}, ...],
 "tokens": ["corte", "mañana", "3pm"], "etiquetas": ["B-servicio", "B-fecha", "B-hora"],
 "origen": "redactado", "plantilla": null, "grupo": "base"}
```

`inicio` y `fin` son posiciones en `texto`. `tokens` sale de `esquema.tokenizar`, que es el mismo
tokenizador que usa el agente. `plantilla` identifica el marco de los mensajes generados y `grupo` el
bloque de la prueba (`base`, `reales` o `colombiano`).

## Cómo regenerarlo

```
py construir.py
```

Solo necesita Python 3. Con la misma semilla produce los mismos archivos. Para añadir mensajes basta
escribirlos en `redactados/` con el formato de la guía; el script avisa de la línea que no la cumpla.

## Límites

- **Casi ningún mensaje viene de un cliente real.** Los redactados salieron de un LLM y los generados de
  marcos que escribí yo. Los únicos reales son los 16 de la prueba, escritos al bot por mí y por un
  profesor durante las pruebas en Telegram, sin datos personales. El corpus cubre las maneras de pedir una
  cita que se me ocurrieron y las que fallaron en esas pruebas, no todas las que usa la gente.
- **La prueba y el entrenamiento comparten autor.** Aunque la prueba no pasa por el generador, la mayor
  parte la escribió el mismo LLM que redactó parte del entrenamiento, así que las cifras sobre
  `test.jsonl` son optimistas. El bloque de mensajes reales es pequeño; medir con más mensajes escritos
  por personas sigue pendiente.
- **Un solo negocio.** Los servicios, los horarios y la forma de hablar son los de una barbería.
- **Poco de cada cosa.** `nombre` aparece 66 veces, las descripciones del corte 221 y las que llevan el
  número de la guarda, 113.

## Licencia

CC BY 4.0. Los nombres de personas son inventados.
