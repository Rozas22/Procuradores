import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from presentador.ejemplo import crear_certificado_prueba, crear_pdf_ejemplo  # noqa: E402


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
    """Los ajustes y la caché de fuentes van a una carpeta temporal, no a la del usuario."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def pdf_ejemplo(tmp_path):
    return crear_pdf_ejemplo(tmp_path / "escrito.pdf")


@pytest.fixture
def pfx(tmp_path):
    return crear_certificado_prueba(tmp_path / "proc.pfx", "1234")
