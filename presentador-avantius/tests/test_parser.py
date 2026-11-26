"""Pruebas del parser con textos inventados (no hay datos reales de clientes)."""
import pytest

from presentador.parser import (
    clave_organo, coincide_organo, elegir_organo, extraer_datos, extraer_firmantes,
    extraer_organo, extraer_procedimiento, extraer_titulo,
)

ESCRITO = """AL JUZGADO DE PRIMERA INSTANCIA Nº 12 DE BILBAO

Autos Juicio Verbal 1379/2026

ESCRITO DE PROPOSICIÓN DE PRUEBA

Dª. MARÍA DEL MAR ORTEGA GONZÁLEZ, Procuradora de los Tribunales, en nombre y
representación de D. Iñaki Ejemplo Ficticio, según tengo acreditado en los autos
arriba indicados, bajo la dirección letrada de D. Jon Etxeberria Uriarte, ante el
Juzgado comparezco y, como mejor proceda en Derecho, DIGO:

PRIMERO.- Que por Diligencia de Ordenación de fecha 12/05/2026 se ha dado traslado...

SUPLICO AL JUZGADO: que tenga por propuesta la prueba.

En Bilbao, a 26 de noviembre de 2026.

PROCURADORA LETRADO
Fdo.: María del Mar Ortega González Fdo.: Jon Etxeberria Uriarte
"""


def test_escrito_completo():
    d = extraer_datos(ESCRITO)
    assert d.organo == "1ª Instancia nº 12 de Bilbao"
    assert (d.tipo_procedimiento, d.numero, d.anio) == ("Juicio Verbal", "1379", "2026")
    assert d.numero_completo == "0001379/2026"
    assert d.titulo == "PROPOSICIÓN DE PRUEBA"
    assert d.titulo_original == "ESCRITO DE PROPOSICIÓN DE PRUEBA"
    assert d.procurador == "María del Mar Ortega González"
    assert d.letrado == "Jon Etxeberria Uriarte"
    assert d.avisos == [] and d.completo


@pytest.mark.parametrize("texto,esperado", [
    ("AL JUZGADO DE PRIMERA INSTANCIA Nº 12 DE BILBAO", "1ª Instancia nº 12 de Bilbao"),
    ("AL JUZGADO\nDE 1ª INSTANCIA Nº 12 DE BILBAO\nAutos: ...", "1ª Instancia nº 12 de Bilbao"),
    ("AL JUZGADO DE PRIMERA INSTANCIA\nNÚMERO 3 DE BARAKALDO\n\nJuicio Ordinario 5/2026", "1ª Instancia nº 3 de Barakaldo"),
    ("AL JUZGADO DE 1ª INSTANCIA N.º 7 DE VITORIA-GASTEIZ", "1ª Instancia nº 7 de Vitoria-Gasteiz"),
    ("AL JUZGADO DE LO MERCANTIL Nº 1 DE BILBAO", "Lo Mercantil nº 1 de Bilbao"),
    ("AL JUZGADO DE LO SOCIAL NÚM. 4 DE DONOSTIA", "Lo Social nº 4 de Donostia"),
    ("A LA AUDIENCIA PROVINCIAL DE BIZKAIA", "Audiencia Provincial de Bizkaia"),
    ("Sin destinatario", ""),
])
def test_organo(texto, esperado):
    assert extraer_organo(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("Autos Juicio Verbal 1379/2026", ("Juicio Verbal", "1379", "2026")),
    ("AUTOS: JUICIO VERBAL Nº 1379/2026", ("Juicio Verbal", "1379", "2026")),
    ("Procedimiento Ordinario 0000123/2025", ("Procedimiento Ordinario", "123", "2025")),
    ("Autos nº 45/26", ("", "45", "2026")),
    ("Procedimiento: Ejecución de Títulos Judiciales 88/2024", ("Ejecución de Títulos Judiciales", "88", "2024")),
    ("Juicio Verbal (Desahucio) — Monitorio 1500/2026", ("Monitorio", "1500", "2026")),
    ("Diligencia de 12/05/2026 sin autos", ("", "", "")),
])
def test_procedimiento(texto, esperado):
    assert extraer_procedimiento(texto) == esperado


