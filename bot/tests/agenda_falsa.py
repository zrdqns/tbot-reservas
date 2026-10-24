"""Agenda en memoria con las mismas reglas y los mismos datos de demostración que la API de la barbería.

Permite probar al agente sin encender los microservicios. Lo que importa en cada prueba es cómo queda
`citas` al final de la conversación.
"""
from datetime import datetime, timedelta

from bot.barberia import ErrorAPI, inicio


class AgendaFalsa:
    def __init__(self, ahora):
        self.ahora = ahora
        self._servicios = [
            {"id": 1, "nombre": "Corte clásico", "descripcion": "Corte a tijera o máquina con lavado", "precio": 25000, "duracionMinutos": 30, "activo": True},
            {"id": 2, "nombre": "Arreglo de barba", "descripcion": "Perfilado y afeitado con navaja", "precio": 18000, "duracionMinutos": 20, "activo": True},
            {"id": 3, "nombre": "Corte y barba", "descripcion": "Corte clásico más arreglo de barba", "precio": 38000, "duracionMinutos": 50, "activo": True},
            {"id": 4, "nombre": "Tinte", "descripcion": "Aplicación de color completo", "precio": 60000, "duracionMinutos": 90, "activo": False},
        ]
        self._barberos = [
            {"id": 1, "nombre": "Andrés Rojas", "documento": "1012345678", "telefono": "3104567890", "especialidad": "Cortes clásicos", "activo": True},
            {"id": 2, "nombre": "Julián Mora", "documento": "1023456789", "telefono": "3115678901", "especialidad": "Barba y afeitado", "activo": True},
            {"id": 3, "nombre": "Felipe Cárdenas", "documento": "1034567890", "telefono": "3126789012", "especialidad": "Degradados", "activo": False},
        ]
        self._clientes = [
            {"id": 1, "nombre": "Carlos Ramírez", "documento": "1098765432", "telefono": "3001234567", "correo": ""},
            {"id": 2, "nombre": "Mateo Herrera", "documento": "1087654321", "telefono": "3012345678", "correo": ""},
        ]
        self._citas = []
        self.escrituras = 0          # veces que alguien creó, movió o canceló una cita

    def servicios(self):
        return self._servicios

    def barberos(self):
        return self._barberos

    def clientes(self):
        return self._clientes

    def citas(self):
        return self._citas

    def crear_cliente(self, nombre, documento, telefono):
        if any(c["documento"] == documento for c in self._clientes):
            raise ErrorAPI(409, f"Ya existe un cliente con el documento {documento}.")
        cliente = {"id": len(self._clientes) + 1, "nombre": nombre, "documento": documento, "telefono": telefono, "correo": ""}
        self._clientes.append(cliente)
        return cliente

    def crear_cita(self, cliente_id, servicio_id, barbero_id, cuando, observaciones=""):
        cita = {"id": len(self._citas) + 1, "estado": "PROGRAMADA"}
        self._asignar(cita, cliente_id, servicio_id, barbero_id, cuando, observaciones)
        self._citas.append(cita)
        return cita

    def mover_cita(self, cita_id, cliente_id, servicio_id, barbero_id, cuando, observaciones=""):
        cita = next(c for c in self._citas if c["id"] == cita_id)
        if cita["estado"] != "PROGRAMADA":
            raise ErrorAPI(409, "Solo se pueden modificar las citas programadas.")
        self._asignar(cita, cliente_id, servicio_id, barbero_id, cuando, observaciones)
        return cita

    def cancelar_cita(self, cita_id):
        cita = next(c for c in self._citas if c["id"] == cita_id)
        if cita["estado"] != "PROGRAMADA":
            raise ErrorAPI(409, "La cita ya está cancelada y no puede cambiar de estado.")
        cita["estado"] = "CANCELADA"
        self.escrituras += 1
        return cita

    def _asignar(self, cita, cliente_id, servicio_id, barbero_id, cuando, observaciones):
        cliente = next((c for c in self._clientes if c["id"] == cliente_id), None)
        if cliente is None:
            raise ErrorAPI(404, f"No se encontró un cliente con el ID {cliente_id}.")
        servicio = next(s for s in self._servicios if s["id"] == servicio_id)
        barbero = next(b for b in self._barberos if b["id"] == barbero_id)
        if cuando < self.ahora:
            raise ErrorAPI(400, "La cita no puede agendarse en una fecha pasada.")
        if not servicio["activo"] or not barbero["activo"]:
            raise ErrorAPI(409, "El servicio o el barbero no está activo.")
        fin = cuando + timedelta(minutes=servicio["duracionMinutos"])
        for otra in self._citas:
            if otra["id"] != cita["id"] and otra["estado"] == "PROGRAMADA" and otra["barberoId"] == barbero_id \
                    and cuando < inicio(otra) + timedelta(minutes=otra["duracionMinutos"]) and inicio(otra) < fin:
                raise ErrorAPI(409, f"El barbero {barbero['nombre']} ya tiene una cita de {inicio(otra):%H:%M}.")
        cita.update(fechaHora=cuando.strftime("%Y-%m-%dT%H:%M:%S"), observaciones=observaciones,
                    clienteId=cliente_id, clienteNombre=cliente["nombre"], servicioId=servicio_id,
                    servicioNombre=servicio["nombre"], precio=servicio["precio"],
                    duracionMinutos=servicio["duracionMinutos"], barberoId=barbero_id, barberoNombre=barbero["nombre"])
        self.escrituras += 1

    def agendar(self, cliente_id, servicio_id, barbero_id, texto):
        """Deja una cita ya puesta antes de empezar la conversación."""
        cita = self.crear_cita(cliente_id, servicio_id, barbero_id, datetime.fromisoformat(texto))
        self.escrituras = 0
        return cita
