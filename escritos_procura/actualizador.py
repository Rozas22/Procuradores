"""Buscar e instalar actualizaciones desde las publicaciones (releases) de GitHub.

La app pregunta a GitHub cuál es la última versión publicada. Si es más nueva,
descarga el instalador y lo ejecuta en modo silencioso: se instala encima de la
versión actual (mismo AppId de Inno Setup), sin desinstalar, conservando los
ajustes y la lista de escritos, y vuelve a abrir la app.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

# Repositorio público donde se publican los instaladores.
REPO_PUBLICACIONES = os.environ.get("ESCRITOS_PROCURA_REPO", "Rozas22/Procuradores")
TIEMPO_ESPERA = 10


@dataclass
class Novedad:
    version: str
    url_instalador: str
    notas: str
    tamano: int = 0


def version_tupla(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums[:3]) or (0,)


def es_mas_nueva(remota: str, local: str = __version__) -> bool:
    return version_tupla(remota) > version_tupla(local)


def buscar(repo: str = REPO_PUBLICACIONES) -> Novedad | None:
    """Devuelve la novedad si hay una versión más nueva; None si estás al día.
    Lanza OSError/ValueError si no se puede consultar."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "EscritosProcura"},
    )
    with urllib.request.urlopen(req, timeout=TIEMPO_ESPERA) as r:
        datos = json.load(r)
    version = str(datos.get("tag_name", "")).lstrip("vV")
    if not version or not es_mas_nueva(version):
        return None
    for a in datos.get("assets", []):
        nombre = a.get("name", "")
        if nombre.lower().endswith(".exe") and "instalador" in nombre.lower():
            return Novedad(version, a["browser_download_url"], datos.get("body") or "", int(a.get("size") or 0))
    return None


def descargar(n: Novedad, progreso=None) -> Path:
    destino = Path(tempfile.gettempdir()) / f"EscritosProcura-Instalador-{n.version}.exe"
    req = urllib.request.Request(n.url_instalador, headers={"User-Agent": "EscritosProcura"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino.with_suffix(".part"), "wb") as f:
        total = int(r.headers.get("Content-Length") or n.tamano or 0)
        hecho = 0
        while True:
            trozo = r.read(256 * 1024)
            if not trozo:
                break
            f.write(trozo)
            hecho += len(trozo)
            if progreso:
                progreso(hecho, total)
    if destino.exists():
        destino.unlink()
    destino.with_suffix(".part").rename(destino)
    return destino


def puede_instalar() -> bool:
    """Solo la app instalada (el .exe) puede actualizarse a sí misma."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def lanzar_instalador(ruta: Path):
    """Ejecuta el instalador en silencio. La app debe cerrarse justo después."""
    subprocess.Popen(
        [str(ruta), "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NOCANCEL", "/CLOSEAPPLICATIONS"],
        close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
