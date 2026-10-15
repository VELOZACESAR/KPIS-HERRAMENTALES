"""Arma el JSON que pinta el tablero y guarda la foto diaria de lo que los Excel no conservan."""
import datetime as dt
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import calculo_aceros, calculo_mantenimiento, calculo_moldes, db, reglas
from .ingesta import estado_fuentes

log = logging.getLogger("tablero")

SERVICIOS_PENDIENTES = [
    {"id": "serigrafia", "nombre": "Serigrafía",
     "necesita": ["Solicitudes y entregas de pantallas con fecha", "Rechazos y bajas de pantallas con su causa"]},
]

SEGUNDOS_CACHE = 60
_cache = {"clave": None, "t": 0, "datos": None}
_lock = threading.Lock()


def _bloque(nombre, fn, errores):
    t = time.time()
    try:
        return fn()
    except Exception as e:
        log.exception("Falla calculando %s", nombre)
        errores.append(f"{nombre}: {e}")
        return None
    finally:
        log.debug("%s en %.2fs", nombre, time.time() - t)


def construir(hoy=None):
    hoy = hoy or dt.date.today()
    R = reglas.cargar()
    errores = []
    datos = {
        "generado": dt.datetime.now().isoformat(timespec="seconds"), "hoy": hoy.isoformat(),
        "orden_materiales": R.orden_materiales, "colores_materiales": R.colores_materiales,
        "festivos": sorted(f.isoformat() for f in R.festivos), "pendientes": SERVICIOS_PENDIENTES,
        "parametros": {"meta_dias_fila": R.num("meta_dias_fila", 2)},
    }
    # Cada bloque es independiente y casi todo el tiempo es espera de red a Azure SQL: van en paralelo.
    bloques = {
        "aceros": ("Aceros (consolidado)", lambda: calculo_aceros.calcular(hoy, R)),
        "historial": ("Historial de aceros", historial),
        "cortes": ("Control de pedidos", lambda: calculo_aceros.enviados_a_cortar(hoy)),
        "x5": ("Inventario X5", calculo_aceros.inventario_x5),
        "moldes": ("Fabricación de moldes", lambda: calculo_moldes.calcular(hoy, R)),
        "historial_moldes": ("Historial de moldes", lambda: historial(["moldes_cola_dias", "moldes_pendientes"])),
        "mantenimiento": ("Mantenimiento de moldes", lambda: calculo_mantenimiento.calcular(hoy, R)),
        "fuentes": ("Estado de fuentes", estado_fuentes),
        "manuales": ("Valores manuales", manuales),
    }
    with ThreadPoolExecutor(max_workers=len(bloques)) as ex:
        futuros = {k: ex.submit(_bloque, nombre, fn, errores) for k, (nombre, fn) in bloques.items()}
        resultado = {k: f.result() for k, f in futuros.items()}
    if resultado["aceros"]:
        resultado["aceros"]["historial"] = resultado["historial"] or {}
    if resultado["moldes"]:
        resultado["moldes"]["historial"] = resultado["historial_moldes"] or {}
    for k in ("aceros", "cortes", "x5", "moldes", "mantenimiento"):
        datos[k] = resultado[k]
    datos["fuentes"] = resultado["fuentes"] or {}
    datos["manuales"] = resultado["manuales"] or {}
    datos["errores"] = errores
    return datos


def obtener(version, forzar=False):
    """Cachea el cálculo: se rehace si cambió algún Excel, si cambió un valor manual o cada minuto
    (mantenimiento se lee en vivo de la app)."""
    clave = (version, dt.date.today())
    with _lock:
        if not forzar and _cache["datos"] and _cache["clave"] == clave and time.time() - _cache["t"] < SEGUNDOS_CACHE:
            return _cache["datos"]
    datos = construir()
    with _lock:
        _cache.update(clave=clave, t=time.time(), datos=datos)
    return datos


def invalidar():
    with _lock:
        _cache["t"] = 0


def historial(indicadores=("retenidas", "fila", "dias_fila"), dias=120):
    filas = db.consultar(f"""SELECT fecha, indicador, valor FROM cesar.foto_diaria
                             WHERE fecha >= ? AND indicador IN ({', '.join('?' * len(indicadores))})""",
                         dt.date.today() - dt.timedelta(days=dias), *indicadores)
    salida = {}
    for r in filas:
        salida.setdefault(r["fecha"].isoformat(), {})[r["indicador"]] = r["valor"]
    return salida


def manuales():
    return {r["clave"]: {"v": r["valor"], "t": r["actualizado"].isoformat(timespec="seconds"), "u": r["usuario"]}
            for r in db.consultar("SELECT clave, valor, actualizado, usuario FROM cesar.valor_manual")}


def guardar_manual(clave, valor, usuario, ip):
    with db.transaccion() as cur:
        cur.execute("SELECT valor FROM cesar.valor_manual WITH (UPDLOCK, HOLDLOCK) WHERE clave = ?", clave)
        fila = cur.fetchone()
        antes = fila[0] if fila else None
        if fila and antes == valor:
            return False
        ahora = db.ahora()
        if valor is None:
            cur.execute("DELETE FROM cesar.valor_manual WHERE clave = ?", clave)
        elif fila:
            cur.execute("UPDATE cesar.valor_manual SET valor = ?, actualizado = ?, usuario = ? WHERE clave = ?",
                        valor, ahora, usuario, clave)
        else:
            cur.execute("INSERT INTO cesar.valor_manual (clave, valor, actualizado, usuario) VALUES (?, ?, ?, ?)",
                        clave, valor, ahora, usuario)
        cur.execute("INSERT INTO cesar.valor_manual_hist (clave, valor_antes, valor, actualizado, usuario, ip) "
                    "VALUES (?, ?, ?, ?, ?, ?)", clave, antes, valor, ahora, usuario, ip)
    invalidar()
    return True


def guardar_foto(hoy=None):
    """Foto del día de los indicadores sin historia propia. Se puede llamar seguido: la última del día manda."""
    hoy = hoy or dt.date.today()
    R = reglas.cargar()
    valores = {}
    try:
        k = calculo_aceros.calcular(hoy, R)["kpis"]
        valores.update(retenidas=k["retenidas"], fila=k["fila"], dias_fila=k["dias_fila"])
    except Exception:
        log.exception("Foto de aceros")
    try:
        m = calculo_moldes.calcular(hoy, R)
        if m:
            valores.update(moldes_cola_dias=m["kpis"]["cola_dias"], moldes_pendientes=m["kpis"]["pendientes"])
    except Exception:
        log.exception("Foto de moldes")
    if not valores:
        return
    ahora = db.ahora()
    with db.transaccion() as cur:
        for indicador, valor in valores.items():
            cur.execute("UPDATE cesar.foto_diaria SET valor = ?, actualizado = ? WHERE fecha = ? AND indicador = ?",
                        valor, ahora, hoy, indicador)
            if cur.rowcount == 0:
                cur.execute("INSERT INTO cesar.foto_diaria (fecha, indicador, valor, actualizado) VALUES (?, ?, ?, ?)",
                            hoy, indicador, valor, ahora)
        cur.execute("""INSERT INTO cesar.x5_inventario_diario (fecha, pieza, matriceria, calidad, actualizado)
                       SELECT ?, pieza, matriceria, calidad, ? FROM cesar.x5_inventario x
                       WHERE NOT EXISTS (SELECT 1 FROM cesar.x5_inventario_diario d WHERE d.fecha = ? AND d.pieza = x.pieza)""",
                    hoy, ahora, hoy)
    log.info("Foto diaria %s: %s", hoy, valores)
