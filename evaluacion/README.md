# Evaluación del agente

Proyecto SI-TBot Reservas · Sistemas Inteligentes · Universidad de Ibagué

Aquí están los conjuntos y los programas con que mido cada componente, según el plan de la Tabla IV del
informe. El entrenamiento del clasificador y la comparación entre modelos están en
`modelo/entrenar_clasificador.ipynb`.

| Qué se mide | Con qué | Cómo se ejecuta |
|---|---|---|
| Fechas y horas | `expresiones_tiempo.csv`: 200 expresiones con su valor correcto | `python -m evaluacion.evaluar_fechas` |
| Clasificador en el equipo del agente | Los 370 mensajes de prueba del corpus | `python modelo/entender.py --prueba` |
| Tarea completa, acción y latencia | `guiones.py`: 70 guiones, cinco repeticiones | `python -m evaluacion.simular` |
| Clasificador frente a un LLM sin ejemplos | Los 370 mensajes de prueba | `python -m evaluacion.comparar_llm clasificador` |
| Normalizador frente a un LLM sin reglas | Las mismas 200 expresiones | `python -m evaluacion.comparar_llm fechas` |
| Comprensión con mensajes de personas | `mensajes_reales.txt`: 92 mensajes escritos al bot en Telegram | `python -m evaluacion.evaluar_reales` |
| El LLM con los dos servidores MCP | 20 preguntas abiertas con respuesta conocida | `python -m evaluacion.preguntas_mcp` |

Hay dos versiones. La primera es la que se armó con el corpus de 2 000 mensajes. La segunda salió de
probar el bot en Telegram: el corpus pasó a 2 600 mensajes, la prueba incluye 16 mensajes reales de esas
pruebas y 54 nuevos con registro colombiano, y se añadieron 10 guiones con lo que falló. Reporto las cifras
de cada versión tal como salieron la primera vez que las medí; cuando después corregí algo, lo digo aparte.

## Fechas y horas

Son 100 fechas, 65 horas y 35 franjas, con cuatro fechas de referencia que incluyen un fin de mes y un fin
de año. Escribí los valores a mano, sin usar el normalizador. Una expresión cuenta como acierto solo si el
valor es exactamente el esperado.

| Tipo | Expresiones | Aciertos | Exactitud |
|---|---|---|---|
| Fecha | 100 | 91 | 91,0 % |
| Hora | 65 | 62 | 95,4 % |
| Franja | 35 | 33 | 94,3 % |
| **Total** | 200 | 186 | 93,0 % |

Esta es la primera pasada, con las reglas que tenía antes de armar el conjunto. Las 14 fallas eran
modismos sin regla: «en ocho días», «de hoy en ocho», «el sábado en ocho», «en quince días», «dentro de
tres días», «un cuarto para las 4», «en hora y media», «pasado el mediodía» y «de 2 a 4». Después añadí
esas reglas y el programa acierta las 200. Ese 100 % solo comprueba que las reglas nuevas quedaron bien:
para volver a medir hacen falta expresiones que el normalizador no haya visto.

En la segunda versión añadí la madrugada, la hora del almuerzo y los días del mes escritos con letras («el
dieciséis», «el día 16»). Las 200 siguen en 200; esas reglas nuevas no están en el conjunto y se prueban en
`bot/tests/test_fechas.py`.

## Clasificador

El modelo es la versión de 8 bits que usa el agente, medida en este equipo. La medida es el mensaje
completo: la intención y todas las ranuras correctas.

| Modelo | Toda la prueba (370) | Primera versión (300) | Mensajes reales (16) | Registro colombiano (54) |
|---|---|---|---|---|
| Primera versión | 84,1 % | 91,3 % | 68,8 % | 48,1 % |
| Segunda versión | 89,5 % | 90,0 % | 93,8 % | 85,2 % |

- En toda la prueba, el modelo de la segunda versión acierta la intención en el 94,9 % de los mensajes y
  las ranuras con un F1 de 96,3 %, en 7 ms por mensaje.
- Los mensajes que fallaron en Telegram ahora se entienden: «oe bro estoy muy mechudo dame una cita para
  el 16 en la madrugada, quiero solo las puntas y el 7 con desvanecido» sale con la fecha 16, la madrugada
  como franja y las dos descripciones como servicio; «no bro la cita es para el 16» sale como reservar y
  «cualquiera» como barbero.
- En los 300 mensajes de la primera versión el modelo nuevo baja 1,3 puntos, cuatro mensajes. En el
  cuaderno, el promedio de tres semillas en ese bloque es el mismo en las dos versiones (89,4 %), así que
  la diferencia está en la semilla que quedó guardada.
