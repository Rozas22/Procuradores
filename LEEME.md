# Escritos Procura

Aplicación de escritorio para Windows que ahorra a procuradores el trabajo repetitivo de cada escrito:

1. **Arrastras** el correo (de Outlook, o un .eml descargado de Gmail) o los PDFs a la ventana.
2. La app lee la primera página del escrito y saca **tipo de escrito, procedimiento, juzgado, plaza y partes**.
3. Crea o reutiliza la **carpeta del procedimiento** (formato configurable: `1265.26`, `1265-2026`...) y guarda escrito y anexos sin sobrescribir nada.
4. Muestra los datos con botones **Copiar** para pegarlos en el portal, y un botón **Ir al portal**.
5. El estado se actualiza solo: **Firmado** cuando aparece un PDF firmado en la carpeta, **Presentado** cuando aparece el `RESGUARDO`.

Si no está segura de algún dato (no encuentra el número, o un anexo habla de otro procedimiento), te enseña los datos para corregirlos antes de archivar.

Todo se queda en el ordenador: ajustes y lista en `%APPDATA%\EscritosProcura`. No se conecta a internet.

## Crear el instalador

**Opción A, en tu PC:** instala Python 3.12 (marcando "Add to PATH") e Inno Setup 6 (`winget install JRSoftware.InnoSetup`), y haz doble clic en `construir_windows.bat`. El instalador sale en `dist\EscritosProcura-Instalador-0.1.0.exe`.

**Opción B, automático con GitHub:** al subir este código a un repositorio de GitHub, el flujo `.github/workflows/instalador-windows.yml` pasa las pruebas y genera el instalador en cada cambio (pestaña Actions → artefacto).

El instalador no pide permisos de administrador y crea accesos en el menú Inicio y el escritorio. Mientras no esté firmado con un certificado de firma de código, Windows mostrará "Windows protegió su PC": pulsa "Más información" → "Ejecutar de todas formas".

## Desarrollo

```
pip install -r requirements.txt pytest
python -m escritos_procura      # abre la app
python -m pytest tests          # pruebas (con datos inventados)
```

- `escritos_procura/motor.py`: lectura de correos y PDFs, extracción de datos, carpetas.
- `escritos_procura/almacen.py`: ajustes y lista de escritos (SQLite).
- `escritos_procura/servicio.py`: archivar y refrescar estados.
- `escritos_procura/gui.py`: ventana, arrastrar y soltar, diálogos.

## Actualizaciones

La app busca versiones nuevas al abrirse y muestra un botón verde "Actualizar". Para publicar una versión: sube `__version__` en `escritos_procura/__init__.py`, añade `notas/vX.Y.Z.md` con las novedades y publica una Release `vX.Y.Z` en GitHub. Actions genera el instalador y lo adjunta a esa Release.

## Próximos pasos

- Asistente del portal Justizia.eus (rellenar el formulario y parar antes de Enviar).
- Firma por lotes con el certificado instalado.
- LexNET.
- Conexión directa con Outlook / Gmail.
