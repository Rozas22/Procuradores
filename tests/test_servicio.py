import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from escritos_procura.almacen import Ajustes, Almacen
from escritos_procura.motor import Adjunto, Datos, Entrada
from escritos_procura.servicio import YaImportado, importar


def test_importar_y_duplicado(tmp_path):
    aj = Ajustes(carpeta_escritos=str(tmp_path / "esc"))
    (tmp_path / "esc").mkdir()
    al = Almacen(tmp_path / "db.sqlite")
    e = Entrada([Adjunto("DOC 1.pdf", b"x"), Adjunto("escrito.pdf", b"y")], origen="prueba")
    d = Datos(tipo_procedimiento="VERBAL", numero="1265", anio="2026", tipo_escrito="Demanda")
    esc = importar(e, d, "escrito.pdf", aj, al)
    carpeta = tmp_path / "esc" / "1265.26"
    assert esc.principal == "escrito.pdf" and esc.anexos == ["DOC 1.pdf"]
    assert (carpeta / "escrito.pdf").exists() and list(carpeta.glob("FICHA *.txt"))
    with pytest.raises(YaImportado):
        importar(e, d, "escrito.pdf", aj, al)
    assert len(al.todos()) == 1
