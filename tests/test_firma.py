import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.firma import configuracion, nombre_firmado


def test_configuracion():
    c = configuracion(14, (323.7, 544.8, 506.4, 585.1)).splitlines()
    assert "signaturePage=14" in c and "signaturePositionOnPageLowerLeftX=324" in c
    assert "alwaysCreateRevision=true" in c


def test_nombre(tmp_path):
    p = tmp_path / "escrito.pdf"
    assert nombre_firmado(p).name == "escrito firmado.pdf"
    (tmp_path / "escrito firmado.pdf").write_bytes(b"x")
    assert nombre_firmado(p).name == "escrito firmado (2).pdf"
