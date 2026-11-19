"""Prepara todos los datos que pide el portal para presentar un escrito.

Todo sale del PDF del escrito, de la carpeta del procedimiento y de la carpeta
de escritos (donde están los poderes de cada cliente). No toca el navegador:
así se puede probar sin portal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .motor import normalizar, pdf_firmado, texto_pdf

FORMAS_JURIDICAS = r"\b(S\.?\s?A\.?\s?U?\.?|S\.?\s?L\.?\s?U?\.?|SAU|SLU|S\.?\s?COOP\.?|SOCIEDAD|ENTIDAD|BANCO|BANKINTER|CAIXA|CAJA|MUTUA|ASEGURADORA|SEGUROS|FUNDACION|ASOCIACION|COMUNIDAD DE PROPIETARIOS|AYUNTAMIENTO|DIPUTACION)\b"
RE_CIF = r"\b([ABCDEFGHJNPQRSUVW])[- ]?(\d{7})[- ]?([0-9A-J])\b"
RE_NIF = r"\b(\d{8})[- ]?([A-Z])\b"
PARTIDOS = ["BILBAO", "BARAKALDO", "GETXO", "DURANGO", "GERNIKA-LUMO", "GERNIKA", "BALMASEDA",
            "VITORIA-GASTEIZ", "VITORIA", "AMURRIO", "DONOSTIA-SAN SEBASTIAN", "DONOSTIA", "SAN SEBASTIAN",
            "IRUN", "EIBAR", "BERGARA", "TOLOSA", "AZPEITIA"]


@dataclass
class Anexo:
    ruta: Path
    titulo: str
    categoria: str          # texto a buscar en el desplegable "Categorización"


@dataclass
class FichaPortal:
    tipo_escrito: str = ""
    tipo_organo: str = ""      # texto a buscar: "1ª Instancia" / "Instrucción"
    partido: str = ""          # "Bilbao"
    plaza: str = ""            # "10"
    seccion: str = ""          # "Civ" / "Pen"...
    numero: str = ""           # "0001265"
    anio: str = ""             # "2026"
    pieza: str = "0"
    tipo_procedimiento: str = ""
    cliente: str = ""
    persona_juridica: bool = True
    identificacion: str = ""
    intervencion: str = "Demandado"
    letrado: str = ""
    letrado_colegiado: str = ""
    procurador: str = ""
    procurador_colegiado: str = ""
    documento: Path | None = None
    documento_firmado: bool = False
    titulo: str = ""
    anexos: list[Anexo] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _titulo_ok(texto: str) -> str:
    return " ".join(p.capitalize() if len(p) > 2 else p.lower() for p in texto.lower().split())


def tipo_organo(organo: str) -> str:
    t = normalizar(organo)
    if "INSTRUCCION" in t and "PRIMERA INSTANCIA" not in t:
        return "Instrucción"
    if "LO MERCANTIL" in t:
        return "Mercantil"
    if "LO SOCIAL" in t:
        return "Social"
    if "LO PENAL" in t:
        return "Penal"
    if "CONTENCIOSO" in t:
        return "Contencioso"
    if "AUDIENCIA PROVINCIAL" in t:
        return "Audiencia Provincial"
    return "1ª Instancia"


def partido_judicial(texto: str) -> str:
    t = normalizar(texto)
    for p in PARTIDOS:
        if re.search(rf"\b{re.escape(p)}\b", t):
            return _titulo_ok(p.replace("-", "- ")).replace("- ", "-")
    m = re.search(r"\bDE\s+([A-Z\-]+)\s*$", t.strip())
    return _titulo_ok(m.group(1)) if m else ""


def seccion(organo: str) -> str:
    t = normalizar(organo)
    for clave, abrev in (("CIVIL", "Civ"), ("PENAL", "Pen"), ("SOCIAL", "Soc"),
                         ("MERCANTIL", "Mer"), ("CONTENCIOSO", "Cont"), ("INSTRUCCION", "Inst")):
        if clave in t:
            return abrev
    return ""


def cliente_del_escrito(texto: str) -> str:
    """'Procurador de los Tribunales y de la sociedad X -en adelante...' -> X"""
    t = re.sub(r"\s+", " ", normalizar(texto))
    m = re.search(r"PROCURADOR[A]? DE LOS TRIBUNALES Y DE (?:LA |EL |DON |DONA |D\. |DA\. )?"
                  r"(?:SOCIEDAD |MERCANTIL |ENTIDAD |COMPANIA )?(.+?)(?:\s+-|\s*\(|,| SEGUN| CON CIF| CON DNI| QUIEN)", t)
    return m.group(1).strip(" .") if m else ""


def letrado_del_escrito(texto: str) -> tuple[str, str]:
    t = re.sub(r"\s+", " ", texto)
    tn = normalizar(t)
    m = re.search(r"DIRECCION LETRADA DE (?:DON|DONA|D\.|DA\.|DNA\.)?\s*(.+?),?\s*COLEGIAD[OA] N[O°.\s]*\s*(\d+)", tn)
    if not m:
        m = re.search(r"LETRAD[OA] (?:DON|DONA|D\.|DA\.)?\s*(.+?),?\s*COLEGIAD[OA] N[O°.\s]*\s*(\d+)", tn)
    if not m:
        return "", ""
    return _titulo_ok(m.group(1).strip(" ,.")), m.group(2)


def es_juridica(nombre: str, ident: str = "") -> bool:
    if ident and re.match(r"^[ABCDEFGHJNPQRSUVW]\d{7}", ident):
        return True
    if ident and re.match(r"^\d{8}[A-Z]$", ident):
        return False
    return bool(re.search(FORMAS_JURIDICAS, normalizar(nombre)))


def _palabras(texto: str) -> set[str]:
    ruido = {"DE", "LA", "EL", "Y", "SA", "SL", "SAU", "SLU", "S", "A", "U", "L", "PODER", "PDF", "ESC", "DEL", "LOS", "LAS"}
    return {w for w in re.findall(r"[A-Z0-9]+", normalizar(texto)) if w not in ruido and len(w) > 1 and not w.isdigit()}


def buscar_poder(base: Path, cliente: str) -> Path | None:
    """El PDF de poder de la carpeta de escritos que más se parece al cliente."""
    if not base.is_dir() or not cliente:
        return None
    objetivo = _palabras(cliente)
    mejor, puntos = None, 0.0
    for f in base.iterdir():
        if f.suffix.lower() != ".pdf" or "PODER" not in normalizar(f.name):
            continue
        comunes = objetivo & _palabras(f.stem)
        p = len(comunes) / max(1, len(objetivo))
        if p > puntos:
            mejor, puntos = f, p
    return mejor if puntos >= 0.5 else None


def identificacion_en(texto: str, cliente: str = "") -> str:
    """CIF (o NIF) del texto; si hay varios, el más cercano al nombre del cliente."""
    t = normalizar(texto)
    cifs = [("".join(m.groups()), m.start()) for m in re.finditer(RE_CIF, t)]
    if not cifs:
        nifs = ["".join(m.groups()) for m in re.finditer(RE_NIF, t)]
        return nifs[0] if nifs else ""
    palabras = normalizar(cliente).split()
    pos = t.find(palabras[0]) if palabras else -1
    if pos >= 0:
        cifs.sort(key=lambda c: abs(c[1] - pos))
    return cifs[0][0]


def categoria_anexo(nombre: str, texto: str) -> tuple[str, str]:
    """(título, texto de la categoría) para un documento adjunto."""
    t = normalizar(texto[:3000])
    m = re.match(r"(?i)^(doc(?:umento)?)\s*\.?\s*(n[ºo°]\s*)?(\d+)", Path(nombre).stem)
    titulo = f"DOC {m.group(3)}" if m else Path(nombre).stem[:60]
    if re.search(r"\bINFORME\b|\bPERITO\b|\bPERICIAL\b|\bDICTAMEN\b", t):
        return titulo, "Pericial"
    return titulo, "Documental"


def ultimo_firmado(carpeta: Path, principal: str, desde_ts: float = 0) -> Path | None:
    """El PDF firmado más reciente de la carpeta, guardado después de archivar el escrito
    (la firma del abogado que ya traía el original no cuenta)."""
    candidatos = []
    for f in carpeta.glob("*.pdf"):
        n = normalizar(f.name)
        if n.startswith(("RESGUARDO", "DOC", "ANEXO", "PODER")):
            continue
        try:
            if f.stat().st_mtime <= desde_ts + 2:
                continue
            if pdf_firmado(f.read_bytes()):
                candidatos.append(f)
        except OSError:
            pass
    if not candidatos:
        return None
    candidatos.sort(key=lambda f: (f.name == principal, f.stat().st_mtime), reverse=True)
    return candidatos[0]


def preparar(escrito, ajustes) -> FichaPortal:
    """escrito: almacen.Escrito; ajustes: almacen.Ajustes"""
    f = FichaPortal(tipo_escrito=escrito.tipo_escrito)
    carpeta = Path(escrito.carpeta)
    principal = carpeta / escrito.principal if escrito.principal else None
    texto = texto_pdf(principal.read_bytes(), 3) if principal and principal.exists() else ""

    m = re.search(r"([A-Za-zÁÉÍÓÚáéíóúñÑ ]*?)\s*(\d+)\s*/\s*(\d{4})", escrito.procedimiento)
    if m:
        f.tipo_procedimiento = m.group(1).strip()
        f.numero = m.group(2).zfill(7)
        f.anio = m.group(3)
    f.tipo_organo = tipo_organo(escrito.organo)
    f.partido = partido_judicial(escrito.organo)
    f.plaza = escrito.plaza
    f.seccion = seccion(escrito.organo)

    f.cliente = cliente_del_escrito(texto) or (escrito.demandado if "contest" in normalizar(escrito.tipo_escrito).lower() else "")
    if not f.cliente:
        f.avisos.append("No sé a qué cliente representas en este escrito: añade el interviniente a mano.")
    poder = buscar_poder(Path(ajustes.carpeta_escritos), f.cliente)
    if poder:
        f.identificacion = identificacion_en(texto_pdf(poder.read_bytes(), 4), f.cliente)
    if not f.identificacion:
        f.identificacion = identificacion_en(texto, f.cliente)
    f.persona_juridica = es_juridica(f.cliente, f.identificacion)
    if f.cliente and not f.identificacion:
        f.avisos.append(f"No he encontrado el CIF/NIF de {f.cliente}: escríbelo tú en el interviniente.")
    if f.cliente and not poder:
        f.avisos.append(f"No he encontrado el poder de {f.cliente} en la carpeta de escritos.")

    f.letrado, f.letrado_colegiado = letrado_del_escrito(texto)
    if not f.letrado_colegiado:
        f.avisos.append("No he encontrado el letrado y su nº de colegiado en el escrito.")
    f.procurador = getattr(ajustes, "procurador_nombre", "")
    f.procurador_colegiado = getattr(ajustes, "procurador_colegiado", "")

    f.titulo = (escrito.tipo_escrito or "Escrito").upper()
    firmado = ultimo_firmado(carpeta, escrito.principal, escrito.recibido_ts)
    f.documento = firmado or principal
    f.documento_firmado = firmado is not None
    if not firmado:
        f.avisos.append("El escrito aún no está firmado por ti: fírmalo en Adobe (Utilizar un certificado → "
                        "Firmar digitalmente), guárdalo en la carpeta y vuelve a pulsar Presentar. "
                        "Si sigues ahora, súbelo tú en Documentación.")

    if poder:
        f.anexos.append(Anexo(poder, "PODER NOTARIAL", "Poder"))
    for nombre in escrito.anexos:
        ruta = carpeta / nombre
        if ruta.suffix.lower() != ".pdf" or not ruta.exists() or ruta == f.documento:
            continue
        if normalizar(ruta.name).startswith(("FICHA", "RESGUARDO")):
            continue
        titulo, cat = categoria_anexo(nombre, texto_pdf(ruta.read_bytes(), 1))
        f.anexos.append(Anexo(ruta, titulo, cat))
    return f
