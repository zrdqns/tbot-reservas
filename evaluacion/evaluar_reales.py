"""Mide la comprensión con los mensajes que escribieron personas al bot en Telegram (mensajes_reales.txt).

    python -m evaluacion.evaluar_reales

Compara el clasificador, el LLM sin ejemplos y el híbrido que usa el agente, igual que comparar_llm con la
prueba del corpus. Las respuestas del LLM se guardan en evaluacion/salidas_llm/reales.json.
"""
from bot import config, respaldo
from bot.comprension import entender  # noqa: F401  (deja modelo/ en la ruta de importación)
from entender import etiquetar, tramos
from esquema import ejemplo, revisar

from .comparar_llm import VARIOS, a_tramos, medir, por_lotes

AQUI = config.RAIZ / "evaluacion"


def leer():
    prueba = []
    for n, linea in enumerate(open(AQUI / "mensajes_reales.txt", encoding="utf-8")):
        if linea.strip() and not linea.startswith("#"):
            intencion, anotado = linea.rstrip("\n").split(" ", 1)
            e = ejemplo(intencion, anotado)
            e["id"] = f"real-{n:03d}"
            assert not revisar(e), (linea, revisar(e))
            prueba.append(e)
    return prueba


def main():
    prueba = leer()
    respuestas, _ = por_lotes("reales", prueba, lambda e: e["id"], respaldo.ESQUEMA + VARIOS,
                              lambda e: "Mensajes:\n", lambda e: e["texto"], 10)
    del_modelo, del_llm, hibrido, fallos, dudas = [], [], [], [], 0
    for e in prueba:
        intencion, confianza, etiquetas = etiquetar(e["tokens"])
        marco = respaldo.validar(respuestas[e["id"]], e["texto"])
        modelo = (intencion, tramos(etiquetas))
        llm = (marco["intencion"], a_tramos(e["texto"], marco["ranuras"])) if marco else ("sin respuesta", set())
        duda = confianza < config.UMBRAL or intencion == "fuera_de_alcance"
        dudas += duda
        del_modelo.append(modelo)
        del_llm.append(llm)
        hibrido.append(llm if duda and marco else modelo)
        if hibrido[-1] != (e["intencion"], tramos(e["etiquetas"])):
            fallos.append(f"- «{e['texto']}»: esperado {e['intencion']}, salió {hibrido[-1][0]}"
                          + (" (pasó al LLM)" if duda else ""))
    print(f"{len(prueba)} mensajes reales; el clasificador duda en {dudas} ({dudas / len(prueba):.1%})\n")
    print("| Sistema | Intención | F1 de ranuras | Mensaje completo |\n|---|---|---|---|")
    for nombre, predicciones in [("Clasificador (BETO ajustado)", del_modelo), ("LLM sin ejemplos", del_llm),
                                 ("Híbrido: clasificador y, si duda, LLM", hibrido)]:
        print(f"| {nombre} | " + " | ".join(f"{100 * v:.1f} %" for v in medir(prueba, predicciones)) + " |")
    print("\nMensajes que el híbrido no acierta completos:\n" + "\n".join(fallos))


if __name__ == "__main__":
    main()
