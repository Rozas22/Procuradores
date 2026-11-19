"""Ventana principal de Escritos Procura."""
from __future__ import annotations

import datetime as dt
import struct
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressDialog, QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
)

from . import __version__, actualizador
from .almacen import APP_NOMBRE, ESTADOS, PORTALES, Ajustes, Almacen, Escrito
from .motor import (FORMATOS_CARPETA, TIPOS_ESCRITO, Datos, Entrada, analizar,
                    leer_archivos, nombre_carpeta)
from .servicio import YaImportado, importar, refrescar_estados

COLOR_ESTADO = {
    "Pendiente de firmar": ("#8a5a00", "#fff3d6"),
    "Firmado": ("#1d4ed8", "#e0ebff"),
    "Presentado": ("#166534", "#dcfce7"),
}

ESTILO = """
QWidget { color: #111827; }
QMainWindow, QDialog { background: #f6f7f9; }
QToolBar { background: #ffffff; border-bottom: 1px solid #e5e7eb; spacing: 4px; padding: 2px; }
QToolBar QToolButton { color: #111827; padding: 4px 8px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #f3f4f6; }
QToolBar QToolButton#actualizar { background: #16a34a; color: white; font-weight: 600; }
QLineEdit, QComboBox { background: #ffffff; color: #111827; border: 1px solid #d1d5db; border-radius: 6px; padding: 4px 6px; }
QComboBox QAbstractItemView { background: #ffffff; color: #111827; selection-background-color: #dbeafe; selection-color: #111827; }
QCheckBox { color: #111827; }
QStatusBar { color: #374151; }
QToolTip { background: #111827; color: #ffffff; border: none; padding: 4px; }
QLabel#titulo { font-size: 20px; font-weight: 600; color: #1f2937; }
QLabel#sub { color: #6b7280; }
QFrame#soltar { border: 2px dashed #9ca3af; border-radius: 12px; background: #ffffff; }
QFrame#soltar[activo="true"] { border-color: #2563eb; background: #eef4ff; }
QFrame#panel { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; }
QLabel#campo { color: #6b7280; font-size: 11px; }
QLabel#valor { color: #111827; font-size: 13px; }
QLabel#aviso { background: #fff7ed; color: #9a3412; border: 1px solid #fed7aa; border-radius: 6px; padding: 6px; }
QPushButton { padding: 6px 12px; border-radius: 6px; border: 1px solid #d1d5db; background: #ffffff; }
QPushButton:hover { background: #f3f4f6; }
QPushButton#primario { background: #2563eb; color: white; border: none; }
QPushButton#primario:hover { background: #1d4ed8; }
QPushButton#copiar { padding: 2px 8px; font-size: 11px; }
QTableWidget { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; gridline-color: #f3f4f6; }
QHeaderView::section { background: #f9fafb; border: none; border-bottom: 1px solid #e5e7eb; padding: 6px; font-weight: 600; }
"""


