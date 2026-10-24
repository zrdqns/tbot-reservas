# Guía de anotación

Cada mensaje del corpus lleva **una intención** y cero o más **ranuras**. La intención dice qué quiere el
cliente; las ranuras son los tramos del mensaje que traen los datos de la cita. Sigo el esquema del
informe: nueve intenciones, seis ranuras y etiquetas BIO por palabra.

```
corte       con  Camilo     mañana   a       las     3        -> reservar
B-servicio  O    B-barbero  B-fecha  B-hora  I-hora  I-hora
```

Los mensajes se escriben con las ranuras entre corchetes, como en MASSIVE:

```
reservar quiero un [servicio : corte] con [barbero : Camilo] [fecha : mañana] [hora : a las 3]
```

## Intenciones

| Intención | Cuándo se usa | Ejemplos |
|---|---|---|
| `reservar` | Pide una cita nueva. | «me agendas un corte mañana», «necesito motilarme hoy» |
| `reprogramar` | Cambia algo de una cita que ya tiene: día, hora, barbero o servicio. | «cámbieme la del sábado para el lunes», «ya no puedo el viernes, mejor el sábado» |
| `cancelar` | Quiere que la cita deje de existir. | «cancela mi cita del viernes», «ya no voy a poder ir mañana» |
| `consultar_disponibilidad` | Pregunta por cupos, turnos libres, horario de atención o qué barberos hay. | «¿tiene cupo mañana en la tarde?», «¿abren los domingos?», «¿qué barberos hay?» |
| `consultar_servicios` | Pregunta por servicios, precios o duración. | «¿cuánto vale el corte?», «¿hacen tinte?» |
| `consultar_citas` | Pregunta por sus propias citas. | «¿a qué hora es mi cita?», «¿tengo cita mañana?» |
| `afirmar` | Acepta lo que el agente propuso, sin datos nuevos. | «sí», «dale», «listo, confirmo» |
| `negar` | Rechaza lo que el agente propuso, sin datos nuevos. | «no», «mejor no», «así no era» |
| `fuera_de_alcance` | Todo lo demás. | «¿venden cera para el pelo?», «¿dónde quedan?», «hola» |

Reglas para decidir:

1. **Un mensaje, una intención.** Si pregunta y además pide agendar, gana la acción: «necesito motilarme
   hoy, ¿tienen algo tipo 5?» es `reservar`.
2. **Reservar frente a reprogramar.** Es `reprogramar` solo si el mensaje habla de una cita que ya existe
   («mi cita», «la del sábado», «ya no puedo el viernes»). «Quiero otra cita para la otra semana» es
   `reservar`.
3. **Reprogramar frente a cancelar.** Si propone otro momento es `reprogramar`; si solo avisa que no va, es
   `cancelar`. «Ya no puedo ir mañana» es `cancelar`; «ya no puedo mañana, mejor el jueves» es `reprogramar`.
4. **Respuestas que solo traen datos.** «Mañana a las 3», «con Andrés» o «Daniel Vanegas» contestan una
   pregunta del agente. Se etiquetan `reservar`, que es la intención por defecto, y la política las aplica
   a la conversación en curso.
5. **Afirmar y negar no llevan ranuras.** «Sí, pero con Julián» o «no, mejor el viernes» traen un dato
   nuevo y se etiquetan `reservar`.
6. **Fuera de alcance no lleva ranuras**, aunque mencione una fecha o un servicio: «¿qué clima va a hacer
   mañana?», «me dejaron mal el corte». Aquí entran las preguntas sobre el negocio que el agente no
   atiende (dirección, medios de pago, productos, empleo, quejas), los saludos y agradecimientos sueltos,
   los consejos («¿qué corte me recomiendas?») y los pedidos a otros negocios («agéndame una cita con el
   odontólogo»).

## Ranuras

Los tramos de tiempo se anotan completos, tal como pasan al normalizador de fechas. Los de servicio,
barbero y nombre llevan solo el valor.

