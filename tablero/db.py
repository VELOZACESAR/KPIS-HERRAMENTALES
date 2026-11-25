import datetime as dt
import threading
import time
from contextlib import contextmanager

import pyodbc

from . import config

pyodbc.pooling = True

_CADENA = (
    f"DRIVER={{{config.DB_DRIVER}}};SERVER={config.DB_SERVER};DATABASE={config.DB_NAME};"
    f"UID={config.DB_USER};PWD={config.DB_PASSWORD};Encrypt=yes;TrustServerCertificate=no;"
    "Connection Timeout=30"
)

# Errores de red/servidor de Azure SQL que se arreglan solos reintentando.
_TRANSITORIOS = ("08S01", "08001", "40613", "40197", "40501", "49918", "10053", "10054", "HYT00")
# La base deja 30 consultas simultáneas para TODAS las apps que la usan (Pedidos, Control Inventarios, Logos...):
# este servidor nunca abre más de MAX_SIMULTANEAS a la vez y, si igual se llena, espera y reintenta.
MAX_SIMULTANEAS = 8
_LIMITE = ("10928", "10936")
_cupo = threading.BoundedSemaphore(MAX_SIMULTANEAS)


def _es_limite(e):
    return any(c in str(e) for c in _LIMITE)


def ahora():
    """Hora local del PC servidor (Colombia). Azure SQL corre en UTC, por eso no se usa SYSDATETIME()."""
    return dt.datetime.now().replace(microsecond=0)


def conectar(intentos=5):
    for n in range(intentos):
        try:
            return pyodbc.connect(_CADENA, autocommit=False)
        except pyodbc.Error as e:
            if n == intentos - 1 or not (_es_limite(e) or any(c in str(e) for c in _TRANSITORIOS)):
                raise
            time.sleep(2 * (n + 1))


@contextmanager
def transaccion():
    with _cupo:
        cn = conectar()
        try:
            cur = cn.cursor()
            yield cur
            cn.commit()
        except Exception:
            cn.rollback()
            raise
        finally:
            cn.close()


def consultar(sql, *params, intentos=5):
    for n in range(intentos):
        try:
            with _cupo:
                cn = conectar()
                try:
                    cur = cn.cursor()
                    cur.execute(sql, *params)
                    columnas = [d[0] for d in cur.description]
                    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
                finally:
                    cn.close()
        except pyodbc.Error as e:
            if n == intentos - 1 or not _es_limite(e):
                raise
            time.sleep(2 * (n + 1))


def ejecutar(sql, *params):
    with transaccion() as cur:
        cur.execute(sql, *params)
        return cur.rowcount


def hay_smartfactory():
    return all((config.SMART_DB_SERVER, config.SMART_DB_NAME, config.SMART_DB_USER, config.SMART_DB_PASSWORD))


def consultar_smart(sql, *params):
    """SmartFactory es un SQL Server de la planta con certificado propio: se confía en él (solo lectura)."""
    cadena = (f"DRIVER={{{config.DB_DRIVER}}};SERVER={config.SMART_DB_SERVER};DATABASE={config.SMART_DB_NAME};"
              f"UID={config.SMART_DB_USER};PWD={config.SMART_DB_PASSWORD};Encrypt=yes;TrustServerCertificate=yes;"
              "Connection Timeout=15")
    cn = pyodbc.connect(cadena, autocommit=True)
    try:
        cn.timeout = 60
        cur = cn.cursor()
        cur.execute(sql, *params)
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
    finally:
        cn.close()


def reemplazar_tabla(cur, tabla, columnas, filas):
    cur.execute(f"DELETE FROM {tabla}")
    if not filas:
        return
    marcas = ", ".join("?" for _ in columnas)
    cur.fast_executemany = True
    cur.executemany(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcas})", filas)
    cur.fast_executemany = False