- El único mensaje real que todavía falla es «puedes cambiar la cita para el marte 13 de octubre»: con la
  errata, el modelo toma «marte» como servicio. La política lo corrige: un servicio que es un día de la
  semana mal escrito se une a la fecha que sigue.

## Tarea completa

Sigo el método de τ-bench. Cada guion fija lo que el cliente quiere, cómo está la agenda antes de empezar
y cómo debe quedar al final. Un cliente simulado conversa con el agente: contesta lo que le preguntan,
corrige si cambia de opinión, escoge entre las horas que le ofrecen y confirma solo si el resumen dice lo
que pidió. La conversación es un éxito si la agenda final es exactamente la esperada. Las cinco
repeticiones cambian la manera de pedirlo, de contestar (con texto o con botón) y de confirmar.

### Primera versión: 60 guiones

| Tipo de guion | Guiones | Conversaciones | Éxito | Guiones con 5 de 5 | Mensajes del cliente |
|---|---|---|---|---|---|
| Reserva completa | 14 | 70 | 100 % | 14 | 2,3 |
| Reserva incompleta | 10 | 50 | 96 % | 8 | 4,4 |
| Cambio de opinión | 8 | 40 | 100 % | 8 | 3,2 |
| Turno ocupado | 8 | 40 | 100 % | 8 | 2,8 |
| Reprogramación | 8 | 40 | 100 % | 8 | 2,2 |
| Cancelación | 6 | 30 | 100 % | 6 | 2,0 |
| Consulta | 3 | 15 | 100 % | 3 | 1,0 |
| Fuera de alcance | 3 | 15 | 100 % | 3 | 1,0 |
| **Total** | 60 | 300 | 99,3 % | 58 | 2,7 |

Las dos conversaciones que fallaron en esta primera pasada empezaban con «buenas, es para una cita» y
«necesito un corte de pelo». El clasificador las tomó por fuera de alcance, el agente mostró el menú y el
cliente simulado no supo seguir. Lo atendí en la política: cuando el clasificador duda pero marcó un
servicio o una fecha, el agente pregunta si quiere agendar una cita con botones en vez de mostrar el menú
general. Con ese cambio las 300 conversaciones terminaron bien.

### Segunda versión: 70 guiones

Los 10 guiones nuevos (grupo H, «registro colombiano») repiten lo que falló en Telegram: el mensaje del
«7 con desvanecido» en la madrugada, la corrección «no bro, la cita es para el 16» al ver el resumen, el
botón «Cambiar algo» seguido de la corrección escrita, «cualquiera» como respuesta a «¿con quién?», la
pregunta «¿qué barberos hay?», dos fechas en un mismo mensaje, pedir cambiar una cita que no existe, la
madrugada con un barbero y una conversación entera en registro colombiano.

La primera vez que los corrí, con el primer entrenamiento de la segunda versión, pasaron 46 de las 50
conversaciones (92 %). Las cuatro que fallaron empezaban con «me motila mañana a las 3» o «estoy muy
mechudo, dame un turno»: el agente preguntaba qué servicio quería y el cliente simulado no sabía contestar,
porque para él ya lo había dicho. Agregué a la política que, si el mensaje nombra el servicio o lo da por
hecho y el clasificador no marcó la ranura, el agente lo entiende igual, como lo entendería un barbero.

Al revisar esas fallas encontré que en el corpus nuevo había dejado «me motila» y «me puede peluquear» sin
anotar en unos mensajes y anotados en otros. Corregí la anotación y volví a entrenar. Ese modelo final no
marca el servicio cuando el cliente contesta solo «un corte», y antes de ampliar la regla anterior a ese
caso fallaban 11 de las 350 conversaciones. Con la regla ampliada:

| Tipo de guion | Guiones | Conversaciones | Éxito | Guiones con 5 de 5 | Mensajes del cliente |
|---|---|---|---|---|---|
| Reserva completa | 14 | 70 | 100 % | 14 | 2,3 |
| Reserva incompleta | 10 | 50 | 100 % | 10 | 4,6 |
| Cambio de opinión | 8 | 40 | 100 % | 8 | 3,3 |
| Turno ocupado | 8 | 40 | 100 % | 8 | 2,8 |
| Reprogramación | 8 | 40 | 100 % | 8 | 2,2 |
| Cancelación | 6 | 30 | 100 % | 6 | 2,0 |
| Consulta | 3 | 15 | 100 % | 3 | 1,0 |
| Fuera de alcance | 3 | 15 | 100 % | 3 | 1,0 |
| Registro colombiano | 10 | 50 | 100 % | 10 | 3,6 |
| **Total** | 70 | 350 | 100 % | 70 | 2,8 |

- **Acción.** Ninguna cita creada, movida o cancelada por error en las 350 conversaciones, tampoco en las
  corridas que fallaron.
