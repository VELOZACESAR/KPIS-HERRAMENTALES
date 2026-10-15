import ctypes
import datetime as dt
import hashlib
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

ERRORES_EXCEL = {"#N/A", "#N/D", "#REF!", "#¡REF!", "#VALUE!", "#¡VALOR!", "#DIV/0!", "#¡DIV/0!", "#NAME?", "#NUM!"}


def copia_temporal(ruta: Path) -> Path:
    """Copia el Excel aparte para poder leerlo aunque alguien lo tenga abierto."""
    destino = Path(tempfile.gettempdir()) / f"tablero_{os.getpid()}_{ruta.name}"
    if os.name == "nt":
        if not ctypes.windll.kernel32.CopyFileW(str(ruta), str(destino), False):
            raise OSError(f"No se pudo copiar {ruta.name} (código {ctypes.GetLastError()})")
    else:
        shutil.copyfile(ruta, destino)
    return destino


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def norm(v):
    s = unicodedata.normalize("NFD", str(v if v is not None else ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def limpio(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return None if not v or v.upper() in ERRORES_EXCEL else v
    return v


def texto(v, largo=None):
    v = limpio(v)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        v = v.isoformat()
    s = str(v)
    return s[:largo] if largo else s


def numero(v):
    v = limpio(v)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d,.\-]", "", v)
        if s.count(",") == 1 and s.count(".") >= 1:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(",") == 1:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def fecha(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,})", v)
        if m:
            d, mes, a = int(m[1]), int(m[2]), m[3]
            a = int(a[-4:]) if len(a) >= 4 else 2000 + int(a[-2:])
            try:
                return dt.date(a, mes, d)
            except ValueError:
                return None
        m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            try:
                return dt.date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                return None
    return None


def fecha_hora(v):
    if isinstance(v, dt.datetime):
        return v.replace(microsecond=0)
    f = fecha(v)
    return dt.datetime.combine(f, dt.time()) if f else None


def ubicar_columnas(encabezado, mapa, obligatorias=()):
    """mapa: {campo: [nombres posibles]} -> {campo: índice}. Falla si falta una obligatoria."""
    nombres = [norm(x) for x in encabezado]
    salida = {}
    for campo, opciones in mapa.items():
        for op in opciones:
            op = norm(op)
            if op in nombres:
                salida[campo] = nombres.index(op)
                break
    faltan = [c for c in obligatorias if c not in salida]
    if faltan:
        raise ValueError(f"No encontré las columnas {', '.join(faltan)} en el encabezado")
    return salida


def buscar_encabezado(filas, requeridos, max_filas=15):
    """Devuelve (índice de la fila de encabezado, la fila) buscando los textos requeridos."""
    req = [norm(r) for r in requeridos]
    for i, fila in enumerate(filas[:max_filas]):
        nombres = {norm(x) for x in fila}
        if all(r in nombres for r in req):
            return i, fila
    raise ValueError(f"No encontré un encabezado con {', '.join(requeridos)}")