| Ranura | Qué incluye el tramo | Qué queda fuera | Ejemplos |
|---|---|---|---|
| `servicio` | El servicio, como sustantivo o como verbo con su complemento, o la descripción de cómo quiere el corte. | El artículo y el pronombre separado, salvo en la descripción del corte. | un [corte], la [barba], [corte y barba], [cortarme el pelo], me [corten el pelo], [lo de siempre], [solo las puntas], [el 7 con desvanecido] |
| `barbero` | El nombre o apodo del barbero, o la descripción cuando no hay preferencia. | «con», «don», «el barbero». | con [Camilo], con don [Jairo], con [cualquiera], con [el que esté libre], con [el de siempre] |
| `fecha` | El día con su artículo o determinante. | «para», «pa», «de». Con «del» y «pal» el tramo empieza después. | [mañana], [el sábado], [este sábado], [el otro sábado], [el 15 de octubre], [la otra semana], para [el lunes], del [viernes] |
| `hora` | La hora de reloj con la partícula que la introduce. | «para», «de», «desde», «hasta». | [a las 3], [tipo tres], [como a las 4], [3pm], [a las 3 de la tarde], [a mediodía], [a primera hora], [ahorita], para [las 5] |
| `franja` | Una parte del día o un intervalo. | «para». | [en la tarde], [por la mañana], [temprano], [esta tarde], [después de las 5], [antes del mediodía], para [la tarde] |
| `nombre` | El nombre del cliente o de la persona para quien es la cita. | «a nombre de», «soy». | a nombre de [Daniel Vanegas], soy [Carlos], para mi hijo [Samuel] |

Casos que se repiten:

- **«Mañana» dos veces.** En «mañana en la mañana» el primero es `fecha` y «en la mañana» es `franja`.
- **Hora con parte del día.** «A las 3 de la tarde» es una sola `hora`. En «el sábado en la tarde tipo 4»
  hay `fecha`, `franja` y `hora`.
- **Intervalos.** «Después de las 5», «antes de las 10» o «entre las 3 y las 4» son `franja`, no `hora`.
- **Servicios unidos.** «Corte y barba», «corte con barba» o «corte + barba» van en un solo tramo, porque
  el catálogo los ofrece como un servicio. Si hay otras palabras en medio («un corte y de una vez la
  barba») son dos tramos.
- **Dos valores de la misma ranura.** En «cámbieme la del sábado para el lunes» hay dos fechas, y en «de las
  2 a las 4», dos horas. Se anotan las dos; la política decide cuál es la cita actual y cuál la nueva.
- **Un nombre suelto.** Sin nada alrededor, un nombre de pila («Andrés») se anota como `barbero` y un
  nombre con apellido («Daniel Vanegas») como `nombre`. La política lo corrige con la pregunta que acababa
  de hacer.
- **Servicios que la barbería no ofrece** («cejas», «keratina») también se anotan: el agente necesita
  reconocerlos para responder que no los hace.
- **Lo que no describe la cita no se anota:** «que después entro a trabajar», «ya me motilé en otro lado»,
  «salgo tarde del trabajo».
- **Expresiones vagas** como «lo más pronto posible», «más tarde», «otro día» o «a la misma hora» no se
  anotan; el agente tiene que preguntar.
- **Errores de escritura.** El tramo se anota como viene: [korte], [el savado], [manana].

Casos que agregué en la segunda versión, con lo que falló al probar el bot en Telegram:

- **Cómo quiere el corte.** La descripción va completa en `servicio`, con el número de la guarda y su
  artículo, porque el agente se la pasa al barbero como observación de la cita: quiero [solo las puntas] y
  [el 7 con desvanecido], un [desvanecido con el 2 a los lados], [todo al 3]. Un número que describe el
  corte nunca es `fecha` ni `hora`: en «dame una cita para [el 16] … [el 7 con desvanecido]» solo el 16 es
  fecha.
- **Correcciones mientras agenda.** «No bro, la cita es para [el 16]» o «uy no, era para [el 21]» son
  `reservar`: corrigen la cita que se está armando. Lo que el cliente niega no se anota: «te dije
  [el 16], no el 7».
- **Sin preferencia de barbero.** Contestar «[cualquiera]», «[cualquiera de los dos]» o «[el que esté
  libre]» a la pregunta del agente es `reservar` con esa ranura de barbero.
- **Qué barberos hay.** «¿Qué barberos hay?», «¿con quién puedo agendar?» y «¿cuántos barberos trabajan
  ahí?» son `consultar_disponibilidad`: el agente contesta con los barberos que están atendiendo.
- **Registro colombiano.** «Oe», «quiubo», «parce», «mi llave», «sisas», «melo», «nanay», «le caigo
  mañana» o «pal 16» se anotan igual que cualquier otra forma de decirlo. El verbo que nombra el servicio
  va en `servicio` aunque no traiga complemento, como [motilarme]: «me [motila] mañana», «¿me puede
  [peluquear]?», «me toca [motilada]». Lo que el cliente cuenta de sí («estoy muy mechudo», «tengo
  matrimonio el sábado») no describe la cita y no se anota.
- **Madrugada.** «En la madrugada» o «bien de madrugada» son `franja`, aunque la barbería no atienda a esa
  hora; el agente le ofrece los primeros turnos del día.