- **Latencia.** El agente tarda unos 5 ms por mensaje en promedio y menos de 20 ms en el peor caso, sin
  contar la red. El requisito es 3 s.

Ese 100 % no es una medida nueva: los guiones del grupo H se escribieron a partir de las mismas
conversaciones que motivaron los cambios.

## Qué tan lejos llegan estas cifras

- **El cliente simulado coopera.** Contesta lo que le preguntan y no se sale del guion. Una persona se
  distrae, escribe dos cosas a la vez o abandona.
- **Casi todas las frases son mías.** Los guiones y casi toda la prueba los escribí yo con un LLM, igual
  que el corpus. Los únicos mensajes reales son 16, escritos al bot por mí y por un profesor.
- **La agenda es una copia en memoria** de la API, con sus mismas reglas (`bot/tests/agenda_falsa.py`).
  Contra la API real probé aparte que el agente crea, mueve y cancela citas.
- La prueba con personas está en la última sección: compañeros del curso usaron el bot en Telegram y sus
  mensajes quedaron como un conjunto aparte.

## Clasificador frente a un LLM sin ejemplos

El LLM es `gpt-oss-120b`, un modelo abierto servido por Groq, el mismo que usa el agente como respaldo.
Recibe el esquema descrito con palabras, sin ningún mensaje resuelto, y devuelve la intención y las ranuras
de cada mensaje de prueba. En la segunda versión la descripción del esquema dice además cómo tratar la
descripción del corte, las correcciones y el registro colombiano, y las respuestas se volvieron a pedir para
los 370 mensajes (las de la primera versión quedaron en `salidas_llm/clasificador_v1.json`).

| Sistema | Intención | F1 de ranuras | Mensaje completo |
|---|---|---|---|
| Clasificador (BETO ajustado) | 94,9 % | 96,3 % | 89,5 % |
| LLM sin ejemplos | 93,0 % | 85,3 % | 71,6 % |
| Híbrido: clasificador y, si duda, LLM | 97,3 % | 96,0 % | 91,1 % |

Mensaje completo por bloque de la prueba:

| Sistema | Primera versión (300) | Mensajes reales (16) | Registro colombiano (54) |
|---|---|---|---|
| Clasificador | 90,0 % | 93,8 % | 85,2 % |
| LLM sin ejemplos | 73,0 % | 87,5 % | 59,3 % |
| Híbrido | 92,0 % | 93,8 % | 85,2 % |

- El LLM queda cerca en intención, pero pierde 11 puntos en ranuras y 18 en mensaje completo: entiende
  qué quiere el cliente, pero no corta los tramos como los necesita el agente.
- El híbrido es el diseño del agente. El clasificador duda en 54 de los 370 mensajes (14,6 %); esos pasan
  al LLM y la intención sube 2,4 puntos y el mensaje completo 1,6.
- Una consulta al LLM tarda 0,9 s de mediana y 1,6 s la más lenta; el clasificador, 7 ms. Las dos caben en
  el requisito de 3 s, pero solo el 15 % de los mensajes paga el segundo.
- En la primera versión, sobre los 300 mensajes y con la descripción anterior del esquema, las cifras de
  mensaje completo fueron 91,3 % para el clasificador, 78,3 % para el LLM y 92,3 % para el híbrido.

La prueba es sintética en su mayor parte y la redacté con la misma guía que le doy al LLM, así que estas
cifras comparan los tres sistemas entre sí; no dicen cómo le iría a ninguno con clientes reales.

## Normalizador frente a un LLM sin reglas

El LLM recibe la fecha de referencia, el horario de atención y los mismos criterios con que escribí los
valores esperados. La última columna cuenta como acierto un valor igual escrito de otra manera, por ejemplo
`09:00-12:00` en lugar de `*-12:00`.

| Tipo | Expresiones | Reglas, primera pasada | LLM sin reglas | LLM, contando equivalentes |
|---|---|---|---|---|
| Fecha | 100 | 91,0 % | 89,0 % | 89,0 % |
| Hora | 65 | 95,4 % | 96,9 % | 98,5 % |
| Franja | 35 | 94,3 % | 68,6 % | 85,7 % |
| **Total** | 200 | 93,0 % | 88,0 % | 91,5 % |

Los dos quedan cerca y fallan distinto. Las reglas fallaron en modismos que no tenían regla; al añadirla el
error desaparece para siempre. El LLM entiende los modismos («un cuarto para las 4» lo resuelve bien), pero
se equivoca con el calendario: para «el domingo» dio el sábado 17, para «el fin de semana» dio viernes y
sábado, y en «el miércoles de la próxima semana» se corrió un día. Son 11 fechas equivocadas de 100, y en
una reserva una fecha corrida un día es una cita equivocada. Por eso las fechas se quedan con las reglas,
como proponía el informe.

