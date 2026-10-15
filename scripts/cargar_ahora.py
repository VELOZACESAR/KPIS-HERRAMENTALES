"""Revisa y carga los Excel una vez (sin web). Útil para probar rutas o forzar un cargue:
    python scripts/cargar_ahora.py            -> solo lo que cambió
    python scripts/cargar_ahora.py --forzar   -> recarga todo aunque no haya cambiado
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tablero import config, tablero  # noqa: E402
from tablero.ingesta import Ingestor, estado_fuentes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
for clave in config.FUENTES:
    print(f"{clave:12} -> {config.ruta_fuente(clave)}")
cargadas = Ingestor().revisar(forzar="--forzar" in sys.argv)
print("Cargadas:", cargadas or "ninguna (sin cambios)")
tablero.guardar_foto()
for fuente, e in estado_fuentes().items():
    print(f"{fuente:12} {e['estado']:6} {e['filas'] or '':>6} filas  {e['mensaje'] or ''}")
