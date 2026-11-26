import base64
import os
import subprocess
import sys

import pytest

from presentador.ejemplo import crear_certificado_prueba
from presentador.parser import extraer_de_pdf
from presentador.signer import (
    AjustesSello, FirmanteWindows, calcular_posicion, comprobar_firma, firmante_pfx, firmar_pdf, info_pdfa,
)

FDO_PROC_X = 70     # en el PDF de ejemplo: «Fdo.: María...» empieza en x=70
FDO_LETRADO_X = 320


def test_extraer_del_pdf_de_ejemplo(pdf_ejemplo):
    d = extraer_de_pdf(pdf_ejemplo)
    assert (d.organo, d.numero, d.anio, d.titulo) == ("1ª Instancia nº 12 de Bilbao", "1379", "2026", "PROPOSICIÓN DE PRUEBA")
    assert d.procurador == "María del Mar Ortega González" and d.letrado == "Jon Etxeberria Uriarte"


def test_posicion_bajo_fdo_del_procurador(pdf_ejemplo):
    pos = calcular_posicion(pdf_ejemplo)
    x0, y0, x1, y1 = pos.caja
    assert pos.metodo == "fdo" and pos.pagina == 1 and not pos.avisos
    assert abs(x0 - FDO_PROC_X) < 2
    assert x1 < FDO_LETRADO_X              # no invade la columna del letrado
    assert y1 < 842 - 80 - 4 * 16 - 110   # por debajo de la línea «Fdo.» (A4 = 842 pt de alto)


def test_posicion_por_nombre_del_procurador(pdf_ejemplo):
    pos = calcular_posicion(pdf_ejemplo, nombre_procurador="Jon Etxeberria Uriarte")
    assert abs(pos.caja[0] - FDO_LETRADO_X) < 2


def test_posicion_fija_si_no_hay_fdo(tmp_path):
    from reportlab.pdfgen import canvas
    ruta = tmp_path / "sin_fdo.pdf"
    c = canvas.Canvas(str(ruta))
    c.drawString(70, 700, "Documento sin firmas")
    c.save()
    pos = calcular_posicion(ruta, AjustesSello(x_fijo=100, y_fijo=50, ancho=150, alto=40))
    assert pos.metodo == "fija" and pos.caja == (100, 50, 250, 90) and pos.avisos


def test_firma_con_pfx(pdf_ejemplo, pfx):
    original = pdf_ejemplo.read_bytes()
    r = firmar_pdf(pdf_ejemplo, None, firmante_pfx(pfx, "1234"))
    assert r.ruta.name == "escrito firmado.pdf" and pdf_ejemplo.read_bytes() == original
    assert r.firmante.startswith("PRUEBA ORTEGA")
    firmas = comprobar_firma(r.ruta)
    assert [f["campo"] for f in firmas] == ["FirmaProcurador"] and firmas[0]["intacta"]
    assert r.ruta.read_bytes().startswith(original)   # revisión incremental: el original queda intacto dentro


def test_reemplazar_original(pdf_ejemplo, pfx):
    r = firmar_pdf(pdf_ejemplo, pdf_ejemplo, firmante_pfx(pfx, "1234"))
    assert r.ruta == pdf_ejemplo and comprobar_firma(pdf_ejemplo)


def test_no_rompe_la_firma_del_letrado(pdf_ejemplo, pfx, tmp_path):
    letrado = crear_certificado_prueba(tmp_path / "letrado.pfx", "abcd", "PRUEBA LETRADO")
    con_letrado = tmp_path / "con_letrado.pdf"
    firmar_pdf(pdf_ejemplo, con_letrado, firmante_pfx(letrado, "abcd"), nombre_procurador="Jon Etxeberria")
    r = firmar_pdf(con_letrado, tmp_path / "final.pdf", firmante_pfx(pfx, "1234"))
    firmas = comprobar_firma(r.ruta)
    assert [f["campo"] for f in firmas] == ["FirmaProcurador", "FirmaProcurador2"]
    assert all(f["intacta"] for f in firmas)


