"""Revisa que esta PC vea los Excel (por OneDrive) y la base. Sale con el número de Excel que no encontró.

    python scripts/revisar_fuentes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tablero import config, db  # noqa: E402

faltan = 0
for clave in config.FUENTES:
    ruta = config.ruta_fuente(clave)
    faltan += ruta is None
    print(f"   {clave:20} {ruta or 'NO ENCONTRADO'}")
db.consultar("SELECT 1 AS ok")
print("   base AGP_Ingenieria: ok")
sys.exit(faltan)
