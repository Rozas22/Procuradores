import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.portal import ruta_para


def test_rutas():
    assert ruta_para("Contestación a la demanda") == "Personacion/Contestacion"
    assert ruta_para("Proposición de prueba") == "buscar"
    assert ruta_para("Escrito de trámite") == "buscar"