def test_info_pdfa(pdf_ejemplo, tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, StreamObject
    assert info_pdfa(pdf_ejemplo) == ""
    w = PdfWriter(clone_from=str(pdf_ejemplo))
    xmp = StreamObject()
    xmp.set_data(b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                 b'<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" pdfaid:part="2" '
                 b'pdfaid:conformance="B"/></rdf:RDF></x:xmpmeta>')
    xmp[NameObject("/Type")] = NameObject("/Metadata")
    xmp[NameObject("/Subtype")] = NameObject("/XML")
    w._root_object[NameObject("/Metadata")] = w._add_object(xmp)
    ruta = tmp_path / "pdfa.pdf"
    w.write(str(ruta))
    assert info_pdfa(ruta) == "PDF/A-2b"


# --- Firmante de Windows, simulando PowerShell con una clave local -----------------------

def _powershell_falso(clave, cert_der):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

    def ejecutar(script, entrada="", entorno=None, timeout=0):
        if "X509Chain" in script:
            return base64.b64encode(cert_der).decode()
        datos = base64.b64decode(entrada)
        h = getattr(hashes, entorno["RESUMEN"])()
        if entorno["ALGORITMO"] == "rsa":
            firma = clave.sign(datos, padding.PKCS1v15(), h)
        else:  # Windows devuelve ECDSA en formato r||s (IEEE P1363)
            r, s = utils.decode_dss_signature(clave.sign(datos, ec.ECDSA(h)))
            n = (clave.curve.key_size + 7) // 8
            firma = r.to_bytes(n, "big") + s.to_bytes(n, "big")
        return base64.b64encode(firma).decode()
    return ejecutar


@pytest.mark.parametrize("tipo", ["rsa", "ec"])
def test_firmante_windows_simulado(pdf_ejemplo, tmp_path, tipo):
    import datetime as dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.x509.oid import NameOID

    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048) if tipo == "rsa" \
        else ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PRUEBA WINDOWS")])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
            .serial_number(1).not_valid_before(ahora - dt.timedelta(days=1))
            .not_valid_after(ahora + dt.timedelta(days=30)).sign(clave, hashes.SHA256()))
    der = cert.public_bytes(serialization.Encoding.DER)
    firmante = FirmanteWindows("AB" * 20, ejecutar=_powershell_falso(clave, der))
    r = firmar_pdf(pdf_ejemplo, tmp_path / "w.pdf", firmante)
    assert r.firmante == "PRUEBA WINDOWS" and comprobar_firma(r.ruta)[0]["intacta"]


def test_huella_invalida():
    with pytest.raises(ValueError):
        FirmanteWindows("no-es-una-huella", ejecutar=lambda *a, **k: "")


# --- Almacén real de Windows (solo en Windows con PRUEBA_ALMACEN_WINDOWS=1, p. ej. en GitHub Actions) ---

@pytest.mark.skipif(sys.platform != "win32" or os.environ.get("PRUEBA_ALMACEN_WINDOWS") != "1",
                    reason="solo en Windows con PRUEBA_ALMACEN_WINDOWS=1 (crea y borra un certificado de prueba)")
def test_almacen_windows_real(pdf_ejemplo, tmp_path):
    from presentador.signer import listar_certificados_windows
    entorno = {k: v for k, v in os.environ.items() if k != "PSModulePath"}  # ver signer._powershell
    ps = ("$ErrorActionPreference='Stop'; $c = New-SelfSignedCertificate -Subject 'CN=PRUEBA PRESENTADOR AVANTIUS' -CertStoreLocation "
          "Cert:\\CurrentUser\\My -KeyAlgorithm RSA -KeyLength 2048 -KeyExportPolicy NonExportable "
          "-KeyUsage DigitalSignature,NonRepudiation -NotAfter (Get-Date).AddDays(2); $c.Thumbprint")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, env=entorno)
    assert r.returncode == 0 and r.stdout.strip(), f"No se pudo crear el certificado de prueba: {r.stderr}"
    huella = r.stdout.strip().splitlines()[-1]
    try:
        assert huella in [c.huella for c in listar_certificados_windows()]
        r = firmar_pdf(pdf_ejemplo, tmp_path / "w.pdf", FirmanteWindows(huella))
        assert r.firmante == "PRUEBA PRESENTADOR AVANTIUS" and comprobar_firma(r.ruta)[0]["intacta"]
    finally:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Remove-Item -LiteralPath Cert:\\CurrentUser\\My\\{huella}"], check=False, env=entorno)


def test_detecta_pdf_manipulado(pdf_ejemplo, pfx, tmp_path):
    r = firmar_pdf(pdf_ejemplo, tmp_path / "f.pdf", firmante_pfx(pfx, "1234"))
    datos = bytearray(r.ruta.read_bytes())
    i = datos.find(b"Juicio Verbal") if b"Juicio Verbal" in datos else 400
    datos[i + 200] ^= 0x01  # un bit cambiado dentro de lo firmado
    manipulado = tmp_path / "manipulado.pdf"
    manipulado.write_bytes(bytes(datos))
    with pytest.raises(Exception):
        comprobar_firma(manipulado)
