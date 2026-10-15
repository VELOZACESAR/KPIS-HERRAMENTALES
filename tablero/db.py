import datetime as dt
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


def ahora():
    """Hora local del PC servidor (Colombia). Azure SQL corre en UTC, por eso no se usa SYSDATETIME()."""
    return dt.datetime.now().replace(microsecond=0)


def conectar(intentos=3):
    for n in range(intentos):
        try:
            return pyodbc.connect(_CADENA, autocommit=False)
        except pyodbc.Error as e:
            if n == intentos - 1 or not any(c in str(e) for c in _TRANSITORIOS):
                raise
            time.sleep(2 * (n + 1))


@contextmanager
def transaccion():
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


def consultar(sql, *params):
    cn = conectar()
    try:
        cur = cn.cursor()
        cur.execute(sql, *params)
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
    finally:
        cn.close()


def ejecutar(sql, *params):
    with transaccion() as cur:
        cur.execute(sql, *params)
        return cur.rowcount


def reemplazar_tabla(cur, tabla, columnas, filas):
    cur.execute(f"DELETE FROM {tabla}")
    if not filas:
        return
    marcas = ", ".join("?" for _ in columnas)
    cur.fast_executemany = True
    cur.executemany(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcas})", filas)
    cur.fast_executemany = False
