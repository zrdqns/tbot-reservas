"""Comprensión de un mensaje con el modelo exportado: intención, confianza y ranuras.

    py entender.py "me agenda un corte con Camilo mañana tipo tres"
    py entender.py --prueba        mide el modelo en corpus/datos/test.jsonl

Usa ONNX Runtime y el tokenizador guardado en modelo_tbot/; no necesita PyTorch.
"""
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

AQUI = Path(__file__).parent
sys.path.append(str(AQUI.parent / "corpus"))
from esquema import tokenizar  # noqa: E402  (el mismo tokenizador con que se armó el corpus)

# En el repositorio el modelo va comprimido (el .onnx pasa de los 100 MB que acepta GitHub): se descomprime una vez
if not (AQUI / "modelo_tbot" / "modelo_int8.onnx").exists():
    zipfile.ZipFile(AQUI / "modelo_tbot.zip").extractall(AQUI / "modelo_tbot")

_esquema = json.loads((AQUI / "modelo_tbot" / "esquema.json").read_text(encoding="utf-8"))
INTENCIONES, ETIQUETAS = _esquema["intenciones"], _esquema["etiquetas"]
_tok = Tokenizer.from_file(str(AQUI / "modelo_tbot" / "tokenizer.json"))
_tok.enable_truncation(64)
_sesion = ort.InferenceSession(str(AQUI / "modelo_tbot" / "modelo_int8.onnx"), providers=["CPUExecutionProvider"])


def tramos(etiquetas):
    """Etiquetas BIO -> {(tipo, primera palabra, última palabra + 1)}."""
    salida, inicio, tipo = set(), None, None
    for i, e in enumerate(list(etiquetas) + ["O"]):
        if tipo is not None and (e == "O" or e.startswith("B-") or e[2:] != tipo):
            salida.add((tipo, inicio, i))
            tipo = None
        if e != "O" and tipo is None:
            inicio, tipo = i, e[2:]
    return salida


def etiquetar(palabras):
    """Intención, confianza y etiqueta BIO de cada palabra."""
    enc = _tok.encode(palabras, is_pretokenized=True)
    log_int, log_ran = _sesion.run(None, {"input_ids": np.array([enc.ids], dtype=np.int64),
                                          "attention_mask": np.array([enc.attention_mask], dtype=np.int64)})
    prob = np.exp(log_int[0] - log_int[0].max())
    prob /= prob.sum()
    etiquetas, anterior = ["O"] * len(palabras), None
    for j, p in enumerate(enc.word_ids):
        if p is not None and p != anterior:
            etiquetas[p] = ETIQUETAS[int(log_ran[0, j].argmax())]
        anterior = p
    return INTENCIONES[int(prob.argmax())], float(prob.max()), etiquetas


def entender(texto):
    """{'intencion', 'confianza', 'ranuras': [{'tipo', 'valor'}]} con el texto tal como lo escribió el cliente."""
    palabras = tokenizar(texto)
    if not palabras:
        return {"intencion": "fuera_de_alcance", "confianza": 1.0, "ranuras": []}
    intencion, confianza, etiquetas = etiquetar([p for p, _, _ in palabras])
    ranuras = [{"tipo": tipo, "valor": texto[palabras[a][1]:palabras[b - 1][2]]}
               for tipo, a, b in sorted(tramos(etiquetas), key=lambda t: t[1])]
    return {"intencion": intencion, "confianza": round(confianza, 3), "ranuras": ranuras}


def _medir(prueba, predicciones):
    vp = fp = fn = bien = completos = 0
    for e, (intencion, etiquetas) in zip(prueba, predicciones):
        oro, hip = tramos(e["etiquetas"]), tramos(etiquetas)
        vp, fp, fn = vp + len(oro & hip), fp + len(hip - oro), fn + len(oro - hip)
        bien += intencion == e["intencion"]
        completos += intencion == e["intencion"] and oro == hip
    precision, exhaustividad = vp / max(vp + fp, 1), vp / max(vp + fn, 1)
    n = len(prueba)
    return (f"{n} mensajes | intención {bien / n:.1%} | F1 ranuras "
            f"{2 * precision * exhaustividad / max(precision + exhaustividad, 1e-9):.1%} | mensaje completo {completos / n:.1%}")


def medir_prueba():
    prueba = [json.loads(linea) for linea in open(AQUI.parent / "corpus" / "datos" / "test.jsonl", encoding="utf-8")]
    inicio = time.time()
    predicciones = [etiquetar(e["tokens"])[::2] for e in prueba]
    print(f"Toda la prueba: {_medir(prueba, predicciones)} | "
          f"{1000 * (time.time() - inicio) / len(prueba):.0f} ms por mensaje")
    for grupo, nombre in [("base", "Primera versión"), ("reales", "Mensajes reales"),
                          ("colombiano", "Registro colombiano")]:
        parte = [(e, p) for e, p in zip(prueba, predicciones) if e.get("grupo") == grupo]
        if parte:
            print(f"{nombre}: {_medir(*zip(*parte))}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--prueba"]:
        medir_prueba()
    else:
        for mensaje in sys.argv[1:] or iter(lambda: input("> "), ""):
            print(json.dumps(entender(mensaje), ensure_ascii=False))
