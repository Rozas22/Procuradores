import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.firma import configuracion, firmas


def test_configuracion():
    c = configuracion(14, (323.7, 544.8, 506.4, 585.1)).splitlines()
    assert "signaturePage=14" in c and "signaturePositionOnPageLowerLeftX=324" in c
    assert "alwaysCreateRevision=true" in c


def test_separador():
    assert "\\n" in configuracion(1, (0, 0, 10, 10), "\\n") and "\n" not in configuracion(1, (0, 0, 10, 10), "\\n")
