"""Pruebas con datos inventados. Ejecutar: python -m pytest tests"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from escritos_procura.motor import (Adjunto, Datos, Entrada, buscar_procedimiento, estado_en_carpeta,
                                    extraer_datos, nombre_carpeta, guardar_adjuntos)

TEXTO = """1/14
ESCRITO CONTESTACION DEMANDA
PROCEDIMIENTO VERBAL 1265/2026.
DEMANDANTE: ACME SEGUROS SA.
DEMANDADO: EMPRESA EJEMPLO SL.
SECCION CIVIL DEL TRIBUNAL DE INSTANCIA DE
BILBAO
PLAZA Nº 10
Dª. FULANA DE TAL, Procurador de los Tribunales"""


def test_contestacion():
    d = extraer_datos(TEXTO)
    assert d.tipo_escrito == "Contestación a la demanda"
    assert d.procedimiento == "Verbal 1265/2026"
    assert d.organo == "Sección Civil del Tribunal de Instancia de Bilbao" and d.plaza == "10"
    assert d.demandante == "ACME SEGUROS SA" and not d.dudoso


def test_formatos_carpeta():
    d = extraer_datos(TEXTO)
    assert nombre_carpeta(d, "{num}.{aa}") == "1265.26"
    assert nombre_carpeta(d, "{num}-{aaaa}") == "1265-2026"
    assert nombre_carpeta(d, "{tipo} {num}-{aaaa}") == "Verbal 1265-2026"
    assert nombre_carpeta(Datos(), "{num}.{aa}") == ""


def test_otros_formatos():
    d = extraer_datos("AL JUZGADO DE PRIMERA INSTANCIA Nº 3 DE BARAKALDO\nJuicio Ordinario nº 87/25\nESCRITO DE PROPOSICIÓN DE PRUEBA")
    assert d.tipo_escrito == "Proposición de prueba" and d.procedimiento == "Ordinario 87/2025"
    assert d.organo.startswith("Juzgado de Primera Instancia")
    assert buscar_procedimiento("JUICIO VERBAL 0001265-2026")[1:] == ("0001265", "2026")
    assert extraer_datos("Hola, te paso la factura").dudoso


def test_guardar_no_sobrescribe(tmp_path):
    guardar_adjuntos(tmp_path, [Adjunto("a.pdf", b"1")])
    nombres = guardar_adjuntos(tmp_path, [Adjunto("a.pdf", b"1"), Adjunto("a.pdf", b"2")])
    assert nombres == ["a.pdf", "a (2).pdf"] and (tmp_path / "a.pdf").read_bytes() == b"1"


def test_estado_en_carpeta(tmp_path):
    t0 = time.time()
    (tmp_path / "escrito.pdf").write_bytes(b"%PDF sin firmar")
    assert estado_en_carpeta(tmp_path, t0) == ""
    (tmp_path / "escrito_firmado.pdf").write_bytes(b"%PDF /Type /Sig /ByteRange [0 1 2 3]")
    assert estado_en_carpeta(tmp_path, t0) == "Firmado"
    (tmp_path / "RESGUARDO 19-11-26.pdf").write_bytes(b"%PDF")
    assert estado_en_carpeta(tmp_path, t0) == "Presentado"
