"""Lectura de escritos: de un correo (.eml/.msg) o PDFs a datos + carpeta del procedimiento."""
from __future__ import annotations

import email
import email.policy
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

# ---------------------------------------------------------------------------
# Extracción de datos del texto
# ---------------------------------------------------------------------------

TIPOS_PROCEDIMIENTO = [
    "ORDINARIO", "VERBAL", "MONITORIO", "EJECUCION DE TITULOS JUDICIALES",
    "EJECUCION DE TITULOS NO JUDICIALES", "EJECUCION HIPOTECARIA", "EJECUCION",
    "CAMBIARIO", "CONCURSO ABREVIADO", "CONCURSO", "INCIDENTE CONCURSAL",
    "DESAHUCIO", "DIVORCIO", "MEDIDAS", "RECURSO DE APELACION", "APELACION",
    "PROCEDIMIENTO ABREVIADO", "DILIGENCIAS PREVIAS", "JUICIO SOBRE DELITOS LEVES",
    "SUMARIO", "DESPIDO", "SEGURIDAD SOCIAL", "EXPEDIENTE DE DOMINIO",
    "JURA DE CUENTAS", "TASACION DE COSTAS",
]

TIPOS_ESCRITO = [
    ("Contestación a la demanda", r"CONTESTACION\s+(A\s+LA\s+)?DEMANDA"),
    ("Proposición de prueba", r"PROPOSICION\s+(DE\s+)?PRUEBA"),
    ("Oposición a recurso", r"OPOSICION\s+(AL\s+)?RECURSO"),
    ("Recurso de apelación", r"RECURSO\s+DE\s+APELACION"),
    ("Recurso de reposición", r"RECURSO\s+DE\s+REPOSICION"),
    ("Recurso de revisión", r"RECURSO\s+DE\s+REVISION"),
    ("Solicitud de ejecución", r"SOLICITUD\s+DE\s+EJECUCION|DEMANDA\s+EJECUTIVA"),
    ("Demanda", r"^\s*(ESCRITO\s+DE\s+)?DEMANDA\b"),
    ("Impugnación", r"IMPUGNACION"),
    ("Oposición", r"\bOPOSICION\b"),
    ("Allanamiento", r"ALLANAMIENTO"),
    ("Desistimiento", r"DESISTIMIENTO"),
    ("Personación", r"PERSONACION"),
    ("Conclusiones", r"CONCLUSIONES"),
    ("Aportación de documentos", r"APORTA(CION)?\s+(DE\s+)?DOCUMENT"),
    ("Escrito de trámite", r"^\s*ESCRITO\b"),
]

RE_NUMERO = r"(?P<num>\d{1,7})\s*[/\-]\s*(?P<anio>(?:19|20)\d{2}|\d{2})\b"


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.upper().replace("º", "O").replace("ª", "A")


@dataclass
class Datos:
    tipo_procedimiento: str = ""
    numero: str = ""
    anio: str = ""
    organo: str = ""
    plaza: str = ""
    tipo_escrito: str = ""
    demandante: str = ""
    demandado: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def anio4(self) -> str:
        if not self.anio:
            return ""
        return self.anio if len(self.anio) == 4 else f"20{self.anio}"

    @property
    def procedimiento(self) -> str:
        if not self.numero:
            return ""
        return f"{self.tipo_procedimiento.title()} {int(self.numero)}/{self.anio4}".strip()

    @property
    def dudoso(self) -> bool:
        """True si conviene que una persona revise antes de archivar."""
        return not (self.numero and self.anio) or any(a.startswith("OJO") for a in self.avisos)


FORMATOS_CARPETA = {
    "1265.26": "{num}.{aa}",
    "1265-2026": "{num}-{aaaa}",
    "1265_2026": "{num}_{aaaa}",
    "1265-26": "{num}-{aa}",
    "Verbal 1265-2026": "{tipo} {num}-{aaaa}",
}


def nombre_carpeta(d: Datos, formato: str) -> str:
    if not (d.numero and d.anio):
        return ""
    nombre = formato.format(
        num=int(d.numero), aa=d.anio4[-2:], aaaa=d.anio4,
        tipo=d.tipo_procedimiento.title() or "Proc",
    )
    return nombre_seguro(nombre)


