"""Asistente del portal PSP de Justizia.eus (Avantius).

Abre una ventana de Microsoft Edge controlada por la app, con un perfil propio
para que la sesión se mantenga entre usos. El usuario se identifica con su
certificado; la app espera a ver la página de inicio y luego navega sola hasta
el formulario del escrito. Nunca pulsa "Enviar": eso lo hace siempre la persona.

Todo lo de Playwright se ejecuta en un hilo aparte (la API síncrona exige
usar los objetos en el mismo hilo que los creó).
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .almacen import carpeta_datos

URL_INICIO_PSP = "https://psp.justizia.eus/PSP/app/index.html#/"
ESPERA_LOGIN_MAX = 15 * 60  # segundos

# Qué camino seguir según el tipo de escrito
RUTA_MENU = {
    "Contestación a la demanda": "Personacion/Contestacion",
    "Personación": "Personacion/Contestacion",
    "Demanda": "Escritos de Inicio",
    "Solicitud de ejecución": "Escritos de Inicio",
}


def ruta_para(tipo_escrito: str) -> str:
    """'buscar' para escritos de trámite; si no, el texto de la opción del Menú."""
    return RUTA_MENU.get(tipo_escrito, "buscar")


@dataclass
class Trabajo:
    tipo_escrito: str
    numero: str
    anio: str
    archivos: list[Path]


class SesionPortal:
    """Una ventana de navegador que se reutiliza para varios escritos."""

    def __init__(self, avisar: Callable[[str, str], None], url_inicio: str = URL_INICIO_PSP,
                 canal: str | None = "msedge", ejecutable: str | None = None, sin_ventana: bool = False):
        self.avisar = avisar            # avisar(nivel, texto) nivel: info|login|listo|error
        self.url_inicio = url_inicio
        self.canal = canal
        self.ejecutable = ejecutable
        self.sin_ventana = sin_ventana
        self._cola: list[Trabajo] = []
        self._hay = threading.Event()
        self._parar = False
        self._hilo: threading.Thread | None = None

    # --- API para la ventana ------------------------------------------------
    def presentar(self, t: Trabajo):
        self._cola.append(t)
        self._hay.set()
        if not self._hilo or not self._hilo.is_alive():
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def cerrar(self):
        self._parar = True
        self._hay.set()

    # --- hilo del navegador -------------------------------------------------
    def _bucle(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.avisar("error", "Falta el componente del navegador (playwright).")
            return
        perfil = carpeta_datos() / "navegador"
        try:
            with sync_playwright() as pw:
                opciones = dict(headless=self.sin_ventana, no_viewport=True, accept_downloads=True,
                                args=["--start-maximized"])
                if self.ejecutable:
                    opciones["executable_path"] = self.ejecutable
                elif self.canal:
                    opciones["channel"] = self.canal
                ctx = pw.chromium.launch_persistent_context(str(perfil), **opciones)
                ctx.set_default_timeout(20_000)
                pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
                while not self._parar:
                    self._hay.wait()
                    self._hay.clear()
                    while self._cola and not self._parar:
                        t = self._cola.pop(0)
                        try:
                            if pagina.is_closed():
                                pagina = ctx.new_page()
                            self._hacer(pagina, t)
                        except Exception as ex:
                            if "closed" in str(ex).lower():
                                self.avisar("error", "Se ha cerrado la ventana del navegador.")
                                return
                            self.avisar("error", f"No he podido seguir en el portal: {ex}\n"
                                                 "Puedes continuar a mano en la ventana del navegador.")
                ctx.close()
        except Exception as ex:
            msg = str(ex)
            if "msedge" in msg.lower() or "executable" in msg.lower():
                msg = "No encuentro Microsoft Edge en este ordenador."
            self.avisar("error", f"No se ha podido abrir el navegador: {msg}")

    @staticmethod
    def en_inicio(pagina) -> bool:
        """La página de inicio del PSP, ya identificado: buscador + 'Menú'."""
        try:
            if "/PSP/app/" not in pagina.url:
                return False
            return pagina.get_by_role("button", name="Buscar").first.is_visible() and \
                pagina.get_by_text("Menú", exact=False).first.is_visible()
        except Exception:
            return False

    def _esperar_login(self, pagina):
        if self.en_inicio(pagina):
            return
        # Volver a la página de inicio (si no hay sesión, el portal lleva al login).
        pagina.goto(self.url_inicio, wait_until="domcontentloaded")
        limite = time.time() + ESPERA_LOGIN_MAX
        avisado = False
        while time.time() < limite and not self._parar:
            if self.en_inicio(pagina):
                return
            if not avisado:
                time.sleep(1.5)
                if self.en_inicio(pagina):
                    return
                self.avisar("login", "Inicia sesión con el certificado en la ventana del navegador. "
                                     "Cuando veas la página de inicio del portal, sigo yo.")
                avisado = True
            time.sleep(1)
        raise TimeoutError("no se ha iniciado sesión a tiempo")

    def _hacer(self, pagina, t: Trabajo):
        self.avisar("info", "Abriendo el portal…")
        try:
            pagina.bring_to_front()
        except Exception:
            pass
        self._esperar_login(pagina)
        self.avisar("info", "Sesión iniciada. Buscando el procedimiento…")
        ruta = ruta_para(t.tipo_escrito)
        if ruta == "buscar":
            self._buscar(pagina, t.numero, t.anio)
            self.avisar("listo", f"He buscado el procedimiento {t.numero}/{t.anio}. "
                                 "Sigue en el navegador; recuerda que el envío lo haces tú.")
        else:
            self._menu(pagina, ruta)
            self.avisar("listo", f"Estás en «{ruta}». Sigue en el navegador; el envío lo haces tú.")

    @staticmethod
    def _buscar(pagina, numero: str, anio: str):
        boton = pagina.get_by_role("button", name="Buscar").first
        # Los dos campos (número / año) están en la misma barra que el botón.
        barra = boton.locator("xpath=ancestor::*[count(.//input[not(@type='hidden')])>=2][1]")
        campos = barra.locator("input:not([type=hidden])")
        campos.nth(0).fill(str(int(numero)))
        campos.nth(1).fill(anio)
        boton.click()

    @staticmethod
    def _menu(pagina, opcion: str):
        pagina.get_by_text("Menú", exact=False).first.click()
        pagina.get_by_text(opcion, exact=True).first.click()
