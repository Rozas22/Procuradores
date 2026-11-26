# Presentador de escritos en Avantius

Aplicación local para Windows 11 que prepara la presentación telemática de escritos en
`https://psp.justizia.eus`: lee el PDF, lo firma con el certificado del procurador y
(en próximas iteraciones) rellena el formulario de Avantius y archiva el justificante.
Sin IA ni servicios externos: expresiones regulares, firma local y automatización del navegador.

Es un proyecto nuevo, independiente de la app «Escritos Procura» de la raíz del repositorio,
que sigue funcionando igual.

## Estado

| Iteración | Contenido | Estado |
|---|---|---|
| 1 | Estructura, `parser.py` (extracción), `mapeo.py` (tipo de escrito), `signer.py` (firma PAdES) | **Hecha** |
| 2 | `avantius_bot.py` (Playwright, pausa antes de «Enviar», justificante) + `archivo.py` | Pendiente |
| 3 | Interfaz web local (FastAPI) con Bandeja, Historial (SQLite) y Configuración | Pendiente |

## Estructura

```
presentador-avantius/
├── presentador/
│   ├── parser.py        Fase A: texto del PDF -> órgano, procedimiento, título, procurador, letrado
│   ├── mapeo.py         Fase A: título -> opción del desplegable «Tipo de Escrito*»
│   ├── signer.py        Fase B: firma PAdES con el certificado de Windows y sello visible
│   ├── config.py        ajustes del usuario (%APPDATA%\PresentadorAvantius\ajustes.json)
│   ├── ejemplo.py       escrito y certificado de PRUEBA para ensayar
│   └── __main__.py      órdenes: extraer, certificados, firmar, comprobar, ejemplo
│   (iteración 2: avantius_bot.py, archivo.py · iteración 3: web/, historial.py)
├── config/
│   └── mapeo_escritos.json   reglas palabra clave -> Tipo de Escrito
├── tests/               pruebas unitarias (datos inventados)
├── instalar.bat         crea el entorno de Python e instala dependencias
└── probar_iteracion1.bat     pruebas + ejemplo completo
```

## Cómo probarlo (Windows 11)

1. Instala **Python 3.11 o superior** desde python.org marcando «Add python.exe to PATH».
2. Descarga el repositorio (botón verde *Code → Download ZIP*) y descomprímelo.
3. En la carpeta `presentador-avantius`, doble clic en **`instalar.bat`** (solo la primera vez).
4. Doble clic en **`probar_iteracion1.bat`**. Hace esto:
   - pasa las pruebas automáticas;
   - crea `ejemplo\escrito_ejemplo.pdf` (un escrito inventado de 2 páginas) y `ejemplo\certificado_prueba.pfx`;
   - muestra los datos extraídos;
   - firma el ejemplo con el certificado de prueba y abre `escrito_ejemplo firmado.pdf`:
     verás el sello en la última página, bajo «Fdo.: María del Mar Ortega González»;
   - lista tus certificados reales de Windows.

### Con un escrito real

Abre una consola en la carpeta (`cmd`) y:

```
.venv\Scripts\python -m presentador extraer "C:\ruta\al\escrito.pdf"
```

Sale algo así:

```json
{
  "organo": "1ª Instancia nº 12 de Bilbao",
  "tipo_procedimiento": "Juicio Verbal",
  "numero": "1379",
  "anio": "2026",
  "titulo": "PROPOSICIÓN DE PRUEBA",
  "titulo_original": "ESCRITO DE PROPOSICIÓN DE PRUEBA",
  "procurador": "María del Mar Ortega González",
  "letrado": "Jon Etxeberria Uriarte",
  "avisos": [],
  "numero_completo": "0001379/2026",
  "tipo_escrito_avantius": "Petición de diligencia de prueba"
}
```

### Firmar con tu certificado de Windows

