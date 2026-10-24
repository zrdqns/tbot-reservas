"""Perfil de cada cliente: lo único que el agente guarda de una conversación a otra.

Tiene el nombre, la cuenta de Telegram, el cliente al que corresponde en el sistema de la barbería y qué
barbero y servicio pide más. El documento y el teléfono no se guardan aquí: pasan directo a la API.
"""
import json
from pathlib import Path


class Perfiles:
    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else None
        self.datos = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta and self.ruta.exists() else {}

    def de(self, uid):
        return self.datos.setdefault(str(uid), {"acepta": False, "nombre": "", "cliente_id": None,
                                                "barberos": {}, "servicios": {}, "recordadas": []})

    def todos(self):
        return list(self.datos.items())

    def borrar(self, uid):
        self.datos.pop(str(uid), None)
        self.guardar()

    def guardar(self):
        if self.ruta:
            self.ruta.parent.mkdir(exist_ok=True)
            self.ruta.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1), encoding="utf-8")
