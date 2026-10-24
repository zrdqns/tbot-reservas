"""Compara el clasificador y el normalizador con un LLM, como pide la Tabla IV del informe.

    python -m evaluacion.comparar_llm clasificador   LLM sin ejemplos frente al clasificador, en los 370 mensajes de prueba
    python -m evaluacion.comparar_llm fechas         LLM sin reglas frente al normalizador, en las 200 expresiones

El LLM es el mismo del respaldo (bot/respaldo.py). Recibe el esquema descrito con palabras, sin ningún
mensaje resuelto, y contesta por lotes. Sus respuestas se guardan en evaluacion/salidas_llm/ para poder
revisarlas y para no repetir las consultas.
"""
import json
import statistics
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from bot import config, respaldo
from bot.comprension import entender  # noqa: F401  (deja modelo/ en la ruta de importación)
from bot.formato import DIAS
from entender import etiquetar, tramos
from esquema import tokenizar

from .evaluar_fechas import leer as leer_expresiones
from .evaluar_fechas import valor as valor_reglas

AQUI = Path(__file__).parent
SALIDAS = AQUI / "salidas_llm"
VARIOS = ('\n\nRecibirás varios mensajes numerados, independientes entre sí. Responde solo con JSON: '
          '{"resultados": [{"n": 1, "intencion": "...", "ranuras": [{"tipo": "...", "valor": "..."}]}]}, '
          'con un resultado por mensaje.')

TIEMPO = """Conviertes expresiones de tiempo escritas por clientes de una barbería de Colombia en valores exactos. \
Recibes el tipo de expresión, la fecha de referencia (el día en que el cliente escribe) y una lista numerada de \
expresiones. Devuelves el valor de cada una.

Tipo fecha:
- Un día: AAAA-MM-DD.
- Varios días: AAAA-MM-DD..AAAA-MM-DD. «Esta semana» va de hoy al domingo; la semana siguiente va de lunes a \
domingo; el fin de semana es sábado y domingo, y si hoy ya es sábado o domingo empieza hoy.
- Una pregunta general por un día de la semana, sin fecha concreta: habitual:<día en minúsculas y sin tilde>.
- Un día de la semana sin más es el próximo, sin contar hoy; con «este» sí puede ser hoy. «El otro sábado» es \
el sábado que sigue al próximo. Un día «de la otra semana» o «de la próxima semana» es el de la semana \
calendario siguiente.
- Un número de día sin mes es el próximo día con ese número, contando hoy. Una fecha con mes que ya pasó es la \
del año siguiente.
- «En ocho días» son siete días y «en quince días» son catorce, como se usa en Colombia. «El sábado en ocho» \
es una semana después del próximo sábado.

Tipo hora: la barbería atiende de 09:00 a 19:00. Una cita puede empezar desde las 09:00 y antes de las 19:00.
- Una hora de reloj: HH:MM en 24 horas. Si no dice si es de la mañana o de la tarde, es la lectura que cae \
dentro del horario de atención.
- Si ninguna lectura cae en el horario de atención: fuera.
- Si es relativa al momento en que escribe: +N, con N en minutos. «Ahora» es +0.
- La primera o la última hora del día: primera o ultima.

Tipo franja: HH:MM-HH:MM en 24 horas, con * en el extremo que queda abierto. La mañana es *-12:00, la tarde \
12:00-18:00, la noche 18:00-*, temprano *-10:30, media mañana 10:00-11:30, media tarde 15:00-16:30 y el final \
de la tarde 17:00-*. El almuerzo va de 12:00 a 14:00. Las horas sin mañana o tarde se leen dentro del horario \
de atención. Si la expresión se refiere a hoy («esta tarde»), añade « hoy» al final.

Responde solo con JSON: {"resultados": [{"n": 1, "valor": "..."}]}, con un resultado por expresión."""


