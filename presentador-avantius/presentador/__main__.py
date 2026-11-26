"""Línea de órdenes de la iteración 1.

    python -m presentador ejemplo                       crea ejemplo/escrito_ejemplo.pdf y un .pfx de prueba
    python -m presentador extraer ESCRITO.pdf           muestra los datos que saca del PDF
    python -m presentador certificados                  lista tus certificados de Windows
    python -m presentador firmar ESCRITO.pdf --huella HUELLA     firma con un certificado de Windows
    python -m presentador firmar ESCRITO.pdf --pfx prueba.pfx --clave 1234
    python -m presentador comprobar ESCRITO_firmado.pdf  comprueba las firmas del PDF
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _imprimir(d: dict) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_extraer(a) -> int:
    from .mapeo import cargar_mapeo, mapear_tipo_escrito
    from .parser import extraer_de_pdf
    d = extraer_de_pdf(a.pdf)
    m = mapear_tipo_escrito(d.titulo, cargar_mapeo(a.mapeo))
    salida = d.como_dict()
    salida["tipo_escrito_avantius"] = m.tipo_escrito
    if m.aviso:
        salida["avisos"].append(m.aviso)
    _imprimir(salida)
    return 0 if d.completo else 1


def cmd_certificados(a) -> int:
    from .signer import listar_certificados_windows
    certs = listar_certificados_windows()
    if not certs:
        print("No hay certificados personales vigentes con clave privada en Windows.")
        return 1
    for i, c in enumerate(certs, 1):
        print(f"{i}. {c.texto}\n   huella: {c.huella}")
    return 0


def cmd_firmar(a) -> int:
    from .config import cargar_ajustes
    from .parser import extraer_de_pdf
    from .signer import AjustesSello, FirmanteWindows, firmante_pfx, firmar_pdf
    ajustes = cargar_ajustes()
    if a.pfx:
        firmante = firmante_pfx(a.pfx, a.clave or "")
    else:
        huella = a.huella or ajustes.get("certificado_huella")
        if not huella:
            print("Indica --huella (mira «python -m presentador certificados») o --pfx.")
            return 2
        firmante = FirmanteWindows(huella)
    procurador = extraer_de_pdf(a.pdf).procurador
    salida = a.salida or (a.pdf if ajustes.get("reemplazar_original") else None)
    r = firmar_pdf(a.pdf, salida, firmante, AjustesSello.desde_dict(ajustes.get("sello")), procurador)
    x0, y0, x1, y1 = r.posicion.caja
    print(f"Firmado por {r.firmante}")
    print(f"PDF firmado: {r.ruta}")
    print(f"Sello en la página {r.posicion.pagina + 1}, x={x0:.0f} y={y0:.0f} ({x1 - x0:.0f}×{y1 - y0:.0f} pt), "
          f"colocado {'bajo «Fdo.» del procurador' if r.posicion.metodo == 'fdo' else 'en la posición fija'}")
    print(f"PDF/A del original: {r.pdfa or 'no declarado'}")
    for av in r.avisos:
        print(f"AVISO: {av}")
    return 0


def cmd_comprobar(a) -> int:
    from .signer import comprobar_firma
    try:
        for f in comprobar_firma(a.pdf):
            print(f"{f['campo']}: {'intacta' if f['intacta'] else 'ROTA'} — {f['firmante']} ({f['cubre_todo']})")
    except RuntimeError as ex:
        print(f"ERROR: {ex}")
        return 1
    return 0


def cmd_ejemplo(a) -> int:
    from .ejemplo import crear_certificado_prueba, crear_pdf_ejemplo
    carpeta = Path(a.carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    pdf = crear_pdf_ejemplo(carpeta / "escrito_ejemplo.pdf")
    pfx = crear_certificado_prueba(carpeta / "certificado_prueba.pfx", "1234")
    print(f"Creado {pdf}\nCreado {pfx} (contraseña 1234, solo para pruebas)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="presentador", description="Presentador de escritos en Avantius — iteración 1")
    sub = p.add_subparsers(dest="orden", required=True)
    s = sub.add_parser("extraer", help="extrae los datos de un PDF")
    s.add_argument("pdf")
    s.add_argument("--mapeo", help="ruta a mapeo_escritos.json")
    s.set_defaults(f=cmd_extraer)
    s = sub.add_parser("certificados", help="lista los certificados de Windows")
    s.set_defaults(f=cmd_certificados)
    s = sub.add_parser("firmar", help="firma un PDF")
    s.add_argument("pdf")
    s.add_argument("--huella", help="huella del certificado de Windows")
    s.add_argument("--pfx", help="archivo .pfx/.p12 en lugar del almacén de Windows")
    s.add_argument("--clave", help="contraseña del .pfx")
    s.add_argument("--salida", help="PDF de salida (por defecto «… firmado.pdf»)")
    s.set_defaults(f=cmd_firmar)
    s = sub.add_parser("comprobar", help="comprueba las firmas de un PDF")
    s.add_argument("pdf")
    s.set_defaults(f=cmd_comprobar)
    s = sub.add_parser("ejemplo", help="crea un escrito y un certificado de prueba")
    s.add_argument("--carpeta", default="ejemplo")
    s.set_defaults(f=cmd_ejemplo)
    a = p.parse_args(argv)
    try:
        return a.f(a)
    except (RuntimeError, ValueError, FileNotFoundError) as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
