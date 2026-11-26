"""Firma PAdES del escrito con el certificado del procurador, sin abrir Adobe ni AutoFirma.

- La firma la calcula pyHanko (PAdES B-B, ETSI.CAdES.detached, SHA-256).
- La clave privada nunca sale de Windows: para el certificado instalado en el almacén
  personal (Cert:\\CurrentUser\\My) se le pide a Windows, vía PowerShell/.NET, que firme
  el resumen. Si el certificado tiene protección o es una tarjeta, Windows pide la
  contraseña/PIN con su propia ventana.
- También se puede firmar con un archivo .pfx/.p12 (útil para pruebas).
- La firma se añade como revisión incremental: el contenido y una firma previa del
  letrado no se tocan, y el sello usa una fuente TrueType incrustada para no romper PDF/A.
- El sello visible va en la última página, en la columna izquierda (PROCURADOR), justo
  debajo de «Fdo.: [Nombre del procurador]». Si no encuentra «Fdo.», usa la posición fija
  de los ajustes.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from asn1crypto import x509 as asn1_x509
from pyhanko.sign import signers

SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------
# Ajustes de la firma visible (en puntos PDF; 1 cm ≈ 28,35 pt)
# ---------------------------------------------------------------------------


@dataclass
class AjustesSello:
    ancho: float = 170.0
    alto: float = 45.0
    desplazamiento_x: float = 0.0   # + derecha, respecto al inicio de «Fdo.»
    desplazamiento_y: float = 4.0   # + hacia abajo, separación bajo la línea «Fdo.»
    # Posición fija si no se encuentra «Fdo.» (origen abajo-izquierda, como en PDF):
    x_fijo: float = 70.0
    y_fijo: float = 80.0
    texto: str = "Firmado digitalmente por:\n%(signer)s\nFecha: %(ts)s"
    tamano_letra: int = 8
    fuente: str = ""                # .ttf; vacío = Arial en Windows / DejaVu en Linux

    @classmethod
    def desde_dict(cls, d: dict | None) -> "AjustesSello":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Posicion:
    pagina: int                                  # índice 0-based
    caja: tuple[float, float, float, float]      # x0, y0, x1, y1 (origen abajo-izquierda)
    metodo: str                                  # "fdo" o "fija"
    avisos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dónde poner el sello
# ---------------------------------------------------------------------------

_RE_FDO_PALABRA = re.compile(r"^F(do|DO|irmado)[.:]*$", re.I)


def _lineas_fdo(pagina) -> list[dict]:
    """Cada «Fdo.» de la página con su posición y el texto que le sigue en su columna."""
    palabras = pagina.extract_words(keep_blank_chars=False, use_text_flow=False)
    fdos = [w for w in palabras if _RE_FDO_PALABRA.match(w["text"]) or w["text"].lower().startswith("fdo.")]
    res = []
    for f in fdos:
        misma_linea = sorted((w for w in palabras if abs(w["top"] - f["top"]) < 3 and w["x0"] >= f["x0"]),
                             key=lambda w: w["x0"])
        texto = []
        for w in misma_linea:
            if w is not f and (_RE_FDO_PALABRA.match(w["text"]) or w["text"].lower().startswith("fdo.")):
                break  # empieza la columna de al lado
            texto.append(w["text"])
        res.append({"x0": f["x0"], "top": f["top"], "bottom": max(w["bottom"] for w in misma_linea),
                    "texto": " ".join(texto)})
    return res


def _normal(s: str) -> str:
    from .parser import normalizar
    return re.sub(r"[^A-Z0-9 ]", "", normalizar(s))


def calcular_posicion(ruta_pdf: str | Path, ajustes: AjustesSello | None = None,
                      nombre_procurador: str = "") -> Posicion:
    import pdfplumber
    aj = ajustes or AjustesSello()
    with pdfplumber.open(str(ruta_pdf)) as pdf:
        n = len(pdf.pages)
        # Normalmente es la última página; si allí no hay «Fdo.» (p. ej. anexos), se busca hacia atrás.
        for idx in range(n - 1, max(-1, n - 4), -1):
            pagina = pdf.pages[idx]
            fdos = _lineas_fdo(pagina)
            if not fdos:
                continue
            x_min, y_min, x_max, y_max = (float(v) for v in pagina.bbox)  # pdfplumber: top-left
            alto_pag = float(pagina.height)
            elegido = None
            if nombre_procurador:
                clave = _normal(nombre_procurador)
                elegido = next((f for f in fdos if clave and clave[:15] in _normal(f["texto"])), None)
            if elegido is None:
                # Columna izquierda = PROCURADOR. Entre las de la línea más baja, la de más a la izquierda.
                ultima = max(f["top"] for f in fdos)
                elegido = min((f for f in fdos if abs(f["top"] - ultima) < 30), key=lambda f: f["x0"])
            avisos = [] if idx == n - 1 else [f"«Fdo.» no está en la última página; firmo en la página {idx + 1}."]
            # No invadir la columna del letrado.
            vecinos = [f["x0"] for f in fdos if f["x0"] > elegido["x0"] + 20 and abs(f["top"] - elegido["top"]) < 30]
            x0 = elegido["x0"] + aj.desplazamiento_x
            ancho = aj.ancho
            if vecinos:
                ancho = min(ancho, min(vecinos) - x0 - 8)
            # Coordenadas PDF (origen abajo): justo debajo de la línea «Fdo.»
            y1 = alto_pag - (elegido["bottom"] + aj.desplazamiento_y)
            y0 = y1 - aj.alto
            if y0 < 10:  # no cabe debajo: encima de «Fdo.»
                y0 = alto_pag - elegido["top"] + 4
                y1 = y0 + aj.alto
                avisos.append("No cabe debajo de «Fdo.»: el sello va justo encima.")
            off_x, off_y = float(pagina.mediabox[0]), float(pagina.mediabox[1])
            caja = (x0 + off_x, y0 + off_y, x0 + max(ancho, 60) + off_x, y1 + off_y)
            return Posicion(idx, tuple(round(v, 1) for v in caja), "fdo", avisos)
        caja = (aj.x_fijo, aj.y_fijo, aj.x_fijo + aj.ancho, aj.y_fijo + aj.alto)
        return Posicion(n - 1, caja, "fija",
                        ["No encuentro «Fdo.:» en el PDF: uso la posición fija de los ajustes."])


# ---------------------------------------------------------------------------
# PDF/A
# ---------------------------------------------------------------------------


def info_pdfa(ruta_pdf: str | Path) -> str:
    """'PDF/A-1b', 'PDF/A-2u'... según los metadatos XMP del PDF, o '' si no declara PDF/A."""
    from pypdf import PdfReader
    r = PdfReader(str(ruta_pdf))
    meta = r.trailer["/Root"].get("/Metadata")
    if meta is None:
        return ""
    xmp = meta.get_object().get_data().decode("utf-8", "ignore")
    parte = re.search(r"pdfaid:part(?:=\"|>)\s*(\d)", xmp)
    conf = re.search(r"pdfaid:conformance(?:=\"|>)\s*([A-Za-z])", xmp)
    if not parte:
        return ""
    return f"PDF/A-{parte.group(1)}{conf.group(1).lower() if conf else ''}"


# ---------------------------------------------------------------------------
# Certificados de Windows
# ---------------------------------------------------------------------------


@dataclass
class CertificadoWindows:
    nombre: str       # CN: "ORTEGA GONZALEZ MARIA DEL MAR - 12345678Z"
    emisor: str
    caduca: str       # dd/mm/aaaa
    huella: str       # thumbprint SHA-1 en hexadecimal

    @property
    def texto(self) -> str:
        return f"{self.nombre}  (emisor {self.emisor}, caduca {self.caduca})"


def _powershell(script: str, entrada: str = "", entorno: dict | None = None, timeout: int = 120) -> str:
    if sys.platform != "win32":
        raise RuntimeError("El almacén de certificados de Windows solo está disponible en Windows.")
    env = dict(os.environ, **(entorno or {}))
    # Si la app se lanza desde PowerShell 7, PSModulePath apunta a sus módulos y Windows
    # PowerShell 5.1 no carga los suyos (Cert:, PKI). Sin la variable usa los de serie.
    env.pop("PSModulePath", None)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       input=entrada, capture_output=True, text=True, timeout=timeout, env=env,
                       creationflags=SIN_VENTANA)
    if r.returncode != 0:
        error = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError("Windows no ha podido usar el certificado: " + (error[0] if error else f"código {r.returncode}"))
    return (r.stdout or "").strip()


_PS_LISTAR = (
    "$ErrorActionPreference='Stop';"
    "@(Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) } | "
    "ForEach-Object { [PSCustomObject]@{ nombre=$_.GetNameInfo('SimpleName',$false); "
    "emisor=$_.GetNameInfo('SimpleName',$true); caduca=$_.NotAfter.ToString('dd/MM/yyyy'); huella=$_.Thumbprint } })"
    " | ConvertTo-Json -Compress"
)


def listar_certificados_windows() -> list[CertificadoWindows]:
    """Certificados personales de Windows vigentes y con clave privada."""
    salida = _powershell(_PS_LISTAR, timeout=30)
    if not salida:
        return []
    datos = json.loads(salida)
    if isinstance(datos, dict):
        datos = [datos]
    return [CertificadoWindows(d.get("nombre") or "", d.get("emisor") or "", d.get("caduca") or "",
                               d.get("huella") or "") for d in datos]


_PS_CADENA = (
    "$ErrorActionPreference='Stop';"
    "$c = Get-Item -LiteralPath ('Cert:\\CurrentUser\\My\\' + $env:HUELLA);"
    "$ch = New-Object System.Security.Cryptography.X509Certificates.X509Chain;"
    "$ch.ChainPolicy.RevocationMode = 'NoCheck'; [void]$ch.Build($c);"
    "$lista = @([Convert]::ToBase64String($c.RawData));"
    "foreach ($e in $ch.ChainElements) { if ($e.Certificate.Thumbprint -ne $c.Thumbprint) "
    "{ $lista += [Convert]::ToBase64String($e.Certificate.RawData) } };"
    "$lista -join ','"
)

_PS_FIRMAR = (
    "$ErrorActionPreference='Stop';"
    "$c = Get-Item -LiteralPath ('Cert:\\CurrentUser\\My\\' + $env:HUELLA);"
    "$datos = [Convert]::FromBase64String([Console]::In.ReadToEnd().Trim());"
    "$h = New-Object System.Security.Cryptography.HashAlgorithmName($env:RESUMEN);"
    "if ($env:ALGORITMO -eq 'rsa') {"
    "  $k = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($c);"
    "  $f = $k.SignData($datos, $h, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)"
    "} else {"
    "  $k = [System.Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPrivateKey($c);"
    "  $f = $k.SignData($datos, $h)"
    "};"
    "[Convert]::ToBase64String($f)"
)


def _p1363_a_der(firma: bytes) -> bytes:
    """ECDSA: Windows devuelve r||s; CMS necesita DER."""
    from asn1crypto.algos import DSASignature
    return DSASignature.from_p1363(firma).dump()


class FirmanteWindows(signers.Signer):
    """Firmante de pyHanko que delega la operación con la clave privada en Windows."""

    def __init__(self, huella: str, ejecutar=None):
        huella = re.sub(r"[^0-9A-Fa-f]", "", huella).upper()
        if len(huella) != 40:
            raise ValueError("La huella del certificado debe tener 40 caracteres hexadecimales.")
        self.huella = huella
        self._ejecutar = ejecutar or _powershell     # inyectable para las pruebas
        ders = [base64.b64decode(x) for x in self._ejecutar(_PS_CADENA, entorno={"HUELLA": huella}).split(",") if x]
        cert = asn1_x509.Certificate.load(ders[0])
        cadena = [asn1_x509.Certificate.load(d) for d in ders[1:]]
        from pyhanko_certvalidator.registry import SimpleCertificateStore
        self._algoritmo = cert.public_key.algorithm   # 'rsa' o 'ec'
        if self._algoritmo not in ("rsa", "ec"):
            raise RuntimeError(f"Tipo de clave no soportado: {self._algoritmo}")
        super().__init__(signing_cert=cert, cert_registry=SimpleCertificateStore.from_certs(cadena))

    async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run: bool = False) -> bytes:
        if dry_run:  # pyHanko solo quiere saber cuánto ocupa
            bits = self.signing_cert.public_key.bit_size
            return bytes(bits // 8) if self._algoritmo == "rsa" else bytes(2 * ((bits + 7) // 8) + 8)
        salida = self._ejecutar(
            _PS_FIRMAR, entrada=base64.b64encode(data).decode("ascii"),
            entorno={"HUELLA": self.huella, "RESUMEN": digest_algorithm.upper().replace("-", ""),
                     "ALGORITMO": self._algoritmo}, timeout=300)
        firma = base64.b64decode(salida.strip().splitlines()[-1])
        return firma if self._algoritmo == "rsa" else _p1363_a_der(firma)


def firmante_pfx(ruta_pfx: str | Path, clave: str) -> signers.SimpleSigner:
    s = signers.SimpleSigner.load_pkcs12(str(ruta_pfx), passphrase=clave.encode("utf-8") if clave else None)
    if s is None:
        raise RuntimeError("No se ha podido abrir el .pfx (¿contraseña incorrecta?).")
    return s


# ---------------------------------------------------------------------------
# Firmar
# ---------------------------------------------------------------------------

FUENTES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _fuente(preferida: str = "") -> str:
    """Ruta de una fuente TrueType con 1000 unidades por em. pyHanko escribe los anchos de
    los glifos en unidades de la fuente, y el PDF los interpreta sobre 1000: con Arial o
    DejaVu (2048) las letras salen separadas. Se guarda una copia reescalada en caché."""
    for f in ([preferida] if preferida else []) + FUENTES:
        if f and Path(f).is_file():
            return _fuente_1000(Path(f))
    raise RuntimeError("No encuentro una fuente TrueType para el sello (indica una en los ajustes).")


def _fuente_1000(ruta: Path) -> str:
    from fontTools.ttLib import TTFont
    fuente = TTFont(str(ruta))
    if fuente["head"].unitsPerEm == 1000:
        return str(ruta)
    from fontTools.ttLib.scaleUpem import scale_upem
    from .config import carpeta_datos
    destino = carpeta_datos() / "fuentes" / f"{ruta.stem}-1000.ttf"
    if not destino.is_file() or destino.stat().st_mtime < ruta.stat().st_mtime:
        destino.parent.mkdir(parents=True, exist_ok=True)
        scale_upem(fuente, 1000)
        temporal = destino.with_suffix(".tmp")
        fuente.save(str(temporal))
        os.replace(temporal, destino)
    return str(destino)


def _nombre_campo(ruta_pdf: Path) -> str:
    from pypdf import PdfReader
    existentes = set((PdfReader(str(ruta_pdf)).get_fields() or {}).keys())
    nombre, i = "FirmaProcurador", 2
    while nombre in existentes:
        nombre, i = f"FirmaProcurador{i}", i + 1
    return nombre


@dataclass
class ResultadoFirma:
    ruta: Path
    posicion: Posicion
    pdfa: str            # PDF/A declarado por el original ('' si ninguno)
    firmante: str
    avisos: list[str]


def firmar_pdf(entrada: str | Path, salida: str | Path | None, firmante: signers.Signer,
               ajustes: AjustesSello | None = None, nombre_procurador: str = "",
               razon: str = "Presentación telemática", lugar: str = "") -> ResultadoFirma:
    """Firma ``entrada`` y guarda el resultado en ``salida`` (por defecto «<nombre> firmado.pdf»
    junto al original). Si ``salida == entrada`` se sustituye el original de forma segura."""
    from pyhanko import stamp
    from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.text import TextBoxStyle
    from pyhanko.sign.fields import SigFieldSpec, SigSeedSubFilter

    import logging
    logging.getLogger("fontTools").setLevel(logging.ERROR)  # avisos de subconjunto de la fuente

    entrada = Path(entrada)
    salida = Path(salida) if salida else entrada.with_name(f"{entrada.stem} firmado.pdf")
    aj = ajustes or AjustesSello()
    pos = calcular_posicion(entrada, aj, nombre_procurador)
    pdfa = info_pdfa(entrada)
    avisos = list(pos.avisos)
    if not pdfa:
        avisos.append("El PDF original no declara PDF/A. Si Avantius lo rechaza, expórtalo como PDF/A antes de firmar.")

    estilo = stamp.TextStampStyle(
        stamp_text=aj.texto,
        text_box_style=TextBoxStyle(font=GlyphAccumulatorFactory(_fuente(aj.fuente), font_size=aj.tamano_letra), font_size=aj.tamano_letra),
        border_width=1, background=None, timestamp_format="%d/%m/%Y %H:%M:%S",
    )
    campo = _nombre_campo(entrada)
    meta = signers.PdfSignatureMetadata(
        field_name=campo, md_algorithm="sha256", subfilter=SigSeedSubFilter.PADES,
        reason=razon, location=lugar or None,
    )
    spec = SigFieldSpec(sig_field_name=campo, on_page=pos.pagina, box=tuple(int(round(v)) for v in pos.caja))
    pdf_signer = signers.PdfSigner(meta, signer=firmante, stamp_style=estilo, new_field_spec=spec)

    temporal = salida.with_name(f"~firmando {salida.name}")
    try:
        with entrada.open("rb") as f_in:
            escritor = IncrementalPdfFileWriter(f_in, strict=False)
            with temporal.open("wb") as f_out:
                pdf_signer.sign_pdf(escritor, output=f_out)
        comprobar_firma(temporal, campo)
        os.replace(temporal, salida)
    finally:
        temporal.unlink(missing_ok=True)

    nombre = firmante.signing_cert.subject.native.get("common_name", "") if firmante.signing_cert else ""
    return ResultadoFirma(salida, pos, pdfa, nombre, avisos)


def comprobar_firma(ruta_pdf: str | Path, campo: str | None = None) -> list[dict]:
    """Integridad de todas las firmas del PDF (sin comprobar la confianza en la CA).
    Lanza RuntimeError si alguna firma está rota o falta ``campo``."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    import logging
    res = []
    # pyHanko registra como error que el certificado no sea de una CA de confianza; aquí
    # solo interesa la integridad (la confianza la comprueba Avantius).
    registro = logging.getLogger("pyhanko")
    nivel = registro.level
    registro.setLevel(logging.CRITICAL)
    try:
        return _comprobar(ruta_pdf, campo, res)
    finally:
        registro.setLevel(nivel)


def _comprobar(ruta_pdf, campo, res):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    with open(ruta_pdf, "rb") as f:
        lector = PdfFileReader(f, strict=False)
        for emb in lector.embedded_signatures:
            st = validate_pdf_signature(emb, ValidationContext(trust_roots=[], allow_fetching=False))
            res.append({"campo": emb.field_name, "intacta": st.intact and st.valid, "cubre_todo": st.coverage.name,
                        "firmante": st.signing_cert.subject.native.get("common_name", "")})
    rotas = [r["campo"] for r in res if not r["intacta"]]
    if rotas:
        raise RuntimeError(f"La firma {', '.join(rotas)} no es válida tras firmar.")
    if campo and campo not in {r["campo"] for r in res}:
        raise RuntimeError("El PDF resultante no contiene la firma nueva.")
    return res
