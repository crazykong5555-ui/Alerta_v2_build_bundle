GENERA UN .EXE PARA alerta_v2.py - INSTRUCCIONES

Resumen:
  No puedo crear un .exe Windows directamente desde este entorno de ejecución de forma confiable.
  Te incluyo los archivos necesarios para que lo generes en tu máquina Windows (o en CI):
  - requirements.txt
  - build_windows.bat
  - build_with_wine.sh (guía)
  - alerta_v2.py (tu script)

Pasos (recomendado: en Windows, PowerShell):
1) Abrir PowerShell en la carpeta donde descomprimiste este bundle.
2) Crear un entorno virtual:
   python -m venv venv
   .\venv\Scripts\Activate.ps1    (o .\venv\Scripts\activate.bat en cmd)
3) Instalar dependencias y PyInstaller:
   pip install -r requirements.txt
   pip install pyinstaller
4) Ejecutar el script de compilación:
   .\build_windows.bat
   Esto lanzará PyInstaller y generará un único archivo ejecutable en la carpeta "dist".
5) Probar el .exe en otra máquina Windows (idealmente en una VM) para confirmar que funciona y que todos los módulos necesarios están incluidos.

Consejos para problemas frecuentes:
- Si faltan datos (archivos .geojson, .csv), decide si quieres incluirlos en el exe o que se creen en tiempo de ejecución en la carpeta donde corra el exe.
- Para ocultar la consola (si tu app usa GUI y no necesitas ver la consola), usa la opción --noconsole en pyinstaller (está comentada en build_windows.bat).
- Si tu app requiere archivos extra, agrega --add-data "ruta\a\archivo;." a la línea de pyinstaller. En PowerShell usa comillas dobles correctamente.
- Si usas pandas, PyInstaller a veces necesita hooks adicionales; ejecutar la app y revisar errores en consola ayuda a identificar missing modules.

Alternativas:
- Usar una máquina Windows / GitHub Actions CI para generar el .exe automáticamente.
- Empaquetar la app como un contenedor Docker (si no necesitas .exe) o crear un instalador con Inno Setup.

Si quieres, puedo:
- Preparar un archivo .spec de PyInstaller más específico (por ejemplo para incluir archivos adicionales).
- Crear un workflow de GitHub Actions que genere el .exe en Windows y te lo devuelva (requiere que autorices/permitas la acción).
- Generar el ZIP que ya creé para descarga, con estos archivos listos.

Archivos incluidos en este bundle:
- alerta_v2.py
- requirements.txt
- build_windows.bat
- build_with_wine.sh
- README_BUILD.txt (esta guía)

