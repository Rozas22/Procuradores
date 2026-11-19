# -*- mode: python ; coding: utf-8 -*-
# Construir: pyinstaller EscritosProcura.spec
from PyInstaller.utils.hooks import collect_all

# Playwright necesita su "driver" (node + paquete) dentro de la app.
pw_datas, pw_bins, pw_hidden = collect_all("playwright")

a = Analysis(
    ["main.py"],
    datas=[("recursos", "recursos")] + pw_datas,
    binaries=pw_bins,
    hiddenimports=pw_hidden,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtNetwork"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="EscritosProcura",
          console=False, icon="recursos/icono.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="EscritosProcura")
