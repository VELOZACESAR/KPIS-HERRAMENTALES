"""Compara cada Excel con lo cargado en la base: filas por tabla y hora de guardado vs. último cargue bueno.

    python scripts/validar_contra_excel.py
"""
import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tablero import config, db  # noqa: E402
from tablero.ingesta import LECTORES  # noqa: E402

problemas = 0
for clave in config.FUENTES:
    ruta = config.ruta_fuente(clave)
    if ruta is None:
        print(f"✖ {clave:20} no encontrado en OneDrive")
        problemas += 1
        continue
    guardado = dt.datetime.fromtimestamp(ruta.stat().st_mtime).replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / ruta.name
        shutil.copyfile(ruta, copia)
        tablas, _ = LECTORES[clave](copia)
    ultimo = db.consultar("SELECT TOP 1 modificado, fin FROM cesar.cargue WHERE fuente = ? AND estado = 'ok' ORDER BY id DESC", clave)
    cargado = ultimo[0]["modificado"] if ultimo else None
    detalle = []
    ok = cargado is not None and cargado >= guardado
    for tabla, (_, filas) in tablas.items():
        en_bd = db.consultar(f"SELECT COUNT(*) AS n FROM {tabla}")[0]["n"]
        ok &= en_bd == len(filas)
        detalle.append(f"{tabla.split('.')[-1]} {len(filas)}/{en_bd}")
    problemas += not ok
    print(f"{'✓' if ok else '✖'} {clave:20} guardado {guardado:%d/%m %H:%M} · cargado {cargado:%d/%m %H:%M} · "
          f"excel/base: {', '.join(detalle)}" if cargado else f"✖ {clave:20} nunca cargado")
sys.exit(problemas)
