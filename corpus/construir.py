"""Arma el corpus: mensajes redactados + generador -> datos/train.jsonl, val.jsonl y test.jsonl.

    py construir.py

El conjunto de prueba se lee primero y nada de lo que entra a entrenamiento o validación puede repetirlo.
"""
import json
import random
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

import generador as g
from esquema import INTENCIONES, RANURAS, ejemplo, revisar

AQUI = Path(__file__).parent
SEMILLA = 2026
TOTAL = 2600
# Mensajes por intención en todo el corpus; reservar absorbe lo que falte para llegar a TOTAL
OBJETIVO = {"reprogramar": 300, "cancelar": 240, "consultar_disponibilidad": 330, "consultar_servicios": 240,
            "consultar_citas": 180, "afirmar": 160, "negar": 140}
PARTE_VAL = 250 / 1700
PARTE_FRAGMENTOS = 0.26   # parte de reservar generado que son respuestas con solo datos o correcciones


def clave(texto):
    """Forma normalizada para detectar repetidos: sin mayúsculas, tildes ni signos."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip() or texto


def grupo(seccion):
    """Bloque de la prueba al que pertenece un mensaje, según el título de su sección."""
    if "mensajes reales" in seccion:
        return "reales"
    return "colombiano" if "versión 2" in seccion else "base"


def leer_redactados(nombre):
    ejemplos, seccion = [], ""
    for n, linea in enumerate((AQUI / "redactados" / nombre).read_text(encoding="utf-8").splitlines(), 1):
        linea = linea.strip()
        if linea.startswith("# ---"):
            seccion = linea
        if not linea or linea.startswith("#"):
            continue
        intencion, _, anotado = linea.partition(" ")
        try:
            ej = ejemplo(intencion, anotado)
        except ValueError as e:
            sys.exit(f"{nombre}:{n}: {e}")
        if revisar(ej):
            sys.exit(f"{nombre}:{n}: {revisar(ej)} en «{anotado}»")
        ejemplos.append({**ej, "origen": "redactado", "plantilla": None, "grupo": grupo(seccion)})
    return ejemplos


def generar(intencion, n, plantillas, prefijo, rng, vistos):
    """n mensajes distintos de una intención, repartidos entre los marcos dados."""
    salida, usos, fallos = [], Counter(), 0
    tope = max(4, 2 * n // len(plantillas) + 1)
    while len(salida) < n:
        i, plantilla = rng.choice(plantillas)
        limite = tope if "{" in plantilla else 3
        if usos[i] >= limite + fallos // 300:
            fallos += 1
            continue
        ej = ejemplo(intencion, g.mensaje(intencion, plantilla, rng))
        if revisar(ej):
            sys.exit(f"{prefijo}-{i:02d}: {revisar(ej)} en «{ej['texto']}»")
        k = clave(ej["texto"])
        if k in vistos:
            fallos += 1
            continue
        vistos.add(k)
        usos[i] += 1
        salida.append({**ej, "origen": "generado", "plantilla": f"{prefijo}-{i:02d}"})
    return salida


def generar_respuestas(intencion, n, rng, vistos):
    funcion = g.afirmar if intencion == "afirmar" else g.negar
    salida = []
    while len(salida) < n:
        ej = ejemplo(intencion, funcion(rng))
        k = clave(ej["texto"])
        if k not in vistos:
            vistos.add(k)
            salida.append({**ej, "origen": "generado", "plantilla": None})
    return salida


def partir(plantillas, rng):
    """Separa los marcos: los de validación no se usan en entrenamiento."""
    marcos = list(enumerate(plantillas))
    rng.shuffle(marcos)
    corte = max(2, round(len(marcos) * PARTE_VAL))
    return marcos[corte:], marcos[:corte]


def main():
    rng = random.Random(SEMILLA)
    prueba = leer_redactados("prueba.txt")
    banco = leer_redactados("entrenamiento.txt")

    vistos = set()
    for ej in prueba:
        if clave(ej["texto"]) in vistos:
            sys.exit(f"repetido en prueba: «{ej['texto']}»")
        vistos.add(clave(ej["texto"]))
    descartados = [ej["texto"] for ej in banco if clave(ej["texto"]) in vistos]
    banco = [ej for ej in banco if clave(ej["texto"]) not in vistos]
    unicos = {}
    for ej in banco:
        unicos.setdefault(clave(ej["texto"]), ej)
    banco = list(unicos.values())
    vistos.update(unicos)

    en_prueba = Counter(ej["intencion"] for ej in prueba)
    en_banco = Counter(ej["intencion"] for ej in banco)
    objetivo = dict(OBJETIVO)
    objetivo["fuera_de_alcance"] = en_prueba["fuera_de_alcance"] + en_banco["fuera_de_alcance"]
    objetivo["reservar"] = TOTAL - sum(objetivo.values())

    train, val = [], []
    for intencion in INTENCIONES:
        redactados = [ej for ej in banco if ej["intencion"] == intencion]
        rng.shuffle(redactados)
        n_total = objetivo[intencion] - en_prueba[intencion]
        n_val = round(n_total * PARTE_VAL)
        n_val_red = round(len(redactados) * PARTE_VAL)
        val += redactados[:n_val_red]
        train += redactados[n_val_red:]
        gen_val, gen_train = n_val - n_val_red, n_total - n_val - (len(redactados) - n_val_red)
        if intencion in ("afirmar", "negar"):
            respuestas = generar_respuestas(intencion, gen_val + gen_train, rng, vistos)
            val += respuestas[:gen_val]
            train += respuestas[gen_val:]
        elif intencion in g.PLANTILLAS:
            bloques = [(g.PLANTILLAS[intencion], intencion[:3] if "_" not in intencion else intencion[10:13], 1.0)]
            if intencion == "reservar":
                bloques = [(g.RESERVAR, "res", 1 - PARTE_FRAGMENTOS), (g.FRAGMENTOS, "dat", PARTE_FRAGMENTOS)]
            resto_val, resto_train = gen_val, gen_train
            for j, (plantillas, prefijo, parte) in enumerate(bloques):
                ultimo = j == len(bloques) - 1
                nv = resto_val if ultimo else round(gen_val * parte)
                nt = resto_train if ultimo else round(gen_train * parte)
                resto_val, resto_train = resto_val - nv, resto_train - nt
                para_train, para_val = partir(plantillas, rng)
                val += generar(intencion, nv, para_val, prefijo, rng, vistos)
                train += generar(intencion, nt, para_train, prefijo, rng, vistos)

    partes = {"train": train, "val": val, "test": prueba}
    salida = AQUI / "datos"
    salida.mkdir(exist_ok=True)
    for nombre, ejemplos in partes.items():
        if nombre != "test":
            rng.shuffle(ejemplos)
        with open(salida / f"{nombre}.jsonl", "w", encoding="utf-8") as f:
            for i, ej in enumerate(ejemplos, 1):
                f.write(json.dumps({"id": f"{nombre}-{i:04d}", **ej}, ensure_ascii=False) + "\n")

    with zipfile.ZipFile(salida / "corpus_barberia.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in partes:
            z.write(salida / f"{nombre}.jsonl", f"{nombre}.jsonl")

    comprobar(partes)
    resumen = resumir(partes, descartados)
    (salida / "resumen.md").write_text(resumen, encoding="utf-8")
    print(resumen)


def comprobar(partes):
    """Ningún mensaje se repite y los marcos de validación no aparecen en entrenamiento."""
    claves = [clave(ej["texto"]) for ejemplos in partes.values() for ej in ejemplos]
    assert len(claves) == len(set(claves)), "hay mensajes repetidos"
    marcos = {n: {ej["plantilla"] for ej in partes[n] if ej["plantilla"]} for n in ("train", "val")}
    assert not marcos["train"] & marcos["val"], "un marco está en entrenamiento y en validación"
    for ejemplos in partes.values():
        for ej in ejemplos:
            assert not revisar(ej), (ej["texto"], revisar(ej))
            assert len(ej["tokens"]) == len(ej["etiquetas"])


def resumir(partes, descartados):
    todos = [ej for ejemplos in partes.values() for ej in ejemplos]
    lineas = ["# Resumen del corpus", "", f"Mensajes: {len(todos)}. Semilla del generador: {SEMILLA}.", "",
              "## Mensajes por intención", "", "| Intención | train | val | test | Total |", "|---|---|---|---|---|"]
    for intencion in INTENCIONES:
        n = [sum(ej["intencion"] == intencion for ej in partes[p]) for p in ("train", "val", "test")]
        lineas.append(f"| {intencion} | {n[0]} | {n[1]} | {n[2]} | {sum(n)} |")
    n = [len(partes[p]) for p in ("train", "val", "test")]
    lineas += [f"| **Total** | {n[0]} | {n[1]} | {n[2]} | {sum(n)} |", "", "## Ranuras anotadas", "",
               "| Ranura | train | val | test | Total |", "|---|---|---|---|---|"]
    for ranura in RANURAS:
        n = [sum(r["tipo"] == ranura for ej in partes[p] for r in ej["ranuras"]) for p in ("train", "val", "test")]
        lineas.append(f"| {ranura} | {n[0]} | {n[1]} | {n[2]} | {sum(n)} |")

    lineas += ["", "## Origen y forma", "", "| Parte | Redactados | Generados | Marcos | Palabras por mensaje | Con ranuras |",
               "|---|---|---|---|---|---|"]
    for p, ejemplos in partes.items():
        red = sum(ej["origen"] == "redactado" for ej in ejemplos)
        marcos = len({ej["plantilla"] for ej in ejemplos if ej["plantilla"]})
        largo = sum(len(ej["tokens"]) for ej in ejemplos) / len(ejemplos)
        con = sum(bool(ej["ranuras"]) for ej in ejemplos) / len(ejemplos)
        lineas.append(f"| {p} | {red} | {len(ejemplos) - red} | {marcos} | {largo:.1f} | {con:.0%} |")

    bloques = Counter(ej["grupo"] for ej in partes["test"])
    lineas += ["", f"La prueba tiene {bloques['base']} mensajes de la primera versión, {bloques['reales']} mensajes reales "
               f"escritos al bot durante las pruebas y {bloques['colombiano']} de la segunda versión, con registro "
               "colombiano, descripciones del corte y correcciones."]

    vocab = {t.lower() for ej in partes["train"] for t in ej["tokens"]}
    fuera = [t for ej in partes["test"] for t in ej["tokens"] if t.lower() not in vocab]
    total_test = sum(len(ej["tokens"]) for ej in partes["test"])
    valores = {(r["tipo"], clave(r["valor"])) for ej in partes["train"] for r in ej["ranuras"]}
    ranuras_test = [(r["tipo"], clave(r["valor"])) for ej in partes["test"] for r in ej["ranuras"]]
    nuevos = sum(v not in valores for v in ranuras_test)
    lineas += ["", "## Prueba frente a entrenamiento", "",
               f"- Vocabulario de entrenamiento: {len(vocab)} palabras distintas.",
               f"- Palabras de la prueba que no están en entrenamiento: {len(fuera)} de {total_test} "
               f"({len(fuera) / total_test:.1%}).",
               f"- Valores de ranura de la prueba que no están en entrenamiento: {nuevos} de {len(ranuras_test)} "
               f"({nuevos / len(ranuras_test):.1%}).",
               "- Mensajes repetidos entre las tres partes: 0."]
    if descartados:
        lineas += ["", f"Redactados de entrenamiento descartados por coincidir con la prueba: {len(descartados)}."]
        lineas += [f"- {t}" for t in descartados]
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    main()