def abrir(ruta: str | Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


# ---------------------------------------------------------------------------
# Arrastrar desde Outlook (archivos "virtuales") y desde el Explorador
# ---------------------------------------------------------------------------

def rutas_de_mime(mime: QMimeData) -> list[Path]:
    rutas = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
    if rutas:
        return [r for r in rutas if r.is_file()]
    # Outlook escritorio: FileGroupDescriptorW + FileContents (solo el primer elemento)
    fmt_desc = next((f for f in mime.formats() if "FileGroupDescriptorW" in f), None)
    fmt_cont = next((f for f in mime.formats() if "FileContents" in f), None)
    if fmt_desc and fmt_cont:
        try:
            desc = bytes(mime.data(fmt_desc))
            n = struct.unpack_from("<I", desc, 0)[0]
            if n >= 1:
                # FILEDESCRIPTORW: 592 bytes, nombre (WCHAR[260]) al final
                nombre = desc[4 + 72: 4 + 592].decode("utf-16-le").split("\x00", 1)[0] or "correo.msg"
                datos = bytes(mime.data(fmt_cont))
                if datos:
                    tmp = Path(tempfile.mkdtemp(prefix="escritos_")) / nombre
                    tmp.write_bytes(datos)
                    return [tmp]
        except Exception:
            pass
    return []


# ---------------------------------------------------------------------------
# Diálogos
# ---------------------------------------------------------------------------

class DialogoAjustes(QDialog):
    def __init__(self, ajustes: Ajustes, parent=None, bienvenida=False):
        super().__init__(parent)
        self.a = ajustes
        self.setWindowTitle("Bienvenida" if bienvenida else "Ajustes")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        if bienvenida:
            t = QLabel(f"Bienvenida a {APP_NOMBRE}")
            t.setObjectName("titulo")
            s = QLabel("Dos datos y empezamos. Puedes cambiarlos cuando quieras en Ajustes.")
            s.setObjectName("sub")
            lay.addWidget(t)
            lay.addWidget(s)
        form = QFormLayout()
        lay.addLayout(form)

        fila = QHBoxLayout()
        self.carpeta = QLineEdit(ajustes.carpeta_escritos)
        self.carpeta.setPlaceholderText("Carpeta donde guardas los escritos de los juzgados")
        b = QPushButton("Elegir…")
        b.clicked.connect(self._elegir)
        fila.addWidget(self.carpeta)
        fila.addWidget(b)
        form.addRow("Carpeta de escritos", fila)

        self.formato = QComboBox()
        for ejemplo, patron in FORMATOS_CARPETA.items():
            self.formato.addItem(ejemplo, patron)
        self.formato.addItem("Personalizado…", "")
        idx = self.formato.findData(ajustes.formato_carpeta)
        self.formato_libre = QLineEdit(ajustes.formato_carpeta)
        self.formato_libre.setToolTip("Usa {num}, {aa} (año 26), {aaaa} (año 2026) y {tipo} (Verbal, Ordinario…)")
        self.formato.setCurrentIndex(idx if idx >= 0 else self.formato.count() - 1)
        self.formato.currentIndexChanged.connect(self._formato_cambiado)
        form.addRow("Nombre de cada carpeta", self.formato)
        form.addRow("", self.formato_libre)
        self._formato_cambiado()

        self.portal = QComboBox()
        self.portal.addItems(list(PORTALES))
        self.portal.setCurrentText(ajustes.portal_nombre if ajustes.portal_nombre in PORTALES else "Otro")
        self.portal_url = QLineEdit(ajustes.portal_url)
        self.portal.currentTextChanged.connect(lambda n: self.portal_url.setText(PORTALES.get(n, "")) if PORTALES.get(n) else None)
        form.addRow("Portal donde presentas", self.portal)
        form.addRow("Dirección del portal", self.portal_url)

        self.ficha = QCheckBox("Guardar también una ficha .txt con los datos en la carpeta")
        self.ficha.setChecked(ajustes.escribir_ficha)
        self.revisar = QCheckBox("Enseñarme siempre los datos antes de archivar (aunque estén claros)")
        self.revisar.setChecked(ajustes.revisar_siempre)
        lay.addWidget(self.ficha)
        lay.addWidget(self.revisar)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Empezar" if bienvenida else "Guardar")
        bb.button(QDialogButtonBox.Ok).setObjectName("primario")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._aceptar)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _elegir(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de escritos", self.carpeta.text())
        if d:
            self.carpeta.setText(d)

    def _formato_cambiado(self):
        patron = self.formato.currentData()
        self.formato_libre.setVisible(not patron)
        if patron:
            self.formato_libre.setText(patron)

    def _aceptar(self):
        carpeta = self.carpeta.text().strip()
        if not carpeta or not Path(carpeta).is_dir():
            QMessageBox.warning(self, APP_NOMBRE, "Elige una carpeta que exista.")
            return
        patron = self.formato_libre.text().strip()
        try:
            prueba = nombre_carpeta(Datos(numero="1265", anio="2026", tipo_procedimiento="VERBAL"), patron)
        except (KeyError, ValueError, IndexError):
            prueba = ""
        if "{num}" not in patron or not prueba:
            QMessageBox.warning(self, APP_NOMBRE, "El nombre de carpeta tiene que incluir {num}.")
            return
        self.a.carpeta_escritos = carpeta
        self.a.formato_carpeta = patron
        self.a.portal_nombre = self.portal.currentText()
        self.a.portal_url = self.portal_url.text().strip()
        self.a.escribir_ficha = self.ficha.isChecked()
        self.a.revisar_siempre = self.revisar.isChecked()
        self.a.guardar()
        self.accept()


class DialogoRevisar(QDialog):
    """Muestra lo que se ha leído para corregirlo antes de archivar."""

    def __init__(self, entrada: Entrada, datos: Datos, principal: str | None, ajustes: Ajustes, parent=None):
        super().__init__(parent)
        self.entrada, self.datos, self.ajustes = entrada, datos, ajustes
        self.setWindowTitle("Revisa los datos del escrito")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        for a in datos.avisos:
            l = QLabel(a)
            l.setObjectName("aviso")
            l.setWordWrap(True)
            lay.addWidget(l)
        form = QFormLayout()
        lay.addLayout(form)

        self.tipo_escrito = QComboBox()
        self.tipo_escrito.setEditable(True)
        self.tipo_escrito.addItems([n for n, _ in TIPOS_ESCRITO])
        self.tipo_escrito.setCurrentText(datos.tipo_escrito)
        form.addRow("Tipo de escrito", self.tipo_escrito)

        fila = QHBoxLayout()
        self.tipo_proc = QLineEdit(datos.tipo_procedimiento.title())
        self.tipo_proc.setPlaceholderText("Verbal, Ordinario…")
        self.numero = QLineEdit(str(int(datos.numero)) if datos.numero else "")
        self.numero.setPlaceholderText("1265")
        self.anio = QLineEdit(datos.anio4)
        self.anio.setPlaceholderText("2026")
        self.anio.setMaximumWidth(70)
        fila.addWidget(self.tipo_proc, 2)
        fila.addWidget(self.numero, 1)
        fila.addWidget(QLabel("/"))
        fila.addWidget(self.anio)
        form.addRow("Procedimiento", fila)

        self.organo = QLineEdit(datos.organo)
        self.plaza = QLineEdit(datos.plaza)
        self.demandante = QLineEdit(datos.demandante)
        self.demandado = QLineEdit(datos.demandado)
        form.addRow("Juzgado", self.organo)
        form.addRow("Plaza", self.plaza)
        form.addRow("Demandante", self.demandante)
        form.addRow("Demandado", self.demandado)

        self.principal = QComboBox()
        for a in entrada.adjuntos:
            self.principal.addItem(a.nombre)
        if principal:
            self.principal.setCurrentText(principal)
        form.addRow("Escrito principal", self.principal)

        self.destino = QLabel()
        self.destino.setObjectName("sub")
        self.destino.setWordWrap(True)
        form.addRow("Se guardará en", self.destino)
        for w in (self.numero, self.anio, self.tipo_proc):
            w.textChanged.connect(self._preview)
        self._preview()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Archivar")
        bb.button(QDialogButtonBox.Ok).setObjectName("primario")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._aceptar)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _leer(self) -> Datos:
        d = Datos(
            tipo_procedimiento=self.tipo_proc.text().strip().upper(),
            numero=self.numero.text().strip(), anio=self.anio.text().strip(),
            organo=self.organo.text().strip(), plaza=self.plaza.text().strip(),
            tipo_escrito=self.tipo_escrito.currentText().strip(),
            demandante=self.demandante.text().strip(), demandado=self.demandado.text().strip(),
            avisos=[a for a in self.datos.avisos if not a.startswith("OJO")],
        )
        return d

    def _preview(self):
        d = self._leer()
        ok = d.numero.isdigit() and d.anio.isdigit() and len(d.anio) in (2, 4)
        nombre = nombre_carpeta(d, self.ajustes.formato_carpeta) if ok else ""
        self.destino.setText(str(Path(self.ajustes.carpeta_escritos) / nombre) if nombre else "Falta el número y el año")

    def _aceptar(self):
        d = self._leer()
        if not (d.numero.isdigit() and d.anio.isdigit() and len(d.anio) in (2, 4)):
            QMessageBox.warning(self, APP_NOMBRE, "Pon el número y el año del procedimiento (por ejemplo 1265 / 2026).")
            return
        self.resultado = (d, self.principal.currentText())
        self.accept()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class ZonaSoltar(QFrame):
    def __init__(self, al_pulsar):
        super().__init__()
        self.setObjectName("soltar")
        self.setMinimumHeight(96)
        lay = QVBoxLayout(self)
        t = QLabel("Arrastra aquí el correo o los PDFs del escrito")
        t.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        t.setFont(f)
        s = QLabel("Correos de Outlook (.msg), correos guardados (.eml) o PDFs sueltos. Gmail: ⋮ → Descargar mensaje.")
        s.setObjectName("sub")
        s.setAlignment(Qt.AlignCenter)
        b = QPushButton("o elige los archivos…")
        b.clicked.connect(al_pulsar)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(b, alignment=Qt.AlignCenter)

    def activo(self, si: bool):
        self.setProperty("activo", "true" if si else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class PanelDetalle(QFrame):
    CAMPOS = [("tipo_escrito", "Tipo de escrito"), ("procedimiento", "Procedimiento"),
              ("organo", "Juzgado"), ("plaza", "Plaza"), ("demandante", "Demandante"),
              ("demandado", "Demandado"), ("principal", "Escrito")]

    def __init__(self, ventana: "Ventana"):
        super().__init__()
        self.v = ventana
        self.e: Escrito | None = None
        self.setObjectName("panel")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        self.vacio = QLabel("Elige un escrito de la lista para ver sus datos.")
        self.vacio.setObjectName("sub")
        self.vacio.setWordWrap(True)
        lay.addWidget(self.vacio)

        self.cuerpo = QWidget()
        cl = QVBoxLayout(self.cuerpo)
        cl.setContentsMargins(0, 0, 0, 0)
        g = QGridLayout()
        self.valores = {}
        for i, (k, nombre) in enumerate(self.CAMPOS):
            l = QLabel(nombre.upper())
            l.setObjectName("campo")
            val = QLabel()
            val.setObjectName("valor")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            b = QPushButton("Copiar")
            b.setObjectName("copiar")
            b.clicked.connect(lambda _=False, w=val: self._copiar(w))
            g.addWidget(l, i * 2, 0, 1, 2)
            g.addWidget(val, i * 2 + 1, 0)
            g.addWidget(b, i * 2 + 1, 1, alignment=Qt.AlignTop)
            self.valores[k] = val
        g.setColumnStretch(0, 1)
        cl.addLayout(g)
        self.avisos = QLabel()
        self.avisos.setObjectName("aviso")
        self.avisos.setWordWrap(True)
        cl.addWidget(self.avisos)

        fila = QHBoxLayout()
        self.estado = QComboBox()
        self.estado.addItems(ESTADOS)
        self.estado.activated.connect(self._estado_manual)
        fila.addWidget(QLabel("Estado:"))
        fila.addWidget(self.estado, 1)
        cl.addLayout(fila)

        botones = QGridLayout()
        b_esc = QPushButton("Abrir escrito")
        b_esc.clicked.connect(lambda: self.e and abrir(Path(self.e.carpeta) / self.e.principal))
        b_carp = QPushButton("Abrir carpeta")
        b_carp.clicked.connect(lambda: self.e and abrir(self.e.carpeta))
        self.b_portal = QPushButton("Ir al portal")
        self.b_portal.setObjectName("primario")
        self.b_portal.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.v.ajustes.portal_url)))
        b_quitar = QPushButton("Quitar de la lista")
        b_quitar.setToolTip("No borra ningún archivo")
        b_quitar.clicked.connect(self._quitar)
        botones.addWidget(b_esc, 0, 0)
        botones.addWidget(b_carp, 0, 1)
        botones.addWidget(self.b_portal, 1, 0, 1, 2)
        botones.addWidget(b_quitar, 2, 0, 1, 2)
        cl.addLayout(botones)
        cl.addStretch(1)
        lay.addWidget(self.cuerpo)
        self.mostrar(None)

    def _copiar(self, w: QLabel):
        QGuiApplication.clipboard().setText(w.text())
        self.v.statusBar().showMessage(f"Copiado: {w.text()}", 2500)

    def mostrar(self, e: Escrito | None):
        self.e = e
        self.vacio.setVisible(e is None)
        self.cuerpo.setVisible(e is not None)
        if e is None:
            return
        for k, w in self.valores.items():
            w.setText(getattr(e, k) or "—")
        self.avisos.setText("\n".join(e.avisos))
        self.avisos.setVisible(bool(e.avisos))
        self.estado.setCurrentText(e.estado)
        self.b_portal.setEnabled(bool(self.v.ajustes.portal_url))

    def _estado_manual(self):
        if self.e:
            self.e.estado = self.estado.currentText()
            self.e.estado_manual = True
            self.v.almacen.guardar(self.e)
            self.v.recargar(seleccionar=self.e.id)

    def _quitar(self):
        if not self.e:
            return
        r = QMessageBox.question(self, APP_NOMBRE, "¿Quitar este escrito de la lista?\nLos archivos de la carpeta no se tocan.")
        if r == QMessageBox.Yes:
            self.v.almacen.borrar(self.e.id)
            self.v.recargar()


