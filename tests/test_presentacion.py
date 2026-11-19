import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.presentacion import (buscar_poder, categoria_anexo, cliente_del_escrito, es_juridica,
                                           identificacion_en, letrado_del_escrito, partido_judicial, tipo_organo)

TEXTO = """Dª. FULANA DE TAL , Procurador de los Tribunales y de la
sociedad EMPRESA-EJEMPLO REDES SAU -en adelante, EER- según acredito mediante poder
ante el Juzgado comparezco bajo la dirección letrada de D. Juan Pérez García,
Colegiado nº 1234 del Iltre. Colegio de Abogados de Bizkaia"""


def test_cliente_y_letrado():
    assert cliente_del_escrito(TEXTO) == "EMPRESA-EJEMPLO REDES SAU"
    assert letrado_del_escrito(TEXTO) == ("Juan Perez Garcia", "1234")


def test_organo():
    assert tipo_organo("Sección Civil del Tribunal de Instancia de Bilbao") == "1ª Instancia"
    assert tipo_organo("Juzgado de Instrucción Nº 2 de Getxo") == "Instrucción"
    assert partido_judicial("Sección Civil del Tribunal de Instancia de Bilbao") == "Bilbao"
    assert partido_judicial("Juzgado de Primera Instancia Nº 3 de Barakaldo") == "Barakaldo"


def test_persona_e_identificacion():
    assert es_juridica("EMPRESA EJEMPLO SL") and not es_juridica("JUAN PEREZ GARCIA")
    assert identificacion_en("La mercantil EMPRESA EJEMPLO SL con CIF B-12345674 y domicilio", "EMPRESA EJEMPLO") == "B12345674"
    assert identificacion_en("D. Juan con DNI 12345678Z") == "12345678Z"


def test_poder(tmp_path):
    (tmp_path / "PODER EMPRESA EJEMPLO REDES.pdf").write_bytes(b"%PDF")
    (tmp_path / "Poder 2656 - OTRA COSA SL.pdf").write_bytes(b"%PDF")
    assert buscar_poder(tmp_path, "EMPRESA EJEMPLO REDES SAU").name == "PODER EMPRESA EJEMPLO REDES.pdf"
    assert buscar_poder(tmp_path, "NADIE CONOCIDO SL") is None


def test_categoria():
    assert categoria_anexo("DOC 1.pdf", "INFORME sobre el suministro") == ("DOC 1", "Pericial")
    assert categoria_anexo("Documento 2.pdf", "Factura") == ("DOC 2", "Documental")