def buscar_procedimiento(texto: str) -> tuple[str, str, str] | None:
    t = normalizar(texto)
    tipos = "|".join(sorted((re.escape(x) for x in TIPOS_PROCEDIMIENTO), key=len, reverse=True))
    patrones = [
        rf"(?:PROCEDIMIENTO|JUICIO|AUTOS|PROC\.)\s*(?:DE\s+)?(?:JUICIO\s+)?(?P<tipo>{tipos})?\s*(?:N[O°\"]?\.?\s*)?(?:[:\-]\s*)?{RE_NUMERO}",
        rf"(?P<tipo>{tipos})\s*(?:N[O°\"]?\.?\s*)?(?:[:\-]\s*)?{RE_NUMERO}",
    ]
    for p in patrones:
        m = re.search(p, t)
        if m:
            return ((m.group("tipo") or "").strip(), m.group("num"), m.group("anio"))
    return None


def extraer_datos(texto: str) -> Datos:
    d = Datos()
    t = normalizar(texto)
    proc = buscar_procedimiento(texto)
    if proc:
        d.tipo_procedimiento, d.numero, d.anio = proc
    for nombre, patron in TIPOS_ESCRITO:
        if re.search(patron, t, re.MULTILINE):
            d.tipo_escrito = nombre
            break
    m = re.search(
        r"((?:SECCION\s+[A-Z ]+?\s+DEL\s+)?(?:TRIBUNAL\s+DE\s+INSTANCIA|"
        r"JUZGADO\s+DE\s+(?:PRIMERA\s+INSTANCIA(?:\s+E\s+INSTRUCCION)?|INSTRUCCION|LO\s+[A-Z\-]+|[A-Z]+)|"
        r"AUDIENCIA\s+PROVINCIAL|TRIBUNAL\s+SUPERIOR\s+DE\s+JUSTICIA)"
        r"(?:\s+N[O°]?\.?\s*\d+)?(?:\s+DE\s+(?!PLAZA)[A-Z\-]+(?:[ ]+(?!PLAZA)[A-Z\-]+)?)?)",
        t,
    )
    if m:
        d.organo = re.sub(r"\s+", " ", m.group(1)).strip().title().replace(" De ", " de ").replace(" Del ", " del ")
        for sin, con in (("Seccion", "Sección"), ("Instruccion", "Instrucción"), ("Audiencia", "Audiencia")):
            d.organo = d.organo.replace(sin, con)
    m = re.search(r"PLAZA\s+N[O°]?\.?\s*(\d+)", t)
    if m:
        d.plaza = m.group(1)
    m = re.search(r"DEMANDANTE[S]?\s*:\s*(.+)", t)
    if m:
        d.demandante = m.group(1).strip(" .")
    m = re.search(r"DEMANDADO[S]?\s*:\s*(.+)", t)
    if m:
        d.demandado = m.group(1).strip(" .")
    return d


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------

@dataclass
class Adjunto:
    nombre: str
    contenido: bytes

    @property
    def es_pdf(self) -> bool:
        return self.nombre.lower().endswith(".pdf")


@dataclass
class Entrada:
    """Lo que ha llegado: un correo o unos archivos sueltos."""
    adjuntos: list[Adjunto]
    asunto: str = ""
    remitente: str = ""
    origen: str = ""

    @property
    def clave(self) -> str:
        h = hashlib.sha256()
        for a in sorted(self.adjuntos, key=lambda x: x.nombre):
            h.update(hashlib.sha256(a.contenido).digest())
        return h.hexdigest()


EXTENSIONES_UTILES = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".zip", ".jpg", ".jpeg", ".tif", ".tiff"}


def nombre_seguro(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nombre).strip(" .")
    return nombre or "documento"


def texto_pdf(contenido: bytes, paginas: int = 2) -> str:
    from pypdf import PdfReader
    try:
        r = PdfReader(BytesIO(contenido))
        return "\n".join((r.pages[i].extract_text() or "") for i in range(min(paginas, len(r.pages))))
    except Exception:
        return ""