class _Senales(QObject):
    resultado = Signal(object, bool, str)
    progreso = Signal(int, int)
    descargado = Signal(str, str)


class Ventana(QMainWindow):
    def __init__(self, almacen: Almacen | None = None):
        super().__init__()
        self.setWindowTitle(APP_NOMBRE)
        self.resize(1180, 720)
        self.setAcceptDrops(True)
        self.ajustes = Ajustes.cargar()
        self.almacen = almacen or Almacen()

        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        a_add = QAction("Añadir archivos…", self)
        a_add.triggered.connect(self.elegir_archivos)
        a_ref = QAction("Actualizar estados", self)
        a_ref.triggered.connect(lambda: self.refrescar(avisar=True))
        a_aj = QAction("Ajustes", self)
        a_aj.triggered.connect(self.abrir_ajustes)
        a_inf = QAction("Acerca de", self)
        a_inf.triggered.connect(lambda: QMessageBox.about(
            self, APP_NOMBRE, f"{APP_NOMBRE} {__version__}\n\nTodo se guarda en este ordenador. "
            "La aplicación no envía datos a ningún sitio."))
        a_upd = QAction("Buscar actualizaciones", self)
        a_upd.triggered.connect(lambda: self.buscar_actualizacion(manual=True))
        for a in (a_add, a_ref, a_aj, a_upd, a_inf):
            tb.addAction(a)
        self.a_nueva = QAction("", self)
        self.a_nueva.setVisible(False)
        self.a_nueva.triggered.connect(self.instalar_actualizacion)
        tb.addSeparator()
        tb.addAction(self.a_nueva)
        tb.widgetForAction(self.a_nueva).setObjectName("actualizar")
        self.novedad = None
        self._senales = _Senales()
        self._senales.resultado.connect(self._resultado_busqueda)
        self._senales.progreso.connect(self._progreso_descarga)
        self._senales.descargado.connect(self._descargado)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(16, 12, 16, 12)
        self.zona = ZonaSoltar(self.elegir_archivos)
        lay.addWidget(self.zona)

        cab = QHBoxLayout()
        t = QLabel("Escritos")
        t.setObjectName("titulo")
        self.filtro = QComboBox()
        self.filtro.addItems(["Pendientes", "Todos"])
        self.filtro.currentIndexChanged.connect(lambda: self.recargar())
        cab.addWidget(t)
        cab.addStretch(1)
        cab.addWidget(QLabel("Ver:"))
        cab.addWidget(self.filtro)
        lay.addLayout(cab)

        sp = QSplitter()
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Recibido", "Procedimiento", "Juzgado", "Tipo de escrito", "Estado"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setShowGrid(False)
        self.tabla.setAlternatingRowColors(False)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        self.tabla.cellDoubleClicked.connect(lambda r, c: self.detalle.e and abrir(self.detalle.e.carpeta))
        self.detalle = PanelDetalle(self)
        sp.addWidget(self.tabla)
        sp.addWidget(self.detalle)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        lay.addWidget(sp, 1)

        self.statusBar().showMessage("Listo")
        self._escritos: list[Escrito] = []
        self.recargar()
        self.temporizador = QTimer(self)
        self.temporizador.timeout.connect(self.refrescar)
        self.temporizador.start(20_000)

    # --- arrastrar y soltar ---------------------------------------------
    def dragEnterEvent(self, ev):
        m = ev.mimeData()
        if m.hasUrls() or any("FileGroupDescriptor" in f for f in m.formats()):
            ev.acceptProposedAction()
            self.zona.activo(True)

    def dragLeaveEvent(self, ev):
        self.zona.activo(False)

    def dropEvent(self, ev):
        self.zona.activo(False)
        rutas = rutas_de_mime(ev.mimeData())
        ev.acceptProposedAction()
        if rutas:
            self.procesar(rutas)
        else:
            QMessageBox.information(self, APP_NOMBRE, "No he podido leer lo que has soltado. "
                                    "Guarda el correo o los PDFs en el ordenador y arrástralos desde la carpeta.")

    def elegir_archivos(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige el correo o los PDFs", str(Path.home() / "Downloads"),
            "Correos y documentos (*.eml *.msg *.pdf *.doc *.docx);;Todos (*.*)")
        if rutas:
            self.procesar([Path(r) for r in rutas])

    # --- importar ---------------------------------------------------------
    def procesar(self, rutas: list[Path]):
        if not self.ajustes.configurado and not self.abrir_ajustes(bienvenida=True):
            return
        try:
            entradas = leer_archivos(rutas)
        except Exception as ex:
            QMessageBox.warning(self, APP_NOMBRE, f"No se ha podido abrir el archivo:\n{ex}")
            return
        hechos, ultimo = [], None
        for e in entradas:
            if not any(a.es_pdf for a in e.adjuntos):
                QMessageBox.information(self, APP_NOMBRE, f"«{e.asunto or e.origen}» no trae ningún PDF.")
                continue
            if (prev := self.almacen.existe(e.clave)):
                self.statusBar().showMessage(f"Ya estaba en la lista: {prev.procedimiento}", 5000)
                ultimo = prev.id
                continue
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                datos, principal = analizar(e)
            finally:
                QApplication.restoreOverrideCursor()
            pnombre = principal.nombre if principal else None
            if datos.dudoso or self.ajustes.revisar_siempre:
                dlg = DialogoRevisar(e, datos, pnombre, self.ajustes, self)
                if dlg.exec() != QDialog.Accepted:
                    continue
                datos, pnombre = dlg.resultado
            try:
                esc = importar(e, datos, pnombre, self.ajustes, self.almacen)
            except YaImportado as yi:
                ultimo = yi.escrito.id
                continue
            except Exception as ex:
                QMessageBox.warning(self, APP_NOMBRE, f"No se ha podido archivar:\n{ex}")
                continue
            hechos.append(esc)
            ultimo = esc.id
        if hechos:
            self.statusBar().showMessage(
                "Archivado: " + "; ".join(f"{h.tipo_escrito or 'escrito'} {h.procedimiento} → {Path(h.carpeta).name}" for h in hechos), 8000)
        self.filtro.setCurrentIndex(0 if all(h.estado != "Presentado" for h in hechos) else 1)
        self.recargar(seleccionar=ultimo)

    # --- lista ------------------------------------------------------------
    def recargar(self, seleccionar: int | None = None):
        if seleccionar is None and self.detalle.e:
            seleccionar = self.detalle.e.id
        todos = self.almacen.todos()
        if self.filtro.currentText() == "Pendientes":
            todos = [e for e in todos if e.estado != "Presentado"]
        self._escritos = todos
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(todos))
        fila_sel = -1
        for i, e in enumerate(todos):
            try:
                rec = dt.datetime.fromisoformat(e.recibido).strftime("%d/%m %H:%M")
            except ValueError:
                rec = e.recibido
            vals = [rec, e.procedimiento, e.organo + (f" · Plaza {e.plaza}" if e.plaza else ""), e.tipo_escrito, e.estado]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 4:
                    fg, bg = COLOR_ESTADO.get(v, ("#111827", "#ffffff"))
                    it.setForeground(QColor(fg))
                    it.setBackground(QColor(bg))
                if c == 1 and e.avisos:
                    it.setToolTip("\n".join(e.avisos))
                    it.setText("⚠ " + v)
                self.tabla.setItem(i, c, it)
            if e.id == seleccionar:
                fila_sel = i
        self.tabla.blockSignals(False)
        if fila_sel >= 0:
            self.tabla.selectRow(fila_sel)
        self.detalle.mostrar(todos[fila_sel] if fila_sel >= 0 else None)

    def _seleccion(self):
        filas = self.tabla.selectionModel().selectedRows()
        self.detalle.mostrar(self._escritos[filas[0].row()] if filas else None)

    def refrescar(self, avisar=False):
        n = refrescar_estados(self.almacen)
        if n or avisar:
            self.recargar()
            self.statusBar().showMessage(f"Estados actualizados ({n} cambios)", 4000)

    # --- actualizaciones ------------------------------------------------------
    def buscar_actualizacion(self, manual=False):
        def tarea():
            try:
                self._senales.resultado.emit(actualizador.buscar(), manual, "")
            except Exception as ex:
                self._senales.resultado.emit(None, manual, str(ex))
        threading.Thread(target=tarea, daemon=True).start()

    def _resultado_busqueda(self, novedad, manual, error):
        if novedad:
            self.novedad = novedad
            self.a_nueva.setText(f"⬆ Actualizar a la versión {novedad.version}")
            self.a_nueva.setVisible(True)
            if manual:
                self.instalar_actualizacion()
        elif manual:
            if error:
                QMessageBox.information(self, APP_NOMBRE, "No se ha podido comprobar si hay actualizaciones. "
                                        "Revisa la conexión a internet e inténtalo más tarde.")
            else:
                QMessageBox.information(self, APP_NOMBRE, f"Ya tienes la última versión ({__version__}).")

    def instalar_actualizacion(self):
        n = self.novedad
        if not n:
            return
        notas = f"\n\nNovedades:\n{n.notas.strip()}" if n.notas.strip() else ""
        r = QMessageBox.question(self, APP_NOMBRE,
                                 f"Hay una versión nueva ({n.version}). Tienes la {__version__}.{notas}\n\n"
                                 "¿Actualizar ahora? La app se cerrará y se abrirá sola en un momento. "
                                 "No se pierde ningún dato.")
        if r != QMessageBox.Yes:
            return
        if not actualizador.puede_instalar():
            QDesktopServices.openUrl(QUrl(n.url_instalador))
            return
        self._dlg = QProgressDialog("Descargando la actualización…", None, 0, 100, self)
        self._dlg.setWindowTitle(APP_NOMBRE)
        self._dlg.setWindowModality(Qt.WindowModal)
        self._dlg.setMinimumDuration(0)
        self._dlg.show()

        def tarea():
            try:
                ruta = actualizador.descargar(n, lambda h, t: self._senales.progreso.emit(h, t))
                self._senales.descargado.emit(str(ruta), "")
            except Exception as ex:
                self._senales.descargado.emit("", str(ex))
        threading.Thread(target=tarea, daemon=True).start()

    def _progreso_descarga(self, hecho, total):
        if total:
            self._dlg.setValue(int(hecho * 100 / total))

    def _descargado(self, ruta, error):
        self._dlg.close()
        if error:
            QMessageBox.warning(self, APP_NOMBRE, f"No se ha podido descargar la actualización:\n{error}")
            return
        actualizador.lanzar_instalador(Path(ruta))
        QApplication.quit()

    def abrir_ajustes(self, bienvenida=False) -> bool:
        ok = DialogoAjustes(self.ajustes, self, bienvenida).exec() == QDialog.Accepted
        self.detalle.mostrar(self.detalle.e)
        return ok


