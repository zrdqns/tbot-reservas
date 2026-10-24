"""Clasificador de intención y ranuras: el modelo entrenado en Colab y exportado a modelo/modelo_tbot."""
import sys

from . import config

sys.path.append(str(config.RAIZ / "modelo"))
from entender import entender  # noqa: E402,F401
