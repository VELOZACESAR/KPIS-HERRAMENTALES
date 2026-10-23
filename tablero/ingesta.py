"""Vigila los Excel sincronizados con OneDrive y los carga a cesar.* cuando cambian.

Reglas:
- Solo se carga si el archivo cambió (fecha + hash). Abrir el Excel sin guardar no dispara nada.
- Se espera a que OneDrive termine de escribir (el archivo debe estar quieto unos segundos).
- Todo el cargue de una fuente va en una sola transacción: o queda completo o queda el anterior.
- Si el archivo trae muchas menos filas que el último cargue bueno, no se carga (suele ser una
  sincronización a medias o alguien borró la hoja por error) y se deja el aviso en cesar.cargue.
"""
import datetime as dt
import logging
import os
import threading
import time
from pathlib import Path

from . import config, db
from .db import ahora
from .excel import copia_temporal, sha256
from .fuentes import LECTORES

log = logging.getLogger("tablero.ingesta")

SEGUNDOS_QUIETO = 8
CAIDA_MAXIMA = 0.5
SEGUNDOS_REDESCUBRIR = 600
REVISIONES_AUSENTE = 3


class Ingestor:
    def __init__(self, al_cargar=None):
        self.al_cargar = al_cargar
        self.lock = threading.Lock()
        self.version = 0
        self.estado = {k: {"ruta": None, "visto": None, "error": None, "buscado": 0} for k in LECTORES}

    def _ruta(self, fuente):
        e = self.estado[fuente]
        if e["ruta"] and Path(e["ruta"]).exists() and time.time() - e["buscado"] < SEGUNDOS_REDESCUBRIR:
            return Path(e["ruta"])
        ruta = config.ruta_fuente(fuente)
        e["ruta"], e["buscado"] = (str(ruta) if ruta else None), time.time()
        return ruta

    def revisar(self, forzar=False):
        """Revisa todas las fuentes. Devuelve las que se cargaron."""
        cargadas = []
        with self.lock:
            for fuente in LECTORES:
                try:
                    if self._revisar_fuente(fuente, forzar):
                        cargadas.append(fuente)
                except Exception as e:
                    log.exception("Falla revisando %s", fuente)
                    self._registrar_error(fuente, None, None, f"{type(e).__name__}: {e}")
            if cargadas:
                self.version += 1
        if cargadas and self.al_cargar:
            try:
                self.al_cargar(cargadas)
            except Exception:
                log.exception("Falla después del cargue")
        return cargadas

    def _revisar_fuente(self, fuente, forzar):
        e = self.estado[fuente]
        ruta = self._ruta(fuente)
        if ruta is None or not ruta.exists():
            # OneDrive borra y vuelve a crear el archivo al sincronizar un cambio: se espera antes de dar la alarma.
            e["ausente"] = e.get("ausente", 0) + 1
            if ruta is not None and e["ausente"] < REVISIONES_AUSENTE:
                return False
            self._registrar_error(fuente, ruta, None, "No encontré el archivo. Revisa que la carpeta de SharePoint "
                                                      "esté sincronizada con OneDrive en este PC o la ruta en .env.")
            e["buscado"] = 0
            return False
        e["ausente"] = 0
        st = ruta.stat()
        firma = (st.st_mtime, st.st_size)
        if not forzar and firma == e["visto"]:
            if e["error"]:
                e["error"] = None
                self._cerrar_error(fuente, ruta, None, st.st_mtime, (self._ultimo_ok(fuente) or {}).get("filas"))
            return False
        if time.time() - st.st_mtime < SEGUNDOS_QUIETO:
            if not forzar:
                return False
            time.sleep(SEGUNDOS_QUIETO)
        copia = copia_temporal(ruta)
        try:
            huella = sha256(copia)
            ultimo = self._ultimo_ok(fuente)
            if ultimo and ultimo["sha256"] == huella and not forzar:
                e["visto"], e["error"] = firma, None
                self._cerrar_error(fuente, ruta, huella, st.st_mtime, ultimo["filas"])
                return False
            inicio = dt.datetime.now()
            try:
                tablas, extra = LECTORES[fuente](copia)
            except Exception as ex:
                e["visto"] = firma
                self._registrar_error(fuente, ruta, huella, f"No se pudo leer: {ex}", st.st_mtime)
                return False
            total = sum(len(f) for _, f in tablas.values())
            previas = ultimo["filas"] if ultimo else 0
            if previas > 50 and total < previas * CAIDA_MAXIMA and not forzar:
                e["visto"] = firma
                self._registrar_error(fuente, ruta, huella,
                                      f"El archivo trae {total} filas y el último cargue bueno tenía {previas}. "
                                      "No se cargó para no perder información (¿sincronización incompleta?).", st.st_mtime)
                return False
            self._cargar(fuente, ruta, huella, st.st_mtime, inicio, tablas, extra, total)
            e["visto"], e["error"] = firma, None
            log.info("%s cargado: %s filas en %.1fs", fuente, total, (dt.datetime.now() - inicio).total_seconds())
            return True
        finally:
            try:
                os.remove(copia)
            except OSError:
                pass

    def _ultimo_ok(self, fuente):
        r = db.consultar("SELECT TOP 1 sha256, filas FROM cesar.cargue WHERE fuente = ? AND estado = 'ok' ORDER BY id DESC", fuente)
        return r[0] if r else None

    def _cerrar_error(self, fuente, ruta, huella, mtime, filas):
        """Si el último registro es un error (ej. el archivo desapareció un rato mientras OneDrive reorganizaba
        carpetas) y el archivo volvió igual, se deja constancia de que la fuente quedó bien otra vez."""
        r = db.consultar("SELECT TOP 1 estado FROM cesar.cargue WHERE fuente = ? ORDER BY id DESC", fuente)
        if r and r[0]["estado"] == "error":
            ahora_ = ahora()
            db.ejecutar("""INSERT INTO cesar.cargue (fuente, archivo, sha256, modificado, inicio, fin, filas, estado, mensaje)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'ok', N'Archivo encontrado de nuevo, sin cambios')""",
                        fuente, str(ruta), huella, dt.datetime.fromtimestamp(mtime).replace(microsecond=0), ahora_, ahora_, filas)

    def _cargar(self, fuente, ruta, huella, mtime, inicio, tablas, extra, total):
        with db.transaccion() as cur:
            cur.execute("""INSERT INTO cesar.cargue (fuente, archivo, sha256, modificado, inicio, fin, filas, estado)
                           OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, 'ok')""",
                        fuente, str(ruta), huella, dt.datetime.fromtimestamp(mtime).replace(microsecond=0),
                        inicio.replace(microsecond=0), ahora(), total)
            id_cargue = cur.fetchone()[0]
            for tabla, (columnas, filas) in tablas.items():
                db.reemplazar_tabla(cur, tabla, ["id_cargue"] + columnas, [(id_cargue,) + tuple(f) for f in filas])
            if fuente == "fila_moldes" and extra.get("matriceros"):
                _upsert_parametro(cur, "moldes_matriceros_excel", str(extra["matriceros"]),
                                  "Matriceros según la hoja Cola de Fila de moldes.xlsx (se actualiza solo)")
            if fuente == "x5":
                hoy = dt.date.today()
                cur.execute("DELETE FROM cesar.x5_inventario_diario WHERE fecha = ?", hoy)
                for _, pieza, mat, cal in tablas["cesar.x5_inventario"][1]:
                    cur.execute("INSERT INTO cesar.x5_inventario_diario (fecha, pieza, matriceria, calidad, actualizado) "
                                "VALUES (?, ?, ?, ?, ?)", hoy, pieza, mat, cal, ahora())

    def _registrar_error(self, fuente, ruta, huella, mensaje, mtime=None):
        e = self.estado[fuente]
        if e["error"] == mensaje:
            return
        e["error"] = mensaje
        log.warning("%s: %s", fuente, mensaje)
        try:
            db.ejecutar("""INSERT INTO cesar.cargue (fuente, archivo, sha256, modificado, inicio, fin, estado, mensaje)
                           VALUES (?, ?, ?, ?, ?, ?, 'error', ?)""",
                        fuente, str(ruta) if ruta else None, huella,
                        dt.datetime.fromtimestamp(mtime).replace(microsecond=0) if mtime else None, ahora(), ahora(), mensaje)
        except Exception:
            log.exception("No se pudo registrar el error de %s", fuente)

    def iniciar(self, intervalo):
        def ciclo():
            while True:
                self.revisar()
                time.sleep(intervalo)
        threading.Thread(target=ciclo, name="ingesta", daemon=True).start()