## Mensajes de personas

Entre el 10 de octubre y el 4 de noviembre, compañeros del curso, un profesor y yo le escribimos al bot en
Telegram. Cada vez que alguien me mostraba una conversación que salía mal, la reproducía con la agenda falsa, la
corregía y la dejaba como prueba en `bot/tests/test_agente.py` (de 165 pruebas a 340). El registro guarda el texto
de cada mensaje sin el nombre ni la cuenta de quien lo escribió.

`mensajes_reales.txt` tiene los 92 mensajes distintos de ese registro que no están en el corpus, anotados a mano
con la guía y leyendo cada mensaje solo, sin la conversación. Dejé fuera ocho respuestas que eran solo un número y
un mensaje copiado con la hora de Telegram.

| Sistema | Intención | F1 de ranuras | Mensaje completo |
|---|---|---|---|
| Clasificador (BETO ajustado) | 87,0 % | 88,4 % | 75,0 % |
| LLM sin ejemplos | 88,0 % | 88,3 % | 71,7 % |
| Híbrido: clasificador y, si duda, LLM | 87,0 % | 87,9 % | 73,9 % |

- Con mensajes de personas el clasificador baja de 89,5 % a 75,0 % de mensaje completo. Es la distancia entre la
  prueba sintética y el uso real que el informe anticipaba.
- El clasificador duda en solo 5 de los 92 mensajes (5,4 %), así que el LLM casi no interviene; en esos cinco
  arregla uno y daña dos. Los errores que quedan llegan con confianza alta, y el umbral no los atrapa.
- La mayoría de los errores son mensajes que dependen de la conversación: «andres» como respuesta (el modelo lo
  toma por nombre del cliente), «que no sea día lunes», «para el mismo día que tengo el corte», «cambia el lunes
  por el martes» mientras todavía arma la cita. Esos casos los resuelve la política con la pregunta que acababa de
  hacer y la cita en curso, que es donde están ahora las pruebas de regresión.
- La otra fuente de error es la frontera entre reservar y consultar: «¿a las 10 no tienes?», «¿para el domingo
  tienes?» o «¿qué días tienes para un corte que no sea el lunes?». Son preguntas que también piden una cita, y
  la guía las pone de un lado o del otro según tengan o no un verbo de agendar.

## El LLM con los dos servidores MCP

Desde noviembre de 2026 el LLM de respaldo consulta dos servidores MCP de solo lectura: «barberia» (servicios,
barberos, horario y turnos libres) y «calendario» (hoy y las reglas de fechas). `preguntas_mcp.py` le hace 20
preguntas abiertas sobre la barbería, con la agenda de prueba, dos citas puestas y el «ahora» fijo en el martes 13 de
octubre de 2026 a las 10:00 a. m., así que la respuesta correcta se conoce. En tres de ellas lo correcto es no contestar
(«¿venden cera?», «¿dónde quedan?» y una que pide agendar). El mismo LLM responde también sin herramientas, con la
instrucción de contestar las preguntas sobre la barbería.

| Tipo de pregunta | Preguntas | Con los dos MCP | Sin herramientas |
|---|---|---|---|
| Servicios y precios | 6 | 5 | 0 |
| Barberos | 3 | 2 | 0 |
| Horario y fechas | 5 | 5 | 3 |
| Turnos libres | 3 | 3 | 2 |
| No debe contestar | 3 | 3 | 3 |
| **Total** | 20 | 18 | 8 |

- Sin herramientas inventa: los barberos «Juan, Carlos y Luis», «sí, atendemos los domingos», un corte de $15.000.
- Con herramientas hace 1,1 consultas por pregunta y tarda 1,8 s de mediana. Falló una suma («un corte para mí y otro
  para mi hijo») y una pregunta por un barbero inactivo, que no contestó.
- Al repetir 12 de las preguntas (`salidas_llm/preguntas_mcp_repeticion.json`) salieron otra vez 11 de 12, pero en una
  el LLM consultó los servicios y aun así contestó «sí, hacemos tinte… $45.000». Desde entonces el agente descarta
  una respuesta con un precio que no salga del catálogo que devolvió la herramienta (o de una suma de esos precios);
  la tabla ya aplica esa verificación sobre las respuestas grabadas. La repetición se cortó porque el plan gratuito
  de Groq da 200 000 tokens al día y una pregunta con herramientas gasta unos 5 000.
- Las respuestas están en `salidas_llm/preguntas_mcp.json`; volver a correr la evaluación no gasta tokens salvo con
  `--de-nuevo`.

