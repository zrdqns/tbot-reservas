"""Servidor MCP «barberia»: el catálogo, el horario y los turnos libres de la barbería, de solo lectura.

    python -m bot.servidores.barberia_mcp            contra las APIs de la barbería (API_CITAS_URL, API_CATALOGO_URL)
    python -m bot.servidores.barberia_mcp --demo     contra la agenda de prueba, sin encender las APIs

No tiene herramientas para crear, mover ni cancelar citas, ni para ver clientes: eso solo lo hace la política del
agente después de que el cliente confirma. Los turnos se calculan con las citas, pero no se dice de quién son.
"""
import os
import sys
from datetime import date, datetime

from mcp.server import MCPServer

from .. import config, fechas
from .. import formato as f
from ..barberia import buscar_barbero, buscar_servicio, turnos

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def ahora_colombia():
    """La hora de Colombia. TBOT_AHORA (AAAA-MM-DDTHH:MM) la fija, para que una evaluación se pueda repetir."""
    if os.environ.get("TBOT_AHORA"):
        return datetime.fromisoformat(os.environ["TBOT_AHORA"])
    return datetime.now(config.ZONA).replace(tzinfo=None)


def crear(api, reloj=ahora_colombia):
    """El servidor con sus herramientas, sobre un cliente de la API (o la agenda de prueba)."""
    mcp = MCPServer("barberia", instructions="Catálogo, horario y turnos libres de la barbería. Solo lectura.")

    def activos(lista):
        return [x for x in lista if x.get("activo", True)]

    @mcp.tool()
    def servicios() -> list[dict]:
        """Servicios que ofrece la barbería, con su precio en pesos colombianos y su duración en minutos."""
        return [{"nombre": s["nombre"], "descripcion": s.get("descripcion", ""), "precio": s["precio"],
                 "minutos": s["duracionMinutos"]} for s in activos(api.servicios())]

    @mcp.tool()
    def barberos() -> list[dict]:
        """Barberos que están atendiendo, con su especialidad."""
        return [{"nombre": b["nombre"], "especialidad": b.get("especialidad", "")} for b in activos(api.barberos())]

    @mcp.tool()
    def horario() -> dict:
        """Horario de atención de cada día de la semana."""
        if hasattr(api, "leer_horario"):
            api.leer_horario()
        return {dia: (f"{config.HORARIO[i][0]:%H:%M}-{config.HORARIO[i][1]:%H:%M}" if i in config.HORARIO else "cerrado")
                for i, dia in enumerate(DIAS)}

    @mcp.tool()
    def turnos_libres(fecha: str, servicio: str = "", barbero: str = "") -> dict:
        """Turnos libres de un día: las horas en que cada barbero puede atender.

        fecha: el día, en formato AAAA-MM-DD o tal como lo dijo el cliente («mañana», «el viernes», «el 16»).
        servicio: opcional, el servicio que quiere; cambia la duración del turno.
        barbero: opcional, el nombre del barbero; deja solo sus turnos.
        """
        cuando = reloj()
        try:
            dia = date.fromisoformat(fecha.strip())
        except ValueError:
            leida = fechas.fecha(fecha, cuando.date())        # las mismas reglas del agente: el LLM no calcula fechas
            if leida is None or leida.dia is None:
                return {"error": "No reconozco esa fecha; usa AAAA-MM-DD o algo como «mañana» o «el viernes»."}
            dia = leida.dia
        lista = activos(api.barberos())
        elegido = buscar_barbero(barbero, lista) if barbero.strip() else None
        if isinstance(elegido, dict):
            lista = [elegido]
        srv = buscar_servicio(servicio, activos(api.servicios())) if servicio.strip() else None
        duracion = srv["duracionMinutos"] if srv else 30
        libres = turnos(dia, duracion, lista, api.citas(), cuando)
        por_barbero = {}
        for t, quienes in libres.items():
            for b in quienes:
                por_barbero.setdefault(f.pila(b["nombre"]), []).append(f"{t:%H:%M}")
        salida = {"fecha": dia.isoformat(), "dia": DIAS[dia.weekday()], "servicio": srv["nombre"] if srv else None,
                  "turnos_por_barbero": por_barbero}
        if dia.weekday() not in config.HORARIO:
            salida["nota"] = "Ese día la barbería no atiende."
        elif dia < cuando.date():
            salida["nota"] = "Ese día ya pasó."
        elif not libres:
            salida["nota"] = "No quedan turnos libres ese día."
        if barbero.strip() and not isinstance(elegido, dict):
            salida["nota_barbero"] = f"No hay un barbero llamado «{barbero}»; se muestran todos."
        return salida

    return mcp


if __name__ == "__main__":
    if "--demo" in sys.argv:
        from ..tests.agenda_falsa import AgendaFalsa
        crear(AgendaFalsa(ahora_colombia())).run()
    else:
        from ..barberia import Barberia
        crear(Barberia()).run()
