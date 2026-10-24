# Agente de Telegram

Proyecto SI-TBot Reservas · Sistemas Inteligentes · Universidad de Ibagué

El agente recibe mensajes en Telegram, entiende qué quiere el cliente y agenda, cambia o cancela citas en
el sistema de la barbería ([barberia-microservicios](https://github.com/zrdqns/barberia-microservicios)),
con las mismas operaciones REST que usa su interfaz web.

## Cómo ejecutarlo

1. Encender los dos microservicios de la barbería (`api-catalogo` en el puerto 8081 y `api-citas` en el 8080).
2. Tener en `.env`, en la raíz del proyecto, el token del bot (`TELEGRAM_TOKEN=...`) y la clave del LLM de
   respaldo (`GROQ_API_KEY=...`). Sin la segunda el agente funciona igual, solo con el clasificador y los menús.
3. Desde la raíz del proyecto:

```
.venv\Scripts\python.exe -m bot
```

Otras órdenes:

| Orden | Qué hace |
|---|---|
| `python -m bot.consola` | Conversar con el agente desde la consola, sin Telegram |
| `python -m bot.configurar` | Poner en Telegram la descripción y el menú de comandos |
| `python -m pytest bot/tests` | Pruebas del normalizador de fechas y de las conversaciones |

## En Vercel

El bot también corre en Vercel como daemon, un proceso que no se apaga y le pregunta a Telegram por
mensajes nuevos (proyecto `tbot-reservas`). Habla con los microservicios desplegados
(`barberia-api-citas.vercel.app` y `barberia-api-catalogo.vercel.app`) y guarda los perfiles y los
mensajes en el esquema `bot` de la misma base de Supabase, porque el disco del contenedor se borra en
cada despliegue (`almacen.py`).

- La imagen sale del `Dockerfile` de la raíz del proyecto y `vercel.json` declara el daemon. El modelo
  viaja como `modelo/modelo_tbot.zip`, porque Vercel no sube archivos de más de 100 MB.
- `.vercelignore` deja subir solo el código del bot, el modelo y el tokenizador del corpus: nada de `.env`,
  `bot/datos`, informes ni corpus.
- Las claves van como variables de entorno del proyecto: `TELEGRAM_TOKEN`, `GROQ_API_KEY`, `DATABASE_URL`,
  `API_CITAS_URL` y `API_CATALOGO_URL`.
- Para publicar un cambio, desde la raíz del proyecto: `vercel deploy --prod`.
- El agente trabaja en un hilo aparte mientras el chat muestra «escribiendo…», que se renueva cada cuatro
  segundos: si un microservicio está despertando, el cliente ve que el bot sigue en eso. Si la conexión con
  Telegram se cae un instante, el aviso se omite y el envío se reintenta, en vez de perder el mensaje.
- Las conversaciones a medio armar viven en memoria: un despliegue nuevo las reinicia (las citas y los
  perfiles no, están en la base de datos).
- **No hay que encender el bot en el computador mientras corre en Vercel.** Telegram entrega los mensajes a
  un solo proceso a la vez; si se prenden los dos, se pelean por ellos.

## Cómo está armado

Cada archivo es uno de los bloques de la arquitectura del informe (Fig. 1).

| Archivo | Bloque | Qué hace |
|---|---|---|
| `__main__.py` | Percepción y acción | Traduce entre Telegram y el agente: mensajes, botones y contacto |
| `comprension.py` | Comprensión | Clasificador de intención y ranuras (BETO ajustado, en ONNX) |
| `fechas.py` | Comprensión | Normalizador de fechas, horas y franjas por reglas |
| `respaldo.py` | Comprensión | LLM que interpreta los mensajes que el clasificador no entiende |
| `agente.py` | Estado y política | Marco de la conversación y reglas que deciden el siguiente paso |
| `perfiles.py` | Estado | Perfil de cada cliente: nombre, cuenta y lo que más pide |
| `almacen.py` | Estado | Los mismos perfiles y el registro de mensajes, en la base de datos (en Vercel) |
| `barberia.py` | Acción | Cliente de la API, búsqueda en el catálogo y turnos libres |
| `config.py` | | Direcciones de la API, horario de respaldo y umbral de confianza |

La política sigue cuatro reglas:

- **Pregunta lo que falta, de a una cosa.** Una cita necesita servicio, barbero, fecha y hora.
- **Consulta la agenda antes de proponer.** Si el turno está ocupado ofrece los tres más cercanos.
- **Solo escribe después de confirmar.** `_ejecutar` es la única función que crea, mueve o cancela una
  cita, y solo se llega a ella con el botón de confirmar o un «sí». Después informa lo que devolvió la API.
- **Si el clasificador duda, pregunta al LLM; si tampoco, ofrece opciones.** Cuando la confianza baja de
  0,95 o el mensaje parece fuera de alcance, pasa al LLM de respaldo, que devuelve el mismo marco de
  intención y ranuras. El LLM no tiene acceso a la agenda: lo que dice sigue el camino de siempre, con
  normalizador, catálogo y confirmación. Si no responde o tampoco lo entiende, el agente pregunta «¿Quieres
  que te agende una cita?» o muestra el menú con las acciones posibles y la opción de hablar con el barbero.

## Cómo habla y qué entiende

El agente le habla al cliente como su barbero: tutea, usa expresiones de Colombia («¡Qué más!», «¿Qué te
hacemos?», «¡Uy, sí, toca darle una arreglada a ese pelo!») y varía las muletillas para no sonar repetido,
pero las fechas, horas, precios y botones van siempre en el mismo formato. Lo que se agregó en la segunda
versión, a partir de lo que falló al probarlo en Telegram:

- **Cómo quiere el corte.** «Solo las puntas y el 7 con desvanecido» se reconoce como un corte clásico y la
  descripción aparece en el resumen y llega a la API como observación de la cita, para el barbero.
- **Correcciones.** «No bro, la cita es para el 16» mientras se arma una cita la corrige, aunque el
  clasificador la lea como otra intención. Con «Cambiar algo» aparecen botones para cambiar el día, la
  hora, el barbero o el servicio, y también se puede escribir.
- **El servicio sobreentendido.** «Me motila mañana a las 3», «estoy muy mechudo» o un «un corte» suelto
  bastan para saber que es un corte, aunque el clasificador no marque la ranura; «quiero lo de siempre»
  busca el servicio que el cliente más pide.
- **Dos días u horas en un mensaje.** Si el cliente nombra dos fechas distintas, el agente pregunta cuál en
  vez de escoger una.
- **«Cualquiera».** Si el agente acaba de preguntar con quién y el cliente contesta «cualquiera», «me da
  igual» o «el que esté libre», esa lectura gana sobre la del clasificador y la del LLM.
- **Fuera del horario.** «En la madrugada» o «en la noche» después del cierre llevan a los primeros o a
  los últimos turnos del día, con el horario de atención.
- **Turnos cada media hora.** «A las 9:52» cae dentro del horario pero no es un turno: el agente explica que
  las citas van en punto y a la media hora y ofrece las más cercanas (9:30, 10:00 y 10:30).
- **La hora y la franja juntas.** Si la hora trae a. m. o p. m., manda la hora: «en la madrugada a las 9:52
  a. m.» son las 9:52. Si no, la franja decide si es de la mañana o de la tarde: «en la madrugada a las 4»
  son las 4:00 a. m., antes de abrir, y lo dice una sola vez.
- **«Cualquiera» se mantiene.** El barbero que le tocó al cliente que no tenía preferencia no lo amarra:
  si después cambia la hora, el agente busca a quien esté libre a esa hora.

Después revisé a mano 185 conversaciones más (reservar, consultar, cambiar, cancelar, mensajes combinados,
jerga y errores de escritura) y corregí lo que fallaba:

- **Dos cosas en un mensaje.** «Cancélala, quiero una cita para el lunes» cancela y sigue con la nueva, con
  el mismo servicio; «cancela todas mis citas» las muestra todas para confirmar.
- **Dejar que el agente escoja.** «La que tengas», «a cualquier hora», «la más tarde que tengas», «cualquier
  día» y «lo más pronto posible» llevan a la primera (o la última) hora libre y el agente dice cuál escogió.
  «No sé» vuelve a mostrar las opciones en vez de cancelar.
- **«¿Qué horas tienes?»** sin decir el servicio: el agente lo pide explicando que de él depende cuánto tiempo
  apartar, y luego muestra las horas de ese día.
- **Preguntas en medio de la reserva.** «¿Cuánto vale?», «¿hasta qué hora abren?», «hola» o «gracias» se
  contestan y la reserva sigue donde iba, con sus botones.
- **Mover la hora.** «Mejor más tarde» muestra los turnos siguientes; «una hora más tarde» corre la hora, y
  al cambiar una cita la corre desde la que tenía.
- **Un cliente, una cita a la vez.** El agente no ofrece horas que se crucen con otra cita del mismo cliente,
  aunque sea con otro barbero (la API tampoco lo deja).
- **Respuestas fijas.** Quién es el bot, hablar con alguien de la barbería, quejas, descuentos y domicilios
  remiten al teléfono de la barbería; «jajaja» o un pulgar arriba no se toman como errores (el pulgar
  confirma si hay algo por confirmar).
- **Lecturas nuevas.** «Korte», «0930», «en ocho días», «dentro de 15 días», «entre las 3 y las 4», «un corte y
  de una vez la barba», «ayer» (ya pasó) y «recuérdame» (el recordatorio sale el día anterior).
- **¿Qué barberos hay?** Responde con los barberos que están atendiendo y un botón para agendar con cada uno.
- **Una cita que no existe.** Si pide cambiar una cita y no tiene ninguna, le ofrece agendar una nueva con lo
  que dijo.

En Telegram, al tocar un botón el mensaje queda con la opción escogida («👉 9:00 a. m.»), y mientras el
agente procesa un texto aparece «escribiendo…».

## Registro del cliente

El sistema de la barbería exige documento y teléfono para crear un cliente. La primera vez que alguien
confirma una cita, el agente le pide compartir su número con el botón de Telegram (en el computador ese
botón queda detrás del ícono de los cuadritos, junto al emoji, y el agente lo dice). Si ese número ya está
en el sistema, lo reconoce; si no, le pide el documento y crea la ficha. El documento y el teléfono van
directo a la API y no se guardan en el agente.

## Horario de atención

El horario lo guarda la barbería en su base de datos y lo entrega api-citas (`GET /api/horario`). El agente
lo lee al arrancar y cada media hora; si la API no responde, usa el de `config.py` (lunes a sábado de 9:00 a. m.
a 7:00 p. m.). La API tampoco deja agendar fuera de ese horario, así que la web y el bot siguen la misma regla.

## Lo que falta

- **Festivos.** El horario es por día de la semana y no los conoce.
