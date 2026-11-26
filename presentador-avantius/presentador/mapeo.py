"""Mapeo del título del escrito a la opción del desplegable «Tipo de Escrito*» de Avantius.

Las reglas viven en ``config/mapeo_escritos.json`` (editable a mano o, en la iteración 3,
desde la pestaña «Configuración y Reglas"). Cada regla tiene una lista ``contiene`` con
palabras clave: se aplica si TODAS aparecen en el título (sin importar tildes ni
mayúsculas). Gana la primera regla que cumpla; si ninguna cumple, se usa ``por_defecto``
y se marca un aviso.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .parser import normalizar

RUTA_POR_DEFECTO = Path(__file__).resolve().parents[1] / "config" / "mapeo_escritos.json"


@dataclass
class ResultadoMapeo:
    tipo_escrito: str
    por_defecto: bool          # True = ninguna regla ha coincidido: revisar
    regla: dict | None = None

    @property
    def aviso(self) -> str:
        if not self.por_defecto:
            return ""
        return f"Ninguna regla coincide con el título: se usará «{self.tipo_escrito}». Revísalo."


def cargar_mapeo(ruta: str | Path | None = None) -> dict:
    ruta = Path(ruta) if ruta else RUTA_POR_DEFECTO
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos.setdefault("por_defecto", "Escrito de trámite")
    datos.setdefault("reglas", [])
    for i, regla in enumerate(datos["reglas"]):
        if not regla.get("tipo_escrito") or not regla.get("contiene"):
            raise ValueError(f"La regla {i + 1} de {ruta.name} necesita «contiene» y «tipo_escrito».")
        if isinstance(regla["contiene"], str):
            regla["contiene"] = [regla["contiene"]]
    return datos


def guardar_mapeo(datos: dict, ruta: str | Path | None = None) -> None:
    ruta = Path(ruta) if ruta else RUTA_POR_DEFECTO
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mapear_tipo_escrito(titulo: str, mapeo: dict | None = None) -> ResultadoMapeo:
    mapeo = mapeo if mapeo is not None else cargar_mapeo()
    t = normalizar(titulo)
    for regla in mapeo["reglas"]:
        if all(normalizar(p) in t for p in regla["contiene"]):
            return ResultadoMapeo(regla["tipo_escrito"], False, regla)
    return ResultadoMapeo(mapeo["por_defecto"], True, None)