def por_lotes(nombre, elementos, clave, sistema, encabezado, texto, tam):
    """Consulta el LLM por lotes y guarda cada respuesta. Devuelve {clave: resultado} y los tokens gastados."""
    SALIDAS.mkdir(exist_ok=True)
    archivo = SALIDAS / f"{nombre}.json"
    guardado = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else {}
    faltan, tokens = [e for e in elementos if clave(e) not in guardado], 0
    for i in range(0, len(faltan), tam):
        lote = faltan[i:i + tam]
        pregunta = encabezado(lote[0]) + "\n".join(f"{n}. {texto(e)}" for n, e in enumerate(lote, 1))
        respuesta, gastados = {}, 0
        for esfuerzo in ("medium", "low"):          # si no alcanza a terminar la respuesta, se repite pensando menos
            try:
                respuesta, gastados = respaldo.chat(sistema, pregunta, esfuerzo, espera=90, reintentos=8, maximo=6000)
                break
            except respaldo.SinRespuesta as error:
                print(f"  {nombre}: lote sin respuesta ({str(error)[:80]})", file=sys.stderr)
        tokens += gastados
        por_numero = {r.get("n"): r for r in respuesta.get("resultados", []) if isinstance(r, dict)}
        for n, e in enumerate(lote, 1):
            guardado[clave(e)] = por_numero.get(n)
        archivo.write_text(json.dumps(guardado, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {nombre}: {min(i + tam, len(faltan))} de {len(faltan)} consultados", file=sys.stderr)
    return guardado, tokens


# --------------------------------------------------------------------------- clasificador

def a_tramos(texto, ranuras):
    """Ranuras como texto -> {(tipo, primera palabra, última palabra + 1)}, igual que las etiquetas BIO."""
    palabras, salida, desde = tokenizar(texto), set(), 0
    for r in ranuras:
        donde = texto.lower().find(r["valor"].lower(), desde)
        donde = donde if donde >= 0 else texto.lower().find(r["valor"].lower())
        dentro = [i for i, (_, a, b) in enumerate(palabras) if a >= donde and b <= donde + len(r["valor"])]
        if donde >= 0 and dentro:
            salida.add((r["tipo"], dentro[0], dentro[-1] + 1))
            desde = donde + len(r["valor"])
    return salida


def medir(prueba, predicciones):
    """predicciones: [(intención, tramos)] en el orden de la prueba."""
    vp = fp = fn = bien = completos = 0
    for e, (intencion, hallados) in zip(prueba, predicciones):
        oro = tramos(e["etiquetas"])
        vp, fp, fn = vp + len(oro & hallados), fp + len(hallados - oro), fn + len(oro - hallados)
        bien += intencion == e["intencion"]
        completos += intencion == e["intencion"] and oro == hallados
    precision, exhaustividad = vp / max(vp + fp, 1), vp / max(vp + fn, 1)
    n = len(prueba)
    return bien / n, 2 * precision * exhaustividad / max(precision + exhaustividad, 1e-9), completos / n


def clasificador():
    prueba = [json.loads(l) for l in open(config.RAIZ / "corpus" / "datos" / "test.jsonl", encoding="utf-8")]
    respuestas, tokens = por_lotes("clasificador", prueba, lambda e: e["id"], respaldo.ESQUEMA + VARIOS,
                                   lambda e: "Mensajes:\n", lambda e: e["texto"], 10)
    del_modelo, del_llm, hibrido, al_llm = [], [], [], 0
    for e in prueba:
        intencion, confianza, etiquetas = etiquetar(e["tokens"])
        marco = respaldo.validar(respuestas[e["id"]], e["texto"])
        modelo = (intencion, tramos(etiquetas))
        llm = (marco["intencion"], a_tramos(e["texto"], marco["ranuras"])) if marco else ("sin respuesta", set())
        duda = confianza < config.UMBRAL or intencion == "fuera_de_alcance"
        al_llm += duda
        del_modelo.append(modelo)
        del_llm.append(llm)
        hibrido.append(llm if duda and marco else modelo)

    sistemas = [("Clasificador (BETO ajustado)", del_modelo), (f"LLM sin ejemplos ({respaldo.MODELO})", del_llm),
                ("Híbrido: clasificador y, si duda, LLM", hibrido)]
    lineas = ["| Sistema | Intención | F1 de ranuras | Mensaje completo |", "|---|---|---|---|"]
    for nombre, predicciones in sistemas:
        lineas.append(f"| {nombre} | " + " | ".join(f"{100 * v:.1f} %" for v in medir(prueba, predicciones)) + " |")
    bloques = [("base", "Primera versión"), ("reales", "Mensajes reales"), ("colombiano", "Registro colombiano")]
    indices = {b: [i for i, e in enumerate(prueba) if e.get("grupo") == b] for b, _ in bloques}
    lineas += ["", "Mensaje completo por bloque de la prueba:", "",
               "| Sistema | " + " | ".join(f"{t} ({len(indices[b])})" for b, t in bloques) + " |", "|---|---|---|---|"]
    for nombre, predicciones in sistemas:
        celdas = [medir([prueba[i] for i in indices[b]], [predicciones[i] for i in indices[b]])[2] for b, _ in bloques]
        lineas.append(f"| {nombre} | " + " | ".join(f"{100 * v:.1f} %" for v in celdas) + " |")
    lineas += ["", f"- Mensajes en que el clasificador duda y pasan al LLM: {al_llm} de {len(prueba)} ({al_llm / len(prueba):.1%})."]
    if tokens:
        lineas.append(f"- Tokens gastados en esta corrida: {tokens}.")

    # tiempo de una consulta suelta, que es como trabaja el respaldo dentro del agente
    tiempos = []
    for e in prueba[:12]:
        inicio = time.perf_counter()
        if respaldo.interpretar(e["texto"]):
            tiempos.append(time.perf_counter() - inicio)
        time.sleep(4)
    if tiempos:
        lineas.append(f"- Tiempo de una consulta al LLM: {statistics.median(tiempos):.1f} s de mediana y {max(tiempos):.1f} s la más "
                      f"lenta, en {len(tiempos)} consultas.")
    errores = Counter((e["intencion"], llm[0]) for e, llm in zip(prueba, del_llm) if llm[0] != e["intencion"])
    lineas += ["", "Confusiones de intención más frecuentes del LLM (real → predicha): "
               + "; ".join(f"{a} → {b} ({n})" for (a, b), n in errores.most_common(6)) + "."]
    print("\n".join(lineas))


# --------------------------------------------------------------------------- fechas

def equivale(tipo, obtenido, esperado):
    """El mismo valor escrito de otra manera: una franja que empieza al abrir o termina al cerrar, y la primera hora."""
    if tipo == "franja":
        abierta = lambda v: v.replace("09:00-", "*-").replace("-19:00", "-*")
        return abierta(obtenido) == abierta(esperado)
    primera = {"primera": "09:00"}
    return primera.get(obtenido, obtenido) == primera.get(esperado, esperado)


def fechas():
    filas = leer_expresiones()
    grupos = {}
    for fila in filas:
        grupos.setdefault((fila["tipo"], fila["referencia"]), []).append(fila)
    respuestas, tokens = {}, 0

    def encabezado(fila):
        if fila["referencia"] == "-":
            return f"Tipo: {fila['tipo']}\nExpresiones:\n"
        dia = date.fromisoformat(fila["referencia"])
        return f"Tipo: fecha\nFecha de referencia: {fila['referencia']} ({DIAS[dia.weekday()]})\nExpresiones:\n"

    for (tipo, referencia), grupo in grupos.items():
        parte, gastados = por_lotes("fechas", grupo, lambda f: f"{f['tipo']}|{f['expresion']}|{f['referencia']}", TIEMPO,
                                    encabezado, lambda f: f["expresion"], 25)
        respuestas.update(parte)
        tokens += gastados

    total, reglas, llm, parecido, fallos = Counter(), Counter(), Counter(), Counter(), []
    for fila in filas:
        dado = respuestas.get(f"{fila['tipo']}|{fila['expresion']}|{fila['referencia']}") or {}
        obtenido = str(dado.get("valor", "sin respuesta")).strip()
        total[fila["tipo"]] += 1
        reglas[fila["tipo"]] += valor_reglas(fila["tipo"], fila["expresion"], fila["referencia"]) == fila["esperado"]
        llm[fila["tipo"]] += obtenido == fila["esperado"]
        parecido[fila["tipo"]] += equivale(fila["tipo"], obtenido, fila["esperado"])
        if obtenido != fila["esperado"]:
            nota = " (equivalente)" if equivale(fila["tipo"], obtenido, fila["esperado"]) else ""
            fallos.append(f"- «{fila['expresion']}» ({fila['referencia']}): esperado {fila['esperado']}, el LLM dio {obtenido}{nota}")
    lineas = [f"| Tipo | Expresiones | Reglas | LLM sin reglas ({respaldo.MODELO}) | LLM, contando valores equivalentes |",
              "|---|---|---|---|---|"]
    for tipo in total:
        lineas.append(f"| {tipo} | {total[tipo]} | {reglas[tipo] / total[tipo]:.1%} | {llm[tipo] / total[tipo]:.1%} | "
                      f"{parecido[tipo] / total[tipo]:.1%} |")
    n = sum(total.values())
    lineas.append(f"| **Total** | {n} | {sum(reglas.values()) / n:.1%} | {sum(llm.values()) / n:.1%} | "
                  f"{sum(parecido.values()) / n:.1%} |")
    if tokens:
        lineas += ["", f"Tokens gastados en esta corrida: {tokens}."]
    lineas += ["", "Expresiones en que el LLM dio otro valor:", ""] + fallos
    print("\n".join(lineas))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"clasificador": clasificador, "fechas": fechas}[sys.argv[1]]()
