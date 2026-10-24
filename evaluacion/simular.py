"""Mide la tarea completa: un cliente simulado ejecuta cada guion contra el agente y se compara la agenda.

    python -m evaluacion.simular            resumen de las 300 conversaciones (60 guiones, cinco repeticiones)
    python -m evaluacion.simular E06 2      muestra una conversación: guion E06, repetición 2

Seguimos el método de τ-bench: el guion fija lo que el cliente quiere y el estado en que debe quedar la
agenda; la conversación es un éxito solo si la agenda final es exactamente la esperada. Las cinco
repeticiones cambian la manera de pedirlo, de contestar y de confirmar, para medir la consistencia.
La agenda es una copia en memoria de la API, con sus mismas reglas y datos (bot/tests/agenda_falsa.py).
"""
import sys
import time
from collections import defaultdict

from bot.agente import Agente
from bot.comprension import entender
from bot.perfiles import Perfiles
from bot.tests.agenda_falsa import AgendaFalsa

from .guiones import AHORA, GUIONES

YO, NOMBRE = 77, "Daniel Vanegas"
REPETICIONES = 5
CONFIRMAR = ["#ok", "sí", "#ok", "dale", "listo, confirmo"]
MAXIMO = 15                                    # mensajes del cliente antes de darse por vencido


def siguiente(guion, rep, respuesta, memoria):
    """Lo que hace el cliente al leer la respuesta del agente: «#dato» toca un botón, «@número» comparte el
    teléfono, cualquier otro texto se escribe y None termina la conversación."""
    texto, botones = respuesta.texto, [dato for fila in respuesta.botones for _, dato in fila]
    for frase, reaccion in guion.si.items():
        if frase in texto and frase not in memoria["usadas"]:
            memoria["usadas"].add(frase)
            if reaccion == "primera":
                return "#" + botones[0]
            return "#" + reaccion if reaccion.split(":")[0] in ("srv", "bar", "dia", "hor", "cita") else reaccion
    if respuesta.pedir_contacto:
        return "@" + guion.telefono
    if "documento" in texto and not botones:
        return guion.documento
    if "ok" in botones:                         # el agente muestra el resumen y espera la confirmación
        if memoria["corrige"]:
            return memoria["corrige"].pop(0)
        if not guion.confirma:
            return "no, mejor no"
        if all(dato in texto for dato in guion.quiere):
            return CONFIRMAR[rep % len(CONFIRMAR)]
        if not memoria["repitio"]:              # el resumen no es lo que pidió: lo dice otra vez, una sola vez
            memoria["repitio"] = True
            return guion.abre[0]
        return "no, así no"
    for clave in ("srv", "bar", "dia", "hor", "cita"):
        if any(b.startswith(clave + ":") for b in botones):
            if clave not in guion.sabe:
                return None
            frases, boton = guion.sabe[clave]
            if not frases or (rep % 2 == 1 and boton in botones):
                return "#" + boton if boton in botones else None
            return frases[rep % len(frases)]
    if memoria["corrige"] and "¿qué le cambiamos?" in texto:
        return memoria["corrige"].pop(0)
    # el agente no entendió y ofrece opciones: quien venía a agendar toca la de agendar, una sola vez
    for opcion in ("duda:reservar", "menu:reservar"):
        if opcion in botones and "srv" in guion.sabe and "opcion" not in memoria["usadas"]:
            memoria["usadas"].add("opcion")
            return "#" + opcion
    return None


