import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.actualizador import es_mas_nueva, version_tupla


def test_versiones():
    assert version_tupla("v0.10.1") == (0, 10, 1)
    assert es_mas_nueva("0.3.0", "0.2.0") and es_mas_nueva("1.0.0", "0.9.9")
    assert not es_mas_nueva("0.2.0", "0.2.0") and not es_mas_nueva("0.1.9", "0.2.0")
