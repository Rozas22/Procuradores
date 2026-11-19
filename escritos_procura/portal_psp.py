"""Pasos en el formulario de Personación/Contestación del PSP (Avantius).

Cada paso es independiente: si uno falla, se apunta y se sigue con el siguiente,
para que la persona solo tenga que completar lo que falte. Nunca se pulsa
«Enviar».

Los controles se localizan por el texto de su etiqueta (como los ve la persona),
no por identificadores internos, para aguantar cambios menores del portal.
"""
from __future__ import annotations

import re
import time
import unicodedata

from .presentacion import FichaPortal


def _n(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip().lower()


def _xp(texto: str) -> str:
    """Literal XPath seguro."""
    if "'" not in texto:
        return f"'{texto}'"
    return "concat('" + texto.replace("'", "',\"'\",'") + "')"


class Formulario:
    def __init__(self, pagina, avisar):
        self.p = pagina
        self.avisar = avisar
        self.hecho: list[str] = []
        self.pendiente: list[str] = []

    # --- utilidades -----------------------------------------------------------
    def esperar(self, ms=400):
        try:
            self.p.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self.p.wait_for_timeout(ms)

    def visible(self, xpath: str):
        """Último elemento visible que cumple el XPath (las ventanas emergentes van al
        final de la página, así ganan a lo que queda detrás), en la página o sus marcos."""
        for marco in [self.p.main_frame, *[f for f in self.p.frames if f != self.p.main_frame]]:
            loc = marco.locator(f"xpath={xpath}")
            try:
                n = loc.count()
            except Exception:
                continue
            for i in reversed(range(n)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:
                    pass
        return None

    def control(self, etiqueta: str, tipo: str = "select", espera: float = 8.0):
        """El control (select/input/textarea) que sigue a la etiqueta visible."""
        tag = {"select": "select", "input": "input[not(@type='hidden') and not(@type='file') and not(@type='checkbox') and not(@type='button') and not(@type='submit')]",
               "textarea": "textarea"}[tipo]
        xpath = (f"//*[not(self::option) and not(self::script)][text()[starts-with(normalize-space(.), {_xp(etiqueta)})]]"
                 f"/following::{tag}[1]")
        fin = time.time() + espera
        while time.time() < fin:
            el = self.visible(xpath)
            if el is not None:
                return el
            self.p.wait_for_timeout(300)
        raise LookupError(f"no encuentro el campo «{etiqueta}»")

    def boton(self, texto: str, espera: float = 8.0, exacto=True):
        cond = (f"normalize-space(.)={_xp(texto)} or normalize-space(@value)={_xp(texto)}" if exacto else
                f"contains(normalize-space(.), {_xp(texto)}) or contains(normalize-space(@value), {_xp(texto)})")
        xpath = f"//*[self::button or self::a or self::input[@type='button' or @type='submit'] or @role='button'][{cond}]"
        fin = time.time() + espera
        while time.time() < fin:
            el = self.visible(xpath)
            if el is not None:
                return el
            self.p.wait_for_timeout(300)
        raise LookupError(f"no encuentro el botón «{texto}»")

    def texto_clic(self, texto: str, espera: float = 8.0):
        xpath = f"//*[not(self::script)][normalize-space(text())={_xp(texto)}]"
        fin = time.time() + espera
        while time.time() < fin:
            el = self.visible(xpath)
            if el is not None:
                el.click()
                return
            self.p.wait_for_timeout(300)
        raise LookupError(f"no encuentro «{texto}»")

    def elegir(self, etiqueta: str, *buscar: str, evitar: tuple[str, ...] = (), espera: float = 10.0) -> str:
        """Elige en un desplegable la opción que contiene todos los textos buscados.
        Si hay varias, la más corta; si no hay ninguna, error."""
        sel = self.control(etiqueta, "select")
        fin = time.time() + espera
        opciones: list[str] = []
        while time.time() < fin:
            opciones = [o for o in sel.locator("option").all_inner_texts() if o.strip()]
            validas = [o for o in opciones
                       if all(_n(b) in _n(o) for b in buscar) and not any(_n(e) in _n(o) for e in evitar)
                       and not _n(o).startswith("seleccione")]
            if validas:
                elegida = sorted(validas, key=len)[0]
                if len(validas) > 1:
                    exactas = [o for o in validas if _n(o) == _n(" ".join(buscar))]
                    elegida = exactas[0] if exactas else elegida
                sel.select_option(label=elegida)
                self.esperar()
                return elegida
            self.p.wait_for_timeout(400)
            sel = self.control(etiqueta, "select")
        raise LookupError(f"en «{etiqueta}» no hay ninguna opción con {' '.join(buscar)!r} "
                          f"(hay: {', '.join(opciones[:8])})")

    def escribir(self, etiqueta: str, valor: str, tipo="input"):
        el = self.control(etiqueta, tipo)
        el.fill(valor)
        try:
            el.dispatch_event("change")
            el.press("Tab")
        except Exception:
            pass

    def subir(self, boton_texto: str, ruta, cerca_de: str | None = None):
        """Pulsa «Seleccionar» y entrega el archivo al selector de archivos."""
        if cerca_de:
            xpath = (f"//*[text()[starts-with(normalize-space(.), {_xp(cerca_de)})]]/following::*"
                     f"[self::button or self::input[@type='button' or @type='submit'] or self::a][normalize-space(.)={_xp(boton_texto)} or @value={_xp(boton_texto)}][1]")
            b = self.visible(xpath)
            if b is None:
                raise LookupError(f"no encuentro «{boton_texto}» junto a «{cerca_de}»")
        else:
            b = self.boton(boton_texto)
        with self.p.expect_file_chooser(timeout=10000) as fc:
            b.click()
        fc.value.set_files(str(ruta))
        self.esperar(800)

    def paso(self, nombre: str, fn) -> bool:
        self.avisar("info", f"Portal: {nombre}…")
        try:
            fn()
            self.hecho.append(nombre)
            return True
        except Exception as ex:
            self.pendiente.append(f"{nombre} ({str(ex).splitlines()[0][:160]})")
            return False

    # --- el formulario --------------------------------------------------------
    def abrir_personarse(self):
        self.boton("Envío escritos", exacto=False).click()
        self.p.wait_for_timeout(300)
        self.texto_clic("Personarse/Contestar")
        self.esperar()

    def destino(self, f: FichaPortal):
        self.elegir("Tipo Órgano Judicial", f.tipo_organo)
        self.elegir("Partido Judicial", f.partido)
        buscar = [f"Pza. {f.plaza} "] if f.plaza else []
        if f.seccion:
            buscar.append(f.seccion)
        if buscar:
            self.elegir("Organo Judicial", *buscar)
        else:
            raise LookupError("el escrito no dice la plaza: elige tú el órgano judicial")
        self.escribir("Número Procedimiento", f.numero)
        self.escribir("Año", f.anio)
        self.escribir("Pieza", f.pieza)
        self.boton("Siguiente").click()
        self.esperar()

    def procedimiento(self, f: FichaPortal):
        """Marca el procedimiento correcto si hay varios y pulsa Siguiente."""
        tabla = self.visible("//*[normalize-space(text())='Tipo de procedimiento']/ancestor::table[1]")
        if tabla is None:
            raise LookupError("no aparece la lista de procedimientos (¿número, año u órgano incorrectos?)")
        filas = tabla.locator("tr:has(input[type=checkbox]), tr:has(input[type=radio])")
        n = filas.count()
        if n == 0:
            raise LookupError("el portal no encuentra ningún procedimiento con esos datos")
        if n > 1:
            objetivo = _n(f.tipo_procedimiento)
            elegida = None
            for i in range(n):
                if objetivo and objetivo in _n(filas.nth(i).inner_text()):
                    elegida = i
                    break
            if elegida is None:
                raise LookupError("hay varios procedimientos y no sé cuál es: márcalo tú")
            for i in range(n):
                casilla = filas.nth(i).locator("input[type=checkbox], input[type=radio]").first
                casilla.set_checked(i == elegida)
        else:
            casilla = filas.first.locator("input[type=checkbox], input[type=radio]").first
            if not casilla.is_checked():
                casilla.check()
        self.boton("Siguiente").click()
        self.esperar()

    def interviniente(self, f: FichaPortal):
        if not f.cliente:
            raise LookupError("no sé quién es el cliente")
        # ¿Ya está en la lista? Entonces solo marcar «Sel.»
        if not self._marcar_interviniente(f):
            self.boton("Nuevo").click()
            self.esperar()
            self.elegir("Representado", "Sí")
            self.elegir("Tipo de Intervención", f.intervencion)
            self.elegir("Tipo de Persona", "Jurídica" if f.persona_juridica else "Física")
            if f.identificacion:
                try:
                    self.elegir("Tipo Identificacion", "CIF" if f.persona_juridica else "NIF", espera=3)
                except LookupError:
                    pass
                self.escribir("Nº Identificacion", f.identificacion)
                self.esperar(1200)  # el portal rellena el resto si ya la conoce
            else:
                raise LookupError("falta el CIF/NIF: complétalo y pulsa Aceptar")
            self.boton("Aceptar").click()
            self.esperar()
            if not self._marcar_interviniente(f):
                raise LookupError("he añadido al cliente pero no he podido marcar «Sel.»")

    def _marcar_interviniente(self, f: FichaPortal) -> bool:
        tabla = self.visible("//*[normalize-space(text())='Interviniente']/ancestor::table[1]")
        if tabla is None:
            return False
        filas = tabla.locator("tr")
        for i in range(filas.count()):
            fila = filas.nth(i)
            txt = _n(fila.inner_text())
            if (f.identificacion and _n(f.identificacion) in txt) or \
               (f.cliente and _n(f.cliente.split()[0]) in txt and "demandado" in txt):
                casillas = fila.locator("input[type=checkbox]")
                if casillas.count():
                    ultima = casillas.nth(casillas.count() - 1)
                    if not ultima.is_checked():
                        ultima.check()
                        self.esperar()
                    return True
        return False

    def _elegir_en_buscador(self, boton_abrir: str, nombre: str, colegiado: str):
        self.boton(boton_abrir).click()
        self.esperar()
        partes = nombre.split()
        try:
            self.escribir("Nombre/Apellido", " ".join(partes[:2]) if len(partes) > 1 else nombre)
        except LookupError:
            pass
        self.boton("Buscar").click()
        self.esperar()
        enlace = self.visible(f"//a[normalize-space(.)={_xp(colegiado)}]")
        if enlace is None:
            raise LookupError(f"no aparece el nº de colegiado {colegiado} en la búsqueda")
        enlace.click()
        self.esperar()
        try:
            cerrar = self.boton("Cerrar", espera=2)
            cerrar.click()
        except LookupError:
            pass

    def defensor(self, f: FichaPortal):
        if not f.letrado_colegiado:
            raise LookupError("no sé quién es el letrado")
        self._elegir_en_buscador("Seleccionar abogado", f.letrado, f.letrado_colegiado)

    def documento(self, f: FichaPortal):
        self.escribir("Título Documento", f.titulo)
        self.escribir("Descripción Documento", f.titulo)
        if not f.documento or not f.documento_firmado:
            raise LookupError("el escrito no está firmado todavía: súbelo tú cuando lo firmes")
        self.subir("Seleccionar", f.documento, cerca_de="Descripción Documento")

    def anexo(self, a):
        boton = self.visible("//*[normalize-space(text())='Documentación Anexa Digital']/following::*"
                             "[self::button or self::input[@type='button' or @type='submit'] or self::a][normalize-space(.)='Añadir' or @value='Añadir'][1]")
        if boton is None:
            raise LookupError("no encuentro «Añadir» en Documentación Anexa Digital")
        boton.click()
        self.esperar()
        self.escribir("Título Documento", a.titulo)
        self.elegir("Categorización", a.categoria)
        self.subir("Seleccionar", a.ruta, cerca_de="Fichero")
        self.boton("Añadir").click()
        self.esperar()
        try:
            self.boton("Cerrar", espera=2).click()
            self.esperar()
        except LookupError:
            pass

    def procurador(self, f: FichaPortal):
        if not f.procurador_colegiado:
            raise LookupError("pon tu nombre y nº de colegiado de procurador en Ajustes")
        boton = None
        for texto in ("Seleccionar procurador", "Añadir procurador", "Seleccionar Procurador"):
            try:
                boton = self.boton(texto, espera=1.5)
                break
            except LookupError:
                continue
        if boton is None:
            boton = self.boton("rocurador", exacto=False, espera=3)
        texto_boton = boton.inner_text().strip() or boton.get_attribute("value") or ""
        self._elegir_en_buscador(texto_boton, f.procurador, f.procurador_colegiado)

    # --- todo seguido -----------------------------------------------------------
    def contestacion(self, f: FichaPortal):
        if not self.paso("abrir Personarse/Contestar", self.abrir_personarse):
            return
        if not self.paso("destino (órgano, partido, plaza, número y año)", lambda: self.destino(f)):
            return
        if not self.paso("procedimiento", lambda: self.procedimiento(f)):
            return
        self.paso("interviniente (cliente)", lambda: self.interviniente(f))
        self.paso("defensor (letrado)", lambda: self.defensor(f))
        self.paso("documento principal", lambda: self.documento(f))
        for a in f.anexos:
            self.paso(f"anexo «{a.titulo}»", lambda a=a: self.anexo(a))
        self.paso("procuradora", lambda: self.procurador(f))
