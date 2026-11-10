"""Cliente MCP del agente: conecta los servidores «barberia» y «calendario» y se los ofrece al LLM como herramientas.

Cada servidor es un proceso aparte que habla MCP por stdio. Las conexiones se abren una vez, en un hilo con su propio
bucle de asyncio, y se quedan abiertas: el agente las usa desde su hilo con `llamar`, que espera la respuesta.
Si un servidor no arranca, el LLM trabaja sin herramientas y el agente sigue igual.
"""
import asyncio
import json
import logging
import os
import sys
import threading
from contextlib import AsyncExitStack

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.types import TextContent

from . import config

SERVIDORES = {"barberia": "bot.servidores.barberia_mcp", "calendario": "bot.servidores.calendario_mcp"}
VARIABLES = ("API_CITAS_URL", "API_CATALOGO_URL", "TBOT_AHORA")      # lo que los servidores necesitan del entorno
SEPARADOR = "__"                                                     # barberia__servicios

log = logging.getLogger(__name__)


def por_stdio(modulo, *argumentos):
    """Cómo lanzar un servidor del proyecto como proceso aparte."""
    entorno = get_default_environment() | {v: os.environ[v] for v in VARIABLES if os.environ.get(v)}
    return StdioServerParameters(command=sys.executable, args=["-m", modulo, *argumentos], cwd=str(config.RAIZ),
                                 env=entorno)


class Herramientas:
    def __init__(self, destinos=None, demo=False):
        """destinos: {nombre: a qué conectarse}. Por omisión, los dos servidores del proyecto por stdio; con demo, la
        barbería lee la agenda de prueba en vez de las APIs. En las pruebas, los objetos servidor directamente."""
        self.destinos = destinos or {nombre: por_stdio(modulo, *(["--demo"] if demo and nombre == "barberia" else []))
                                     for nombre, modulo in SERVIDORES.items()}
        self.clientes, self.lista, self.error = {}, [], None
        self._bucle = self._fin = None
        self._listo = threading.Event()

    # ---------- ciclo de vida ----------
    def iniciar(self, espera=30):
        """Abre las conexiones. Devuelve True si todos los servidores respondieron."""
        threading.Thread(target=lambda: asyncio.run(self._vivir()), daemon=True, name="mcp").start()
        self._listo.wait(espera)
        if self.error or not self.clientes:
            log.warning("Herramientas MCP no disponibles: %s", self.error or "no respondieron a tiempo")
            return False
        log.info("Herramientas MCP: %s", ", ".join(h["function"]["name"] for h in self.lista))
        return True

    async def _vivir(self):
        self._bucle, self._fin = asyncio.get_running_loop(), asyncio.Event()
        try:
            async with AsyncExitStack() as pila:
                for nombre, destino in self.destinos.items():
                    cliente = await pila.enter_async_context(Client(destino))
                    self.clientes[nombre] = cliente
                    for h in (await cliente.list_tools()).tools:
                        self.lista.append({"type": "function", "function": {
                            "name": nombre + SEPARADOR + h.name, "description": f"[{nombre}] {h.description or ''}".strip(),
                            "parameters": h.input_schema or {"type": "object", "properties": {}}}})
                self._listo.set()
                await self._fin.wait()
        except Exception as error:                  # un servidor que no arranca no tumba al agente
            self.error = f"{type(error).__name__}: {error}"
            self.clientes.clear()
            self.lista.clear()
        finally:
            self._listo.set()

    def cerrar(self):
        if self._bucle and self._fin:
            self._bucle.call_soon_threadsafe(self._fin.set)

    # ---------- uso ----------
    @property
    def disponibles(self):
        return bool(self.clientes)

    def llamar(self, nombre, argumentos, espera=10):
        """Ejecuta una herramienta y devuelve su resultado como texto para el LLM (nunca lanza excepciones)."""
        servidor, _, herramienta = nombre.partition(SEPARADOR)
        cliente = self.clientes.get(servidor)
        if not cliente or not herramienta:
            return json.dumps({"error": f"No existe la herramienta {nombre}."}, ensure_ascii=False)
        esquema = next((h["function"]["parameters"] for h in self.lista if h["function"]["name"] == nombre), {})
        validos = esquema.get("properties", {})
        argumentos = {k: v for k, v in (argumentos or {}).items() if k in validos}     # el LLM a veces manda basura
        try:
            futuro = asyncio.run_coroutine_threadsafe(cliente.call_tool(herramienta, argumentos), self._bucle)
            resultado = futuro.result(espera)
        except Exception as error:
            return json.dumps({"error": f"La herramienta no respondió ({type(error).__name__})."}, ensure_ascii=False)
        if resultado.structured_content is not None:
            datos = resultado.structured_content
            return json.dumps(datos.get("result", datos) if set(datos) == {"result"} else datos, ensure_ascii=False)
        texto = "\n".join(b.text for b in resultado.content if isinstance(b, TextContent))
        if resultado.is_error:
            return json.dumps({"error": texto}, ensure_ascii=False)
        try:
            return json.dumps(json.loads(texto), ensure_ascii=False)     # compacto: menos tokens para el LLM
        except ValueError:
            return texto