def paleta_clara() -> QPalette:
    """Colores fijos claros: así se lee igual aunque Windows esté en modo oscuro."""
    p = QPalette()
    texto, fondo, base = QColor("#111827"), QColor("#f6f7f9"), QColor("#ffffff")
    for grupo in (QPalette.Active, QPalette.Inactive):
        p.setColor(grupo, QPalette.Window, fondo)
        p.setColor(grupo, QPalette.WindowText, texto)
        p.setColor(grupo, QPalette.Base, base)
        p.setColor(grupo, QPalette.AlternateBase, QColor("#f9fafb"))
        p.setColor(grupo, QPalette.Text, texto)
        p.setColor(grupo, QPalette.Button, base)
        p.setColor(grupo, QPalette.ButtonText, texto)
        p.setColor(grupo, QPalette.ToolTipBase, texto)
        p.setColor(grupo, QPalette.ToolTipText, base)
        p.setColor(grupo, QPalette.PlaceholderText, QColor("#9ca3af"))
        p.setColor(grupo, QPalette.Highlight, QColor("#2563eb"))
        p.setColor(grupo, QPalette.HighlightedText, base)
        p.setColor(grupo, QPalette.Link, QColor("#2563eb"))
    for rol in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, rol, QColor("#9ca3af"))
    p.setColor(QPalette.Disabled, QPalette.Window, fondo)
    p.setColor(QPalette.Disabled, QPalette.Base, QColor("#f3f4f6"))
    p.setColor(QPalette.Disabled, QPalette.Button, QColor("#f3f4f6"))
    return p


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NOMBRE)
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    app.setStyle("Fusion")
    app.setPalette(paleta_clara())
    app.setStyleSheet(ESTILO)
    icono = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "recursos" / "icono.ico"
    if icono.exists():
        app.setWindowIcon(QIcon(str(icono)))
    v = Ventana()
    v.show()
    if not v.ajustes.configurado:
        QTimer.singleShot(200, lambda: v.abrir_ajustes(bienvenida=True))
    QTimer.singleShot(3000, v.buscar_actualizacion)
    for arg in sys.argv[1:]:
        if Path(arg).is_file():
            QTimer.singleShot(400, lambda a=arg: v.procesar([Path(a)]))
    sys.exit(app.exec())