def pdf_firmado(contenido: bytes) -> bool:
    """Firma PAdES/Acrobat: el PDF lleva un diccionario de firma con /ByteRange."""
    return b"/ByteRange" in contenido and b"/Sig" in contenido


def es_escrito_principal(texto: str) -> bool:
    t = normalizar(texto[:3000])
    return "PROCURADOR" in t and bool(
        re.search(r"^\s*ESCRITO|DIGO|SUPLICO|AL\s+JUZGADO|COMPAREZCO", t, re.MULTILINE))


def leer_eml(contenido: bytes, origen: str) -> Entrada:
    msg = email.message_from_bytes(contenido, policy=email.policy.default)
    adj = []
    for parte in msg.walk():
        fn = parte.get_filename()
        if not fn:
            continue
        ext = Path(fn).suffix.lower()
        if ext not in EXTENSIONES_UTILES:
            continue
        if parte.get("Content-ID") and ext in {".jpg", ".jpeg"}:
            continue  # imágenes de la firma del correo
        datos = parte.get_payload(decode=True)
        if datos:
            adj.append(Adjunto(nombre_seguro(Path(fn).name), datos))
        elif parte.get_content_type() == "message/rfc822":
            pass
    # correos reenviados como adjunto
    for parte in msg.walk():
        if parte.get_content_type() == "message/rfc822":
            interno = parte.get_payload(0) if parte.is_multipart() else None
            if interno is not None:
                adj += leer_eml(interno.as_bytes(), origen).adjuntos
    return Entrada(adj, str(msg.get("Subject") or ""), str(msg.get("From") or ""), origen)


def leer_msg(ruta: Path) -> Entrada:
    import extract_msg
    m = extract_msg.openMsg(str(ruta))
    try:
        adj = []
        for a in m.attachments:
            fn = getattr(a, "longFilename", None) or getattr(a, "shortFilename", None) or getattr(a, "name", None)
            data = getattr(a, "data", None)
            if not fn or not isinstance(data, (bytes, bytearray)):
                continue
            if Path(fn).suffix.lower() in EXTENSIONES_UTILES and not getattr(a, "hidden", False):
                adj.append(Adjunto(nombre_seguro(Path(fn).name), bytes(data)))
        return Entrada(adj, m.subject or "", m.sender or "", f"correo {ruta.name}")
    finally:
        m.close()


def leer_archivos(rutas: list[Path]) -> list[Entrada]:
    """Cada correo es una entrada; los PDFs sueltos soltados a la vez van juntos."""
    entradas, sueltos = [], []
    for r in rutas:
        ext = r.suffix.lower()
        if ext == ".eml":
            entradas.append(leer_eml(r.read_bytes(), f"correo {r.name}"))
        elif ext == ".msg":
            entradas.append(leer_msg(r))
        elif ext in EXTENSIONES_UTILES:
            sueltos.append(Adjunto(nombre_seguro(r.name), r.read_bytes()))
    if sueltos:
        entradas.append(Entrada(sueltos, origen="archivos: " + ", ".join(a.nombre for a in sueltos)))
    return entradas


# ---------------------------------------------------------------------------
# Análisis y archivado
# ---------------------------------------------------------------------------