def test_fecha_antes_que_autos_no_confunde():
    assert extraer_procedimiento("Bilbao, 12/05/2026\nAutos Juicio Verbal 1379/2026")[1:] == ("1379", "2026")


@pytest.mark.parametrize("texto,limpio", [
    ("ESCRITO DE PROPOSICIÓN DE PRUEBA", "PROPOSICIÓN DE PRUEBA"),
    ("ESCRITO DE OPOSICIÓN AL RECURSO DE APELACIÓN", "OPOSICIÓN AL RECURSO DE APELACIÓN"),
    ("ESCRITO SOLICITANDO LA SUSPENSIÓN DE LA VISTA", "LA SUSPENSIÓN DE LA VISTA"),
    ("CONTESTACIÓN A LA DEMANDA", "CONTESTACIÓN A LA DEMANDA"),
    ("ESCRITO DE APORTACIÓN DE DOCUMENTOS Y\nSOLICITUD DE SUSPENSIÓN", "APORTACIÓN DE DOCUMENTOS Y SOLICITUD DE SUSPENSIÓN"),
])
def test_titulo(texto, limpio):
    texto = f"AL JUZGADO DE PRIMERA INSTANCIA Nº 1 DE BILBAO\nAutos Juicio Verbal 1/2026\n{texto}\nD. Fulano, Procurador..."
    assert extraer_titulo(texto)[0] == limpio


def test_titulo_ignora_encabezados_y_secciones():
    texto = "AL JUZGADO\nDE PRIMERA INSTANCIA Nº 1 DE BILBAO\nDIGO:\nHECHOS\nSUPLICO AL JUZGADO\nRECURSO DE REPOSICIÓN\n"
    assert extraer_titulo(texto)[0] == "RECURSO DE REPOSICIÓN"


def test_firmantes_orden_letrado_primero():
    texto = "LETRADO PROCURADOR\nFdo.: Ane Letrada Ficticia Fdo.: Mikel Procurador Ficticio"
    assert extraer_firmantes(texto) == ("Mikel Procurador Ficticio", "Ane Letrada Ficticia")


def test_firmantes_en_lineas_separadas_y_cuerpo():
    texto = ("D. Mikel Procurador Ficticio, Procurador de los Tribunales, bajo la dirección letrada "
             "de Dña. Ane Letrada Ficticia, DIGO:\n...\nFdo: Mikel Procurador Ficticio\n")
    assert extraer_firmantes(texto) == ("Mikel Procurador Ficticio", "Ane Letrada Ficticia")


def test_avisos_si_faltan_datos():
    d = extraer_datos("Texto cualquiera sin datos de un escrito judicial")
    assert not d.completo and len(d.avisos) == 4


# --- Comparación con la columna «Órgano judicial» de Avantius (para la iteración 2) ---

def test_clave_organo():
    assert clave_organo("1ª Instancia nº 12 de Bilbao") == clave_organo("1ª Ins. 12 Dec. Of. Bilbao (Bilbao)")
    assert clave_organo("1ª Instancia nº 12 de Bilbao").numero == "12"


def test_elegir_fila_correcta():
    filas = ["1ª Ins. 10 Dec. Of. Bilbao (Bilbao)", "1ª Ins. 12 Dec. Of. Bilbao (Bilbao)"]
    assert elegir_organo("1ª Instancia nº 12 de Bilbao", filas) == 1
    assert elegir_organo("1ª Instancia nº 3 de Bilbao", filas) is None
    assert not coincide_organo("Lo Social nº 12 de Bilbao", filas[1])
    assert not coincide_organo("1ª Instancia nº 12 de Barakaldo", "1ª Ins. 12 Barakaldo (Getxo)")
