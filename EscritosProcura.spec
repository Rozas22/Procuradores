# -*- mode: python ; coding: utf-8 -*-
# Construir: pyinstaller EscritosProcura.spec
a = Analysis(
    ["main.py"],
    datas=[("recursos", "recursos")],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtNetwork"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="EscritosProcura",
          console=False, icon="recursos/icono.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="EscritosProcura")
