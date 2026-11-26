"""Extracción de datos de un escrito judicial en PDF, sin IA: solo texto y expresiones regulares.

Uso rápido:
    from presentador.parser import extraer_de_pdf
    datos = extraer_de_pdf("escrito.pdf")
    datos.numero, datos.anio, datos.organo, datos.titulo

Todas las funciones de texto (``extraer_datos``) se pueden probar sin PDF.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    """Mayúsculas, sin tildes y con 'º/ª' como 'O/A'. Conserva la longitud de cada línea
    lo suficiente como para buscar con regex; no sirve para mostrar."""
    t = texto.replace("º", "o").replace("ª", "a").replace("°", "o")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.upper()


def _espacios(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class DatosEscrito:
    organo: str = ""               # "1ª Instancia nº 12 de Bilbao"
    tipo_procedimiento: str = ""   # "Juicio Verbal"
    numero: str = ""               # "1379" (sin ceros a la izquierda)
    anio: str = ""                 # "2026"
    titulo: str = ""               # "PROPOSICIÓN DE PRUEBA"
    titulo_original: str = ""      # "ESCRITO DE PROPOSICIÓN DE PRUEBA"
    procurador: str = ""
    letrado: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def numero_completo(self) -> str:
        """Formato de Avantius con ceros: '0001379/2026'."""
        return f"{int(self.numero):07d}/{self.anio}" if self.numero and self.anio else ""

    @property
    def completo(self) -> bool:
        return bool(self.organo and self.numero and self.anio and self.titulo)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["numero_completo"] = self.numero_completo
        return d


# ---------------------------------------------------------------------------
# Órgano judicial
# ---------------------------------------------------------------------------

# Línea que abre el escrito: "AL JUZGADO ...", "A LA AUDIENCIA PROVINCIAL ...", "AL TRIBUNAL ..."
_RE_DESTINATARIO = re.compile(
    r"^\s*(?:AL|A\s+LA|A\s+LA\s+SALA\s+DEL?|AL\s+ILMO\.?|A\s+LA\s+ILMA\.?)\s+"
    r"(?P<resto>(?:JUZGADO|TRIBUNAL|AUDIENCIA|SALA|SECCION|SECRETARIA|SERVICIO\s+COMUN)\b.*)$"
)
_PALABRAS_MINUSCULA = {"de", "del", "la", "las", "lo", "los", "e", "y", "a", "en", "nº"}


def _formatear_organo(texto_norm: str) -> str:
    """'JUZGADO DE PRIMERA INSTANCIA NO 12 DE BILBAO' -> '1ª Instancia nº 12 de Bilbao'."""
    t = _espacios(texto_norm).strip(" ,.:;")
    t = re.sub(r"^(?:JUZGADO|TRIBUNAL)\s+(?=DE\s+(?:PRIMERA|1A|INSTRUCCION|LO\b|VIOLENCIA|MENORES|VIGILANCIA))", "", t)
    t = re.sub(r"^DE\s+", "", t)
    t = re.sub(r"\bPRIMERA\s+INSTANCIA\b", "1A INSTANCIA", t)
    t = re.sub(r"\b1A\.?\s*INST(?:ANCIA|\.)?\b", "1A INSTANCIA", t)
    # Número: "Nº 12", "N.º 12", "NUM. 12", "NUMERO 12", "NO 12", "N 12"
    t = re.sub(r"\b(?:N\.?\s*O\.?|NUM\.?|NUMERO|N)\s*[:.]?\s*(?=\d)", "NUMERO ", t)
    palabras = []
    for p in t.split(" "):
        if p == "NUMERO":
            palabras.append("nº")
        elif re.fullmatch(r"\d+A", p):
            palabras.append(p[:-1] + "ª")
        elif re.fullmatch(r"\d+O", p):
            palabras.append(p[:-1] + "º")
        elif p.lower() in _PALABRAS_MINUSCULA and palabras:
            palabras.append(p.lower())
        else:
            palabras.append("-".join(x.capitalize() for x in p.split("-")))
    res = " ".join(palabras)
    for sin, con in (("Instruccion", "Instrucción"), ("Seccion", "Sección"), ("Ejecucion", "Ejecución"),
                     ("Comun", "Común"), ("Penitenciaria", "Penitenciaria"), ("Gasteiz", "Gasteiz")):
        res = res.replace(sin, con)
    return res


def extraer_organo(texto: str) -> str:
    """Busca la línea 'AL JUZGADO ...' y, si sigue en la línea siguiente, la une."""
    return _buscar_organo(texto)[0]


def _buscar_organo(texto: str) -> tuple[str, set[int]]:
    """(órgano formateado, índices de las líneas que ocupa)."""
    lineas = [normalizar(l) for l in texto.splitlines()]
    for i, linea in enumerate(lineas[:60]):  # siempre está al principio
        m = _RE_DESTINATARIO.match(linea)
        if not m:
            continue
        partes = [m.group("resto")]
        usadas = {i}
        # Si la línea no lleva número ni localidad ("AL JUZGADO" solo, o "... DE PRIMERA INSTANCIA"),
        # el resto está debajo ("Texto bajo AL JUZGADO").
        j = i + 1
        while j < len(lineas) and len(partes) < 3:
            siguiente = lineas[j].strip()
            if not siguiente:
                j += 1
                continue
            ya_completo = re.search(r"\d", " ".join(partes)) and re.search(r"\bDE\s+[A-Z\-]{3,}\s*$", " ".join(partes))
            if ya_completo or _parece_inicio_de_otra_cosa(siguiente):
                break
            partes.append(siguiente)
            usadas.add(j)
            j += 1
        return _formatear_organo(" ".join(partes)), usadas
    return "", set()


def _parece_inicio_de_otra_cosa(linea_norm: str) -> bool:
    return bool(re.match(
        r"(AUTOS|PROCEDIMIENTO|PROC\.|N\.?O\s+DE\s+AUTOS|JUICIO|ESCRITO|D\.|DON|DONA|DA\.|D\.A|EL\s+PROCURADOR|"
        r"LA\s+PROCURADORA|PARTE|DEMANDA|RECURSO|ROLLO|EJECUCION|ASUNTO|REF)", linea_norm))


# Claves para comparar el órgano del PDF con el de la tabla de Avantius
# ("1ª Instancia nº 12 de Bilbao" frente a "1ª Ins. 12 Dec. Of. Bilbao (Bilbao)").
_JURISDICCIONES = [
    ("1INS-INSTR", r"1A\s*INS[A-Z.]*\s*(?:E|Y|/)\s*INSTR|PRIMERA\s+INSTANCIA\s+E\s+INSTRUCCION|MIXTO"),
    ("VSM", r"VIOLENCIA\s+SOBRE\s+LA\s+MUJER|VIOL[A-Z.]*\s*MUJER|\bVSM\b|\bVIOGEN\b"),
    ("1INS", r"1A\s*INS|PRIMERA\s+INSTANCIA|\bCIVIL\b|FAMILIA"),
    ("INSTR", r"INSTRUCCION|\bINSTR\b|\bINS\.?\s*INSTR"),
    ("MERC", r"MERCANTIL|\bMERC\b"),
    ("SOCIAL", r"\bSOCIAL\b|\bSOC\b|\bLABORAL\b"),
    ("CA", r"CONTENCIOSO|\bCONT\b|\bC-?A\b"),
    ("PENAL", r"\bPENAL\b|\bPEN\b"),
    ("MENORES", r"MENORES|\bMEN\b"),
    ("VIGPEN", r"VIGILANCIA"),
    ("AP", r"AUDIENCIA\s+PROVINCIAL|\bAP\b|\bA\.P\.?\b"),
    ("TSJ", r"TRIBUNAL\s+SUPERIOR|\bTSJ\b"),
]


@dataclass(frozen=True)
class ClaveOrgano:
    jurisdiccion: str   # "1INS", "SOCIAL", ...
    numero: str         # "12"
    localidad: str      # "BILBAO"


def clave_organo(texto: str) -> ClaveOrgano:
    t = normalizar(texto)
    jur = ""
    for clave, patron in _JURISDICCIONES:
        if re.search(patron, t):
            jur = clave
            break
    # Localidad: entre paréntesis al final (formato Avantius) o el último "DE X".
    loc = ""
    m = re.search(r"\(([^)]+)\)\s*$", t)
    if m:
        loc = m.group(1)
    else:
        m = re.search(r"\bDE\s+([A-Z][A-Z\- ]*?)\s*$", t)
        if m and not re.search(r"INSTANCIA|INSTRUCCION|MERCANTIL|SOCIAL|LO\b", m.group(1)):
            loc = m.group(1)
    loc = _espacios(re.sub(r"[^A-Z ]", " ", loc))
    # Número del juzgado: el primero que no sea el ordinal "1A" de "1ª Instancia".
    sin_ordinales = re.sub(r"\b\d+\s*[AO]\b\.?", " ", t)
    sin_ordinales = re.sub(r"\(.*?\)", " ", sin_ordinales)
    m = re.search(r"(?:PLAZA|SECCION|N\.?\s*O\.?|NUMERO|NUM\.?)?\s*\b(\d{1,3})\b(?!\s*/)", sin_ordinales)
    num = str(int(m.group(1))) if m else ""
    return ClaveOrgano(jur, num, loc)


def coincide_organo(organo_pdf: str, organo_portal: str) -> bool:
    """¿Es el mismo juzgado? Compara tipo, número y (si ambos la tienen) localidad."""
    a, b = clave_organo(organo_pdf), clave_organo(organo_portal)
    if not (a.numero and b.numero) or a.numero != b.numero:
        return False
    if a.jurisdiccion and b.jurisdiccion and a.jurisdiccion != b.jurisdiccion:
        return False
    if a.localidad and b.localidad and not (a.localidad in b.localidad or b.localidad in a.localidad):
        return False
    return True


def elegir_organo(organo_pdf: str, candidatos: list[str]) -> int | None:
    """Índice del único candidato que coincide con el órgano del PDF, o None si hay 0 o varios."""
    aciertos = [i for i, c in enumerate(candidatos) if coincide_organo(organo_pdf, c)]
    return aciertos[0] if len(aciertos) == 1 else None


# ---------------------------------------------------------------------------
# Procedimiento: tipo, número y año
# ---------------------------------------------------------------------------

# Forma normalizada -> forma para mostrar. Las más largas primero al construir la regex.
TIPOS_PROCEDIMIENTO = {
    "JUICIO VERBAL": "Juicio Verbal",
    "JUICIO ORDINARIO": "Juicio Ordinario",
    "PROCEDIMIENTO ORDINARIO": "Procedimiento Ordinario",
    "PROCEDIMIENTO VERBAL": "Juicio Verbal",
    "VERBAL DESAHUCIO": "Verbal Desahucio",
    "VERBAL": "Juicio Verbal",
    "ORDINARIO": "Procedimiento Ordinario",
    "MONITORIO": "Monitorio",
    "PROCESO MONITORIO": "Monitorio",
    "JUICIO CAMBIARIO": "Juicio Cambiario",
    "EJECUCION DE TITULOS JUDICIALES": "Ejecución de Títulos Judiciales",
    "EJECUCION DE TITULOS NO JUDICIALES": "Ejecución de Títulos No Judiciales",
    "EJECUCION HIPOTECARIA": "Ejecución Hipotecaria",
    "EJECUCION": "Ejecución",
    "ETJ": "Ejecución de Títulos Judiciales",
    "ENJ": "Ejecución de Títulos No Judiciales",
    "DIVORCIO CONTENCIOSO": "Divorcio Contencioso",
    "DIVORCIO DE MUTUO ACUERDO": "Divorcio de Mutuo Acuerdo",
    "DIVORCIO": "Divorcio",
    "MODIFICACION DE MEDIDAS": "Modificación de Medidas",
    "MEDIDAS PROVISIONALES": "Medidas Provisionales",
    "CONCURSO ABREVIADO": "Concurso Abreviado",
    "CONCURSO ORDINARIO": "Concurso Ordinario",
    "CONCURSO": "Concurso",
    "INCIDENTE CONCURSAL": "Incidente Concursal",
    "DILIGENCIAS PREVIAS": "Diligencias Previas",
    "PROCEDIMIENTO ABREVIADO": "Procedimiento Abreviado",
    "JUICIO SOBRE DELITOS LEVES": "Juicio sobre Delitos Leves",
    "RECURSO DE APELACION": "Recurso de Apelación",
    "ROLLO DE APELACION": "Rollo de Apelación",
    "DESPIDO": "Despido",
    "SEGURIDAD SOCIAL": "Seguridad Social",
    "EXPEDIENTE DE DOMINIO": "Expediente de Dominio",
    "JURA DE CUENTAS": "Jura de Cuentas",
    "TASACION DE COSTAS": "Tasación de Costas",
}

_RE_TIPOS = "|".join(sorted((re.escape(k) for k in TIPOS_PROCEDIMIENTO), key=len, reverse=True))
# Número/año que no forme parte de una fecha (12/05/2026) ni de un número más largo.
_RE_NUM_ANIO = r"(?<![\d/.])(?P<num>\d{1,7})\s*/\s*(?P<anio>(?:19|20)\d{2}|\d{2})(?![\d/])"
_RE_NUM_PREFIJO = r"(?:N\.?\s*O\.?|NUM\.?|NUMERO|N)?\s*[:.\-]?\s*"
_PATRONES_PROC = [
    # "Autos Juicio Verbal 1379/2026", "Procedimiento: Ordinario nº 12/2026", "AUTOS Nº 1379/2026"
    re.compile(rf"(?:AUTOS|PROCEDIMIENTO|PROC\.|N\.?O\s+DE\s+AUTOS|ASUNTO)\s*[:.\-]?\s*"
               rf"(?:DE\s+)?(?P<tipo>{_RE_TIPOS})?\s*{_RE_NUM_PREFIJO}{_RE_NUM_ANIO}"),
    # "Juicio Verbal 1379/2026" sin la palabra autos
    re.compile(rf"(?P<tipo>{_RE_TIPOS})\s*{_RE_NUM_PREFIJO}{_RE_NUM_ANIO}"),
]


def extraer_procedimiento(texto: str) -> tuple[str, str, str]:
    """(tipo para mostrar, número sin ceros, año de 4 cifras) o ('', '', '')."""
    t = normalizar(texto)
    for patron in _PATRONES_PROC:
        m = patron.search(t)
        if m:
            tipo = _espacios(m.group("tipo") or "")
            anio = m.group("anio")
            anio = anio if len(anio) == 4 else f"20{anio}"
            return TIPOS_PROCEDIMIENTO.get(tipo, tipo.title()), str(int(m.group("num"))), anio
    return "", "", ""


# ---------------------------------------------------------------------------
# Título del escrito
# ---------------------------------------------------------------------------

# Encabezados en mayúsculas que NO son el título.
_NO_TITULO = re.compile(
    r"^(AL|A\s+LA|AUTOS|PROCEDIMIENTO|PROC\.|JUZGADO|TRIBUNAL|AUDIENCIA|DIGO|DIGE|EXPON(E|GO|EMOS)|"
    r"SUPLIC[OA]|SOLICITO|OTROSI|HECHOS?|FUNDAMENTOS?|ALEGACIONES|ANTECEDENTES|PRIMER[OA]?|SEGUND[OA]|"
    r"TERCER[OA]?|CUART[OA]|QUINT[OA]|SEXT[OA]|SEPTIM[OA]|OCTAV[OA]|NOVEN[OA]|DECIM[OA]|UNIC[OA]|"
    r"PROCURADORA?|LETRADA?|ABOGADA?|FDO|EN\s+\w+\s*,?\s+A\s+\d|PARTE|DEMANDANTE|DEMANDADA?O?|"
    r"I{1,3}|IV|V|VI{0,3}|[IVX]+\.)\b"
)
_PREFIJOS_TITULO = re.compile(r"^(ESCRITO\s+(DE|DEL|DE\s+LA|POR\s+EL\s+QUE\s+SE|SOLICITANDO|INTERPONIENDO)?\s*)", re.I)
_CONECTORES_FINAL = re.compile(r"\b(Y|E|DE|DEL|LA|LAS|LOS|EL|A|AL|EN|POR|PARA|CON|SOBRE|,)\s*$")


def _es_linea_mayusculas(linea: str) -> bool:
    letras = [c for c in linea if c.isalpha()]
    if len(letras) < 6:
        return False
    return sum(1 for c in letras if c.isupper()) / len(letras) >= 0.9


def extraer_titulo(texto: str, saltar: set[int] | None = None) -> tuple[str, str]:
    """(título limpio, título tal cual). Primera línea en mayúsculas que empieza por 'ESCRITO';
    si no hay, la primera línea en mayúsculas que no sea encabezado. ``saltar`` son las
    líneas del bloque «AL JUZGADO ...» (por defecto se calculan)."""
    if saltar is None:
        saltar = _buscar_organo(texto)[1]
    lineas = [l.strip() for l in texto.splitlines()]
    candidatas: list[int] = []
    for i, l in enumerate(lineas[:120]):
        n = normalizar(l)
        if not _es_linea_mayusculas(l) or _NO_TITULO.match(n):
            continue
        if i in saltar:
            continue  # bloque "AL JUZGADO ..."
        if re.search(r"\d+\s*/\s*\d{2,4}", n):
            continue  # línea de autos
        candidatas.append(i)
    if not candidatas:
        return "", ""
    elegida = next((i for i in candidatas if normalizar(lineas[i]).startswith("ESCRITO")), candidatas[0])
    partes = [lineas[elegida]]
    j = elegida + 1
    while j in candidatas and _CONECTORES_FINAL.search(normalizar(partes[-1])):
        partes.append(lineas[j])
        j += 1
    original = _espacios(" ".join(partes)).strip(" .:;")
    limpio = _PREFIJOS_TITULO.sub("", original).strip(" .:;") or original
    return limpio, original


# ---------------------------------------------------------------------------
# Procurador y letrado
# ---------------------------------------------------------------------------

_RE_FDO = re.compile(r"\bF(?:do|DO|irmado)\s*[.:]\s*[:.]?\s*", re.I)
_TRATAMIENTO = r"(?:D\.ª|Dª\.?|D\.|Dña\.?|Doña|Don)\s+"
_RE_PROCURADOR_CUERPO = re.compile(
    rf"{_TRATAMIENTO}(?P<nombre>[A-ZÁÉÍÓÚÑÜ][^,\n]{{3,80}}?)\s*,\s*(?:Procurador|PROCURADOR)", re.UNICODE)
_RE_LETRADO_CUERPO = re.compile(
    rf"(?:direcci[oó]n\s+(?:letrada|t[eé]cnica)|asistid[oa]\s+(?:por|del?)|Letrad[oa]\s*:)\s*"
    rf"(?:de\s+)?(?:l\s+|la\s+)?(?:Letrad[oa]\s+|Abogad[oa]\s+)?(?:{_TRATAMIENTO})?(?P<nombre>[A-ZÁÉÍÓÚÑÜ][^,.;\n]{{3,80}})",
    re.IGNORECASE | re.UNICODE)


def _limpiar_nombre(nombre: str) -> str:
    nombre = re.sub(rf"^{_TRATAMIENTO}", "", nombre.strip(), flags=re.I)
    nombre = re.sub(r"\s*(Procurador[a]?|Letrad[oa]|Abogad[oa]|Col\.?\s*n?º?\s*\d+.*)$", "", nombre, flags=re.I)
    return _espacios(nombre).strip(" .,:;")


def extraer_firmantes(texto: str) -> tuple[str, str]:
    """(procurador, letrado). Primero por las líneas 'Fdo.:' del final (columna izquierda =
    procurador, salvo que el encabezado de columnas diga 'LETRADO ... PROCURADOR'), y si no
    aparecen, por la comparecencia del cuerpo ('D. X, Procurador...', 'dirección letrada de...')."""
    lineas = texto.splitlines()
    fdos: list[str] = []
    orden_letrado_primero = False
    for linea in lineas:
        n = normalizar(linea)
        if re.search(r"\bLETRAD[OA]\b.*\bPROCURADOR", n) and not re.search(r"[a-z]", linea):
            orden_letrado_primero = True
        if re.search(r"\bPROCURADOR[A]?\b.*\bLETRAD[OA]\b", n) and not re.search(r"[a-z]", linea):
            orden_letrado_primero = False
        trozos = _RE_FDO.split(linea)
        if len(trozos) > 1:
            fdos.extend(t for t in (_limpiar_nombre(x) for x in trozos[1:]) if t)
    procurador = letrado = ""
    if len(fdos) >= 2:
        procurador, letrado = (fdos[-1], fdos[-2]) if orden_letrado_primero else (fdos[-2], fdos[-1])
    elif len(fdos) == 1:
        procurador = fdos[0]
    m = _RE_PROCURADOR_CUERPO.search(texto)
    if m and not procurador:
        procurador = _limpiar_nombre(m.group("nombre"))
    m = _RE_LETRADO_CUERPO.search(texto)
    if m and not letrado:
        letrado = _limpiar_nombre(m.group("nombre"))
    return procurador, letrado


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def extraer_datos(texto: str) -> DatosEscrito:
    d = DatosEscrito()
    d.organo, lineas_organo = _buscar_organo(texto)
    d.tipo_procedimiento, d.numero, d.anio = extraer_procedimiento(texto)
    d.titulo, d.titulo_original = extraer_titulo(texto, lineas_organo)
    d.procurador, d.letrado = extraer_firmantes(texto)
    if not d.organo:
        d.avisos.append("No encuentro el juzgado (línea «AL JUZGADO ...»).")
    if not d.numero:
        d.avisos.append("No encuentro el número y año del procedimiento.")
    if not d.titulo:
        d.avisos.append("No encuentro el título del escrito.")
    if not d.procurador:
        d.avisos.append("No encuentro el nombre del procurador («Fdo.: ...»).")
    return d


def texto_de_pdf(ruta: str | Path) -> str:
    """Texto seleccionable de todas las páginas (pdfplumber)."""
    import pdfplumber
    with pdfplumber.open(str(ruta)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def extraer_de_pdf(ruta: str | Path) -> DatosEscrito:
    texto = texto_de_pdf(ruta)
    if len(texto.strip()) < 50:
        d = DatosEscrito()
        d.avisos.append("El PDF no tiene texto seleccionable (¿es un escaneo?).")
        return d
    return extraer_datos(texto)
