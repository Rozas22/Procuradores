"""Ajustes del usuario en %APPDATA%\\PresentadorAvantius\\ajustes.json (en Linux/Mac, ~/.presentador-avantius).

Claves usadas en la iteración 1:
    certificado_huella    huella del certificado de Windows elegido
    reemplazar_original   true = el firmado sustituye al original; false = «… firmado.pdf»
    sello                 {ancho, alto, desplazamiento_x, desplazamiento_y, x_fijo, y_fijo, tamano_letra, fuente}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

POR_DEFECTO = {
    "certificado_huella": "",
    "reemplazar_original": False,
    "carpeta_base": "",
    "sello": {},
}


def carpeta_datos() -> Path:
    base = os.environ.get("APPDATA")
    d = Path(base) / "PresentadorAvantius" if base else Path.home() / ".presentador-avantius"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta_ajustes() -> Path:
    return carpeta_datos() / "ajustes.json"


def cargar_ajustes() -> dict:
    datos = dict(POR_DEFECTO)
    r = ruta_ajustes()
    if r.is_file():
        datos.update(json.loads(r.read_text(encoding="utf-8")))
    return datos


def guardar_ajustes(datos: dict) -> None:
    ruta_ajustes().write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
