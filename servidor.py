"""Servidor del tablero de Herramentales: web + vigilancia de los Excel + foto diaria.

    python servidor.py            -> sirve en http://<este-pc>:8050
    python servidor.py --una-vez  -> solo revisa/carga los Excel y guarda la foto del día (sin web)
"""
import logging
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from tablero import config, tablero
from tablero.ingesta import Ingestor


def configurar_logs():
    config.CARPETA_LOGS.mkdir(exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    archivo = RotatingFileHandler(config.CARPETA_LOGS / "servidor.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    archivo.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(archivo)
    if sys.stdout and sys.stdout.isatty():
        consola = logging.StreamHandler()
        consola.setFormatter(formato)
        raiz.addHandler(consola)
    logging.getLogger("waitress").setLevel(logging.WARNING)


def despues_de_cargar(_fuentes):
    tablero.invalidar()
    tablero.guardar_foto()


def foto_periodica():
    while True:
        time.sleep(3600)
        try:
            tablero.guardar_foto()
        except Exception:
            logging.exception("Foto periódica")


def main():
    configurar_logs()
    log = logging.getLogger("servidor")
    ingestor = Ingestor(al_cargar=despues_de_cargar)
    if "--una-vez" in sys.argv:
        ingestor.revisar()
        tablero.guardar_foto()
        return 0

    from waitress import serve
    from tablero.web import crear_app

    ingestor.iniciar(config.SEGUNDOS_REVISION)
    threading.Thread(target=foto_periodica, name="foto", daemon=True).start()
    threading.Thread(target=lambda: tablero.obtener(ingestor.version), name="precalentar", daemon=True).start()
    nombre = socket.gethostname()
    log.info("Tablero en http://%s:%s (y http://localhost:%s)", nombre, config.PUERTO, config.PUERTO)
    try:
        serve(crear_app(ingestor), host=config.HOST, port=config.PUERTO, threads=8, ident="tablero-herramentales")
    except OSError as e:
        log.error("No se pudo abrir el puerto %s (¿ya hay otro servidor corriendo?): %s", config.PUERTO, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
