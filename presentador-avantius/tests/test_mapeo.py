import json

import pytest

from presentador.mapeo import RUTA_POR_DEFECTO, cargar_mapeo, mapear_tipo_escrito

MAPEO = {
    "por_defecto": "Escrito de trámite",
    "reglas": [
        {"contiene": ["PROPOSICION DE PRUEBA"], "tipo_escrito": "Petición de diligencia de prueba"},
        {"contiene": ["RECURSO", "REPOSICION"], "tipo_escrito": "Recurso de reposición"},
    ],
}


def test_regla_sin_tildes_ni_mayusculas():
    r = mapear_tipo_escrito("Proposición de prueba", MAPEO)
    assert r.tipo_escrito == "Petición de diligencia de prueba" and not r.por_defecto and not r.aviso


def test_todas_las_palabras_deben_aparecer():
    assert mapear_tipo_escrito("RECURSO DE REPOSICIÓN", MAPEO).tipo_escrito == "Recurso de reposición"
    assert mapear_tipo_escrito("RECURSO DE APELACIÓN", MAPEO).por_defecto


def test_por_defecto_con_aviso():
    r = mapear_tipo_escrito("SOLICITUD DE SUSPENSIÓN", MAPEO)
    assert r.tipo_escrito == "Escrito de trámite" and r.por_defecto and "Revísalo" in r.aviso


def test_archivo_del_proyecto_es_valido():
    m = cargar_mapeo(RUTA_POR_DEFECTO)
    assert mapear_tipo_escrito("PROPOSICIÓN DE PRUEBA", m).tipo_escrito == "Petición de diligencia de prueba"


def test_regla_incompleta_da_error(tmp_path):
    r = tmp_path / "m.json"
    r.write_text(json.dumps({"reglas": [{"contiene": ["X"]}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_mapeo(r)