def _upsert_parametro(cur, clave, valor, descripcion):
    cur.execute("UPDATE cesar.parametro SET valor = ? WHERE clave = ?", valor, clave)
    if cur.rowcount == 0:
        cur.execute("INSERT INTO cesar.parametro (clave, valor, descripcion) VALUES (?, ?, ?)", clave, valor, descripcion)


def estado_fuentes():
    filas = db.consultar("""
        SELECT c.fuente, c.estado, c.archivo, c.modificado, c.fin, c.filas, c.mensaje, ok.fin AS ultimo_ok,
               ok.modificado AS modificado_ok, ok.filas AS filas_ok
        FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY fuente ORDER BY id DESC) rn FROM cesar.cargue) c
        OUTER APPLY (SELECT TOP 1 fin, modificado, filas FROM cesar.cargue o
                     WHERE o.fuente = c.fuente AND o.estado = 'ok' ORDER BY o.id DESC) ok
        WHERE c.rn = 1""")
    salida = {}
    for r in filas:
        salida[r["fuente"]] = {
            "estado": r["estado"], "archivo": Path(r["archivo"]).name if r["archivo"] else None,
            "mensaje": r["mensaje"] if r["estado"] == "error" else None,
            "ultimo_ok": r["ultimo_ok"].isoformat() if r["ultimo_ok"] else None,
            "modificado": r["modificado_ok"].isoformat() if r["modificado_ok"] else None,
            "filas": r["filas_ok"],
        }
    return salida