```
.venv\Scripts\python -m presentador certificados
.venv\Scripts\python -m presentador firmar "C:\ruta\al\escrito.pdf" --huella HUELLA_DE_LA_LISTA
.venv\Scripts\python -m presentador comprobar "C:\ruta\al\escrito firmado.pdf"
```

- Por defecto crea `escrito firmado.pdf` al lado y **no toca el original**.
- Windows te pedirá la contraseña o el PIN si tu certificado lo tiene configurado así.
- Para no escribir la huella cada vez, ponla en `%APPDATA%\PresentadorAvantius\ajustes.json`:
  `{"certificado_huella": "ABC123...", "reemplazar_original": false}`

## Cómo funciona

**Extracción (`parser.py`).** `pdfplumber` saca el texto seleccionable y se aplican regex:
- *Órgano*: la línea «AL JUZGADO …» (y la siguiente si continúa debajo), normalizada a
  «1ª Instancia nº 12 de Bilbao». `coincide_organo()` ya sabe compararlo con la columna de
  Avantius «1ª Ins. 12 Dec. Of. Bilbao (Bilbao)» por tipo, número y localidad (se usará en la iteración 2).
- *Procedimiento*: «Autos Juicio Verbal 1379/2026», «Procedimiento Ordinario 0000123/2025»,
  «Autos nº 45/26»… sin confundirlo con fechas como 12/05/2026.
- *Título*: primera línea en mayúsculas que empieza por «ESCRITO» (o, si no hay, la primera
  en mayúsculas que no sea encabezado: DIGO, HECHOS, SUPLICO…). Se quita «ESCRITO DE».
- *Procurador y letrado*: las líneas «Fdo.:» del final (izquierda = procurador, salvo que el
  encabezado diga «LETRADO  PROCURADOR») y, si faltan, la comparecencia del cuerpo.
- Si falta algo, aparece en `avisos` para revisarlo antes de presentar.

**Tipo de escrito (`mapeo.py` + `config/mapeo_escritos.json`).** Cada regla tiene palabras
clave (`contiene`, todas deben aparecer, sin importar tildes) y la opción exacta de Avantius.
Si ninguna coincide: «Escrito de trámite» y un aviso.

**Firma (`signer.py`).**
- `pyHanko` genera una firma **PAdES** (ETSI.CAdES.detached, SHA-256).
- La clave privada no sale de Windows: el programa pide a Windows (PowerShell/.NET) que
  firme el resumen con el certificado de `Cert:\CurrentUser\My`. Pensado para certificados
  de software (FNMT, Izenpe…); con tarjeta debería funcionar si su controlador está instalado.
- El sello va en la última página, bajo «Fdo.: [procurador]» (columna izquierda), sin
  invadir la columna del letrado. Si no cabe debajo, va justo encima. Si no hay «Fdo.»,
  usa la posición fija de los ajustes. Tamaño y desplazamientos se ajustan en `ajustes.json`
  → `"sello": {"ancho": 170, "alto": 45, "desplazamiento_x": 0, "desplazamiento_y": 4}`.
- Se firma como **revisión incremental**: el contenido original queda intacto (si el
  letrado ya firmó, su firma sigue siendo válida) y el sello usa una fuente TrueType
  incrustada (Arial), para que un PDF/A siga siéndolo.
- Tras firmar se comprueba que todas las firmas del PDF están íntegras; si no, no se guarda nada.

### PDF/A

La firma conserva el PDF/A del original, pero no convierte a PDF/A un PDF que no lo es
(eso rompería la firma del letrado). El programa avisa si el original no declara PDF/A:
en ese caso hay que exportarlo como PDF/A desde Word (*Guardar como → PDF → Opciones →
Compatible con ISO 19005-1 (PDF/A)*) antes de firmar.

## Pruebas

```
.venv\Scripts\python -m pytest -q tests
```

En GitHub, el flujo *Presentador Avantius (pruebas)* las pasa en Windows en cada cambio,
incluida una firma real con el almacén de certificados de Windows (con un certificado de
prueba temporal que crea y borra).
