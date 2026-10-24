# Resumen del corpus

Mensajes: 2600. Semilla del generador: 2026.

## Mensajes por intención

| Intención | train | val | test | Total |
|---|---|---|---|---|
| reservar | 590 | 102 | 118 | 810 |
| reprogramar | 220 | 38 | 42 | 300 |
| cancelar | 177 | 31 | 32 | 240 |
| consultar_disponibilidad | 243 | 42 | 45 | 330 |
| consultar_servicios | 177 | 31 | 32 | 240 |
| consultar_citas | 132 | 23 | 25 | 180 |
| afirmar | 118 | 20 | 22 | 160 |
| negar | 103 | 18 | 19 | 140 |
| fuera_de_alcance | 141 | 24 | 35 | 200 |
| **Total** | 1901 | 329 | 370 | 2600 |

## Ranuras anotadas

| Ranura | train | val | test | Total |
|---|---|---|---|---|
| servicio | 587 | 100 | 105 | 792 |
| barbero | 242 | 44 | 46 | 332 |
| fecha | 967 | 152 | 200 | 1319 |
| hora | 427 | 72 | 86 | 585 |
| franja | 225 | 42 | 42 | 309 |
| nombre | 51 | 7 | 8 | 66 |

## Origen y forma

| Parte | Redactados | Generados | Marcos | Palabras por mensaje | Con ranuras |
|---|---|---|---|---|---|
| train | 485 | 1416 | 388 | 9.1 | 69% |
| val | 83 | 246 | 68 | 9.0 | 67% |
| test | 370 | 0 | 0 | 8.3 | 67% |

La prueba tiene 300 mensajes de la primera versión, 16 mensajes reales escritos al bot durante las pruebas y 54 de la segunda versión, con registro colombiano, descripciones del corte y correcciones.

## Prueba frente a entrenamiento

- Vocabulario de entrenamiento: 1254 palabras distintas.
- Palabras de la prueba que no están en entrenamiento: 115 de 3064 (3.8%).
- Valores de ranura de la prueba que no están en entrenamiento: 64 de 487 (13.1%).
- Mensajes repetidos entre las tres partes: 0.

Redactados de entrenamiento descartados por coincidir con la prueba: 2.
- cuánto vale el corte
- tienen wifi
