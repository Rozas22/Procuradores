"""Firma de PDFs con el certificado instalado en Windows, usando AutoFirma.

La app nunca toca la clave privada: llama a AutoFirma (la aplicación gratuita
del Gobierno), que usa el almacén de certificados de Windows. La firma se añade
como una revisión nueva del PDF, así que la del abogado sigue siendo válida.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

URL_AUTOFIRMA = "https://firmaelectronica.gob.es/Home/Descargas.html"
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Certificado:
    nombre: str        # CN, p. ej. "ORTEGA GONZALEZ MARIA DEL MAR - 11908401J"
    emisor: str
    caduca: str
    huella: str

    @property
    def texto(self) -> str:
        return f"{self.nombre}  (emisor {self.emisor}, caduca {self.caduca})"


def buscar_autofirma() -> str | None:
    bases = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA")]
    for base in filter(None, bases):
        for sub in ("AutoFirma/AutoFirma", "Autofirma/Autofirma", "AutoFirma", "Autofirma",
                    "Programs/AutoFirma/AutoFirma"):
            for exe in ("AutofirmaCommandLine.exe", "AutoFirmaCommandLine.exe"):
                ruta = Path(base) / sub / exe
                if ruta.is_file():
                    return str(ruta)
    for exe in ("AutofirmaCommandLine", "AutoFirmaCommandLine", "autofirma"):
        r = shutil.which(exe)
        if r:
            return r
    return None


def listar_certificados() -> list[Certificado]:
    """Certificados personales de Windows con clave privada y vigentes."""
    if sys.platform != "win32":
        return []
    ps = (
        "Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) } | "
        "ForEach-Object { [PSCustomObject]@{ nombre=$_.GetNameInfo('SimpleName',$false); "
        "emisor=$_.GetNameInfo('SimpleName',$true); caduca=$_.NotAfter.ToString('dd/MM/yyyy'); huella=$_.Thumbprint } } | "
        "ConvertTo-Json -Compress"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=30, creationflags=SIN_VENTANA)
    salida = (r.stdout or "").strip()
    if not salida:
        return []
    datos = json.loads(salida)
    if isinstance(datos, dict):
        datos = [datos]
    return [Certificado(d.get("nombre", ""), d.get("emisor", ""), d.get("caduca", ""), d.get("huella", ""))
            for d in datos]


def posicion_firma(ruta_pdf: Path) -> tuple[int, tuple[float, float, float, float], bool]:
    """(página 1-based, rectángulo x0,y0,x1,y1, ¿junto a otra firma?) para la firma visible.
    Si hay una firma (la del abogado) en la última página firmada, se pone a su derecha;
    si no cabe, debajo. Si no hay ninguna, abajo a la derecha de la última página."""
    from pypdf import PdfReader
    r = PdfReader(str(ruta_pdf))
    n = len(r.pages)
    for idx in range(n - 1, -1, -1):
        pagina = r.pages[idx]
        ancho = float(pagina.mediabox.width)
        for a in pagina.get("/Annots") or []:
            a = a.get_object()
            ft = a.get("/FT") or (a.get("/Parent").get_object().get("/FT") if a.get("/Parent") else None)
            if a.get("/Subtype") != "/Widget" or ft != "/Sig":
                continue
            x0, y0, x1, y1 = (float(v) for v in a["/Rect"])
            if x1 - x0 < 5:  # firma invisible
                continue
            w, h = x1 - x0, y1 - y0
            nx0 = x1 + 15
            if nx0 + w <= ancho - 20:
                return idx + 1, (nx0, y0, nx0 + w, y1), True
            ny1 = y0 - 10
            return idx + 1, (x0, max(20, ny1 - h), x1, max(20 + h, ny1)), True
    pagina = r.pages[-1]
    ancho = float(pagina.mediabox.width)
    return n, (ancho - 260, 60, ancho - 60, 110), False


def configuracion(pagina: int, rect, separador: str = "\n") -> str:
    """Propiedades de AutoFirma para la firma visible. Según la versión, AutoFirma
    separa las propiedades con un salto de línea real o con el texto «\\n»."""
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    props = {
        "signaturePage": pagina,
        "signaturePositionOnPageLowerLeftX": x0,
        "signaturePositionOnPageLowerLeftY": y0,
        "signaturePositionOnPageUpperRightX": x1,
        "signaturePositionOnPageUpperRightY": y1,
        "layer2Text": "Firmado digitalmente por $$SUBJECTCN$$ Fecha: $$SIGNDATE=yyyy.MM.dd HH:mm:ss$$",
        "layer2FontSize": 7,
        "layer2FontFamily": 1,
        "layer2FontColor": "black",
        "alwaysCreateRevision": "true",
    }
    return separador.join(f"{k}={v}" for k, v in props.items())


def firmas(ruta_pdf: Path) -> list[dict]:
    """Firmas del PDF: nombre del campo, página, ¿visible?, ¿tiene valor (firmada)?"""
    from pypdf import PdfReader
    r = PdfReader(str(ruta_pdf))
    res = []
    for n, pagina in enumerate(r.pages, 1):
        for a in pagina.get("/Annots") or []:
            a = a.get_object()
            campo = a.get("/Parent").get_object() if a.get("/Parent") else a
            if a.get("/Subtype") != "/Widget" or (campo.get("/FT") or a.get("/FT")) != "/Sig":
                continue
            x0, y0, x1, y1 = (float(v) for v in a.get("/Rect", [0, 0, 0, 0]))
            res.append({"nombre": str(campo.get("/T") or a.get("/T") or ""), "pagina": n,
                        "visible": (x1 - x0) > 5 and (y1 - y0) > 5,
                        "firmada": (campo.get("/V") or a.get("/V")) is not None})
    return res


def _copia_seguridad(ruta: Path) -> Path:
    import datetime as dt
    from .almacen import carpeta_datos
    d = carpeta_datos() / "originales_sin_firmar" / dt.datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    destino = d / ruta.name
    i = 2
    while destino.exists():
        destino = d / f"{ruta.stem} ({i}){ruta.suffix}"
        i += 1
    shutil.copy2(ruta, destino)
    return destino


def firmar(ruta_pdf: Path, cert: Certificado | None, autofirma: str | None = None,
           elegir_en_autofirma: bool = False) -> Path:
    """Firma el PDF con AutoFirma y SUSTITUYE el original por el firmado, solo si se
    comprueba que el nuevo lleva una firma más y visible. El original sin firmar se
    guarda aparte (carpeta de datos de la app) por seguridad. Lanza RuntimeError si falla."""
    exe = autofirma or buscar_autofirma()
    if not exe:
        raise RuntimeError("No encuentro AutoFirma en este ordenador.")
    pagina, rect, _ = posicion_firma(ruta_pdf)
    antes = firmas(ruta_pdf)
    nombres_antes = {f["nombre"] for f in antes}
    temporal = ruta_pdf.with_name(f"~firmando {ruta_pdf.name}")
    ultimo_error = ""
    for separador in ("\n", "\\n"):
        temporal.unlink(missing_ok=True)
        args = [exe, "sign", "-i", str(ruta_pdf), "-o", str(temporal), "-format", "pades",
                "-store", "windows", "-config", configuracion(pagina, rect, separador)]
        if elegir_en_autofirma or cert is None:
            args.append("-certgui")
        else:
            args += ["-filter", f"subject.contains:{cert.nombre}"]
        r = subprocess.run(args, capture_output=True, text=True, timeout=300, creationflags=SIN_VENTANA)
        salida = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if not temporal.is_file():
            ultimo_error = salida.splitlines()[-1][:300] if salida else f"AutoFirma terminó con código {r.returncode}"
            break  # no es cosa de la posición: no reintentar
        try:
            despues = firmas(temporal)
        except Exception as ex:
            ultimo_error = f"el PDF firmado no se puede leer ({ex})"
            continue
        nuevas = [f for f in despues if f["firmada"] and f["nombre"] not in nombres_antes]
        if not nuevas:
            ultimo_error = "AutoFirma no ha añadido ninguna firma al PDF"
            continue
        if not any(f["visible"] for f in nuevas):
            ultimo_error = "AutoFirma ha firmado, pero la firma no ha quedado visible en el documento"
            continue
        _copia_seguridad(ruta_pdf)
        os.replace(temporal, ruta_pdf)
        return ruta_pdf
    temporal.unlink(missing_ok=True)
    raise RuntimeError(ultimo_error or "no se ha podido firmar")