def correr(guion, rep, ver=False):
    agenda = AgendaFalsa(AHORA)
    for cita in guion.agenda:
        agenda.agendar(*cita)
    perfiles = Perfiles()
    conocido = next((c["nombre"] for c in agenda.clientes() if c["id"] == guion.cliente), "")
    perfiles.de(YO).update(acepta=True, cliente_id=guion.cliente, nombre=conocido)
    agente = Agente(agenda, entender, perfiles)

    mensaje, dicho, tiempos = guion.abre[rep % len(guion.abre)], [], []
    memoria = {"corrige": list(guion.corrige), "usadas": set(), "repitio": False}
    while mensaje is not None and len(tiempos) < MAXIMO:
        inicio = time.perf_counter()
        if mensaje.startswith("#"):
            respuestas = agente.boton(YO, NOMBRE, mensaje[1:], AHORA)
        elif mensaje.startswith("@"):
            respuestas = agente.contacto(YO, NOMBRE, mensaje[1:], AHORA)
        else:
            respuestas = agente.texto(YO, NOMBRE, mensaje, AHORA)
        tiempos.append(time.perf_counter() - inicio)
        dicho += [r.texto for r in respuestas]
        if ver:
            print(f"\nCLIENTE  {mensaje}")
            for r in respuestas:
                print("AGENTE   " + r.texto.replace("\n", "\n         "))
                if r.botones:
                    print("         " + " ".join(f"[{t}]" for fila in r.botones for t, _ in fila))
        mensaje = siguiente(guion, rep, respuestas[-1], memoria)

    final = sorted((c["clienteId"], c["servicioId"], c["barberoId"], c["fechaHora"][:16], c["estado"]) for c in agenda.citas())
    esperada = sorted(guion.queda)
    return {"exito": final == esperada and (not guion.dice or any(guion.dice in d for d in dicho)),
            "erroneas": len([c for c in final if c not in esperada]),     # citas creadas, movidas o canceladas por error
            "mensajes": len(tiempos), "tiempos": tiempos, "final": final, "esperada": esperada}


def main():
    por_tipo, fallas, tiempos = defaultdict(list), [], []
    for guion in GUIONES:
        corridas = [correr(guion, rep) for rep in range(REPETICIONES)]
        por_tipo[guion.tipo].append(corridas)
        tiempos += [t for c in corridas for t in c["tiempos"]]
        fallas += [(guion, rep, c) for rep, c in enumerate(corridas) if not c["exito"]]

    lineas = ["| Tipo de guion | Guiones | Conversaciones | Éxito | Guiones con 5 de 5 | Mensajes del cliente |",
              "|---|---|---|---|---|---|"]
    todas = []
    for tipo, guiones in list(por_tipo.items()) + [("**Total**", None)]:
        guiones = guiones if guiones is not None else todas
        corridas = [c for g in guiones for c in g]
        lineas.append(f"| {tipo} | {len(guiones)} | {len(corridas)} | {sum(c['exito'] for c in corridas) / len(corridas):.1%} | "
                      f"{sum(all(c['exito'] for c in g) for g in guiones)} | {sum(c['mensajes'] for c in corridas) / len(corridas):.1f} |")
        todas = todas + guiones if tipo != "**Total**" else todas
    corridas = [c for g in todas for c in g]
    tiempos.sort()
    lineas += ["", f"- Citas creadas, movidas o canceladas por error: {sum(c['erroneas'] for c in corridas)} "
               f"en {len(corridas)} conversaciones.",
               f"- Tiempo del agente por mensaje: {1000 * sum(tiempos) / len(tiempos):.0f} ms en promedio, "
               f"{1000 * tiempos[int(len(tiempos) * 0.95)]:.0f} ms en el percentil 95 y {1000 * tiempos[-1]:.0f} ms el más lento."]
    if fallas:
        lineas += ["", "Conversaciones que no terminaron con la agenda esperada:", ""]
        lineas += [f"- {g.id}, repetición {rep} ({g.que}): «{g.abre[rep % len(g.abre)]}»" for g, rep, _ in fallas]
    print("\n".join(lineas))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3:
        guion = next(g for g in GUIONES if g.id == sys.argv[1])
        resultado = correr(guion, int(sys.argv[2]), ver=True)
        print(f"\nÉxito: {resultado['exito']}\nAgenda final:    {resultado['final']}\nAgenda esperada: {resultado['esperada']}")
    else:
        main()
