"""Mide el normalizador de fechas y horas con las 200 expresiones de expresiones_tiempo.csv.

    python -m evaluacion.evaluar_fechas

Una expresión cuenta como acierto solo si el valor es exactamente el esperado.
"""
import csv
import sys
from collections import Counter
from datetime import date, time
from pathlib import Path

from bot import fechas

AQUI = Path(__file__).parent
APERTURA, CIERRE = time(9), time(19)


def leer():
    lineas = [l for l in (AQUI / "expresiones_tiempo.csv").read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return list(csv.DictReader(lineas, delimiter=";"))


def valor(tipo, expresion, referencia):
    """Lo que entiende el normalizador, escrito como en la columna «esperado»."""
    if tipo == "fecha":
        f = fechas.fecha(expresion, date.fromisoformat(referencia))
        if f is None:
            return "sin valor"
        if f.habitual:
            return f"habitual:{f.habitual}"
        return f"{f.dia}..{f.hasta}" if f.hasta else str(f.dia)
    if tipo == "hora":
        h = fechas.hora(expresion)
        if h is None:
            return "sin valor"
        if h.especial or h.en_minutos is not None:
            return h.especial or f"+{h.en_minutos}"
        lecturas = fechas.en_horario(h, APERTURA, CIERRE)
        return lecturas[0].strftime("%H:%M") if len(lecturas) == 1 else "fuera" if not lecturas else "dos lecturas"
    fr = fechas.franja(expresion, APERTURA, CIERRE)
    if fr is None:
        return "sin valor"
    extremo = lambda t: t.strftime("%H:%M") if t else "*"
    return f"{extremo(fr.desde)}-{extremo(fr.hasta)}" + (" hoy" if fr.hoy else "")


def main():
    filas = leer()
    aciertos, total, fallos = Counter(), Counter(), []
    for fila in filas:
        obtenido = valor(fila["tipo"], fila["expresion"], fila["referencia"])
        total[fila["tipo"]] += 1
        if obtenido == fila["esperado"]:
            aciertos[fila["tipo"]] += 1
        else:
            fallos.append((fila, obtenido))
    lineas = ["| Tipo | Expresiones | Aciertos | Exactitud |", "|---|---|---|---|"]
    for tipo in total:
        lineas.append(f"| {tipo} | {total[tipo]} | {aciertos[tipo]} | {aciertos[tipo] / total[tipo]:.1%} |")
    n, a = sum(total.values()), sum(aciertos.values())
    lineas.append(f"| **Total** | {n} | {a} | {a / n:.1%} |")
    if fallos:
        lineas += ["", "Expresiones con valor equivocado:", ""]
        lineas += [f"- «{f['expresion']}» ({f['referencia']}): esperado {f['esperado']}, obtenido {o}" for f, o in fallos]
    print("\n".join(lineas))
    return "\n".join(lineas)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
