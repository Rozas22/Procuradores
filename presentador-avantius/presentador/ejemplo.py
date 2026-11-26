"""Genera un escrito de ejemplo (datos inventados) y un certificado de PRUEBA para probar
la extracción y la firma sin tocar escritos ni certificados reales.

    python -m presentador ejemplo  -> crea la carpeta «ejemplo/»
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

PARRAFOS = [
    "Dª. MARÍA DEL MAR ORTEGA GONZÁLEZ, Procuradora de los Tribunales, en nombre y representación",
    "de D. Iñaki Ejemplo Ficticio, según tengo acreditado en los autos arriba indicados, bajo la",
    "dirección letrada de D. Jon Etxeberria Uriarte, ante el Juzgado comparezco y, como mejor",
    "proceda en Derecho, DIGO:",
    "",
    "PRIMERO.- Que por Diligencia de Ordenación de fecha 12/05/2026 se ha dado traslado a esta",
    "parte para proponer los medios de prueba de los que intente valerse.",
    "",
    "SEGUNDO.- Que, en su virtud, propongo los siguientes medios de prueba: documental, por",
    "reproducción de los documentos aportados con la demanda; e interrogatorio de la parte actora.",
]


def _fuente_reportlab():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from .signer import FUENTES
    for f in FUENTES:
        if Path(f).is_file():
            pdfmetrics.registerFont(TTFont("Texto", f))
            return "Texto"
    return "Helvetica"


def crear_pdf_ejemplo(ruta: str | Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    ruta = Path(ruta)
    fuente = _fuente_reportlab()
    c = canvas.Canvas(str(ruta), pagesize=A4)
    ancho, alto = A4
    # Página 1
    c.setFont(fuente, 12)
    c.drawString(70, alto - 80, "AL JUZGADO DE PRIMERA INSTANCIA Nº 12 DE BILBAO")
    c.setFont(fuente, 11)
    c.drawString(70, alto - 110, "Autos Juicio Verbal 1379/2026")
    c.setFont(fuente, 12)
    c.drawString(70, alto - 150, "ESCRITO DE PROPOSICIÓN DE PRUEBA")
    c.setFont(fuente, 10)
    y = alto - 190
    for p in PARRAFOS:
        c.drawString(70, y, p)
        y -= 16
    c.showPage()
    # Página 2 (última): súplica y firmas en dos columnas
    c.setFont(fuente, 10)
    y = alto - 80
    for p in ["SUPLICO AL JUZGADO: que tenga por presentado este escrito y por propuesta la prueba",
              "indicada, acordando su admisión y práctica.", "",
              "En Bilbao, a 26 de noviembre de 2026."]:
        c.drawString(70, y, p)
        y -= 16
    c.setFont(fuente, 10)
    c.drawString(70, y - 40, "PROCURADORA")
    c.drawString(320, y - 40, "LETRADO")
    c.drawString(70, y - 110, "Fdo.: María del Mar Ortega González")
    c.drawString(320, y - 110, "Fdo.: Jon Etxeberria Uriarte")
    c.showPage()
    c.save()
    return ruta


def crear_certificado_prueba(ruta_pfx: str | Path, clave: str = "1234",
                             nombre: str = "PRUEBA ORTEGA GONZALEZ MARIA DEL MAR - 00000000T") -> Path:
    """Certificado autofirmado SOLO para pruebas (Avantius no lo aceptará)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    clave_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombre),
                        x509.NameAttribute(NameOID.COUNTRY_NAME, "ES")])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(sujeto).issuer_name(sujeto)
            .public_key(clave_priv.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(days=1)).not_valid_after(ahora + dt.timedelta(days=365))
            .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
            .sign(clave_priv, hashes.SHA256()))
    ruta_pfx = Path(ruta_pfx)
    ruta_pfx.write_bytes(pkcs12.serialize_key_and_certificates(
        b"prueba", clave_priv, cert, None, serialization.BestAvailableEncryption(clave.encode())))
    return ruta_pfx
