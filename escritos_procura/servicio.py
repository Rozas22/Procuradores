"""Une el motor y el almacén: importar una entrada y refrescar estados."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .almacen import Ajustes, Almacen, Escrito
from .motor import (Datos, Entrada, analizar, escribir_ficha, estado_en_carpeta,
                    guardar_adjuntos, nombre_carpeta)


class YaImportado(Exception):
    def __init__(self, escrito: Escrito):
        super().__init__("Este escrito ya estaba en la lista.")
        self.escrito = escrito


def importar(entrada: Entrada, datos: Datos, principal_nombre: str | None,
             ajustes: Ajustes, almacen: Almacen) -> Escrito:
    """Archiva una entrada ya analizada (y quizá corregida por el usuario)."""
    previo = almacen.existe(entrada.clave)
    if previo:
        raise YaImportado(previo)
    if not ajustes.carpeta_escritos:
        raise ValueError("Falta elegir la carpeta de escritos en Ajustes.")
    nombre = nombre_carpeta(datos, ajustes.formato_carpeta)
    if not nombre:
        raise ValueError("Falta el número y el año del procedimiento.")
    destino = Path(ajustes.carpeta_escritos) / nombre

    principal = next((a for a in entrada.adjuntos if a.nombre == principal_nombre), None)
    orden = ([principal] if principal else []) + [a for a in entrada.adjuntos if a is not principal]
    finales = guardar_adjuntos(destino, orden)
    principal_final = finales[0] if principal else ""
    anexos = finales[1:] if principal else finales

    ahora = dt.datetime.now()
    if ajustes.escribir_ficha:
        escribir_ficha(destino, datos, principal_final, anexos, entrada.origen, ahora.strftime("%d-%m-%y %H.%M"))

    e = Escrito(
        recibido=ahora.isoformat(timespec="seconds"),
        tipo_escrito=datos.tipo_escrito, procedimiento=datos.procedimiento,
        organo=datos.organo, plaza=datos.plaza, demandante=datos.demandante,
        demandado=datos.demandado, carpeta=str(destino), principal=principal_final,
        anexos=anexos, avisos=[a for a in datos.avisos if not a.startswith("No se ha")],
        origen=entrada.origen, clave=entrada.clave,
    )
    return almacen.guardar(e)


def refrescar_estados(almacen: Almacen) -> int:
    """Actualiza el estado mirando la carpeta (firmado / resguardo). Devuelve cuántos cambiaron."""
    cambios = 0
    for e in almacen.todos():
        if e.estado_manual or e.estado == "Presentado":
            continue
        nuevo = estado_en_carpeta(Path(e.carpeta), e.recibido_ts, e.principal) or "Pendiente de firmar"
        if nuevo != e.estado:
            e.estado = nuevo
            almacen.guardar(e)
            cambios += 1
    return cambios


__all__ = ["importar", "refrescar_estados", "YaImportado", "analizar"]