def analizar(e: Entrada) -> tuple[Datos, Adjunto | None]:
    pdfs = [a for a in e.adjuntos if a.es_pdf]
    textos = {id(a): texto_pdf(a.contenido) for a in pdfs}

    principal = next((a for a in pdfs if es_escrito_principal(textos[id(a)])), None)
    if principal is None and len(pdfs) == 1:
        principal = pdfs[0]
    if principal is None:
        cand = [a for a in pdfs if not re.match(r"(?i)^(doc|documento|anexo)\s*\.?\s*\d+", a.nombre)]
        principal = cand[0] if cand else None

    d = extraer_datos(textos[id(principal)]) if principal else Datos()

    otros = []
    for a in pdfs:
        if a is principal:
            continue
        p = buscar_procedimiento(textos[id(a)]) or buscar_procedimiento(a.nombre)
        if p:
            otros.append((a.nombre, p))
    if principal:
        p = buscar_procedimiento(principal.nombre)
        if p:
            otros.append((principal.nombre, p))

    if not d.numero:
        p_asunto = buscar_procedimiento(e.asunto)
        fuente = otros[0] if otros else (("el asunto del correo", p_asunto) if p_asunto else None)
        if fuente:
            tipo, d.numero, d.anio = fuente[1]
            d.tipo_procedimiento = d.tipo_procedimiento or tipo
            d.avisos.append(f"El número de procedimiento se ha sacado de {fuente[0]}. Compruébalo.")
    else:
        for nombre, (_, num, anio) in otros:
            if int(num) != int(d.numero) or anio[-2:] != d.anio[-2:]:
                d.avisos.append(f"OJO: «{nombre}» habla del procedimiento {int(num)}/{anio}, "
                                f"distinto del escrito ({int(d.numero)}/{d.anio4}).")

    if principal is None:
        d.avisos.append("No se ha encontrado un PDF que parezca el escrito principal.")
    if not d.numero:
        d.avisos.append("No se ha encontrado el número de procedimiento.")
    if not d.tipo_escrito:
        d.avisos.append("No se ha reconocido el tipo de escrito.")
    if not d.organo:
        d.avisos.append("No se ha reconocido el juzgado.")
    return d, principal


def guardar_adjuntos(destino: Path, adjuntos: list[Adjunto]) -> list[str]:
    """Copia los adjuntos sin sobrescribir nada. Devuelve los nombres finales."""
    destino.mkdir(parents=True, exist_ok=True)
    finales = []
    for a in adjuntos:
        ruta = destino / a.nombre
        if ruta.exists():
            if ruta.read_bytes() == a.contenido:
                finales.append(ruta.name)
                continue
            i = 2
            while (destino / f"{ruta.stem} ({i}){ruta.suffix}").exists():
                i += 1
            ruta = destino / f"{ruta.stem} ({i}){ruta.suffix}"
        ruta.write_bytes(a.contenido)
        finales.append(ruta.name)
    return finales


def escribir_ficha(destino: Path, d: Datos, principal: str, anexos: list[str], origen: str, cuando: str) -> Path:
    ficha = destino / f"FICHA {cuando}.txt"
    lineas = [
        "DATOS PARA LA PRESENTACIÓN (revisar antes de presentar)",
        "=" * 56,
        f"Tipo de escrito : {d.tipo_escrito or '?'}",
        f"Procedimiento   : {d.procedimiento or '?'}",
        f"Órgano judicial : {d.organo or '?'}",
        f"Plaza           : {d.plaza or '-'}",
        f"Demandante      : {d.demandante or '-'}",
        f"Demandado       : {d.demandado or '-'}",
        "",
        f"Escrito         : {principal or '?'}",
        "Anexos          : " + (", ".join(anexos) or "ninguno"),
        f"Origen          : {origen}",
    ]
    if d.avisos:
        lineas += ["", "AVISOS:"] + [f"  - {a}" for a in d.avisos]
    ficha.write_text("\r\n".join(lineas) + "\r\n", encoding="utf-8-sig")
    return ficha


def estado_en_carpeta(carpeta: Path, desde_ts: float, principal: str = "") -> str:
    """Mira la carpeta: RESGUARDO nuevo -> Presentado; PDF firmado nuevo -> Firmado."""
    if not carpeta.is_dir():
        return ""
    firmado = False
    for f in carpeta.iterdir():
        if not f.is_file():
            continue
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if normalizar(f.name).startswith("RESGUARDO") and mt >= desde_ts - 60:
            return "Presentado"
        # Firmado = un PDF guardado DESPUÉS de archivar (al firmarlo). La firma del
        # abogado que ya traía el PDF original no cuenta.
        if f.suffix.lower() == ".pdf" and mt > desde_ts + 2 and not normalizar(f.name).startswith(("DOC", "ANEXO")):
            try:
                with open(f, "rb") as fh:
                    if pdf_firmado(fh.read()):
                        firmado = True
            except OSError:
                pass
    return "Firmado" if firmado else ""
