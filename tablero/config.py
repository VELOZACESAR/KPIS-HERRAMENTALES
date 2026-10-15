import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _env(nombre, defecto=None, obligatorio=False):
    valor = os.environ.get(nombre, defecto)
    if obligatorio and not valor:
        raise RuntimeError(f"Falta la variable {nombre} en el archivo .env")
    return valor


DB_SERVER = _env("DB_SERVER", "agpcolombia.database.windows.net")
DB_NAME = _env("DB_NAME", "AGP_Ingenieria")
DB_USER = _env("DB_USER", obligatorio=True)
DB_PASSWORD = _env("DB_PASSWORD", obligatorio=True)
DB_DRIVER = _env("DB_DRIVER", "ODBC Driver 18 for SQL Server")

HOST = _env("HOST", "0.0.0.0")
PUERTO = int(_env("PUERTO", "8050"))
CLAVE_EDICION = _env("CLAVE_EDICION", "")
SEGUNDOS_REVISION = int(_env("SEGUNDOS_REVISION", "60"))

CARPETA_LOGS = RAIZ / "logs"
CARPETA_WEB = RAIZ / "web"


def raices_onedrive():
    vistas, salida = set(), []
    for c in (os.environ.get("OneDriveCommercial"), os.environ.get("OneDrive"),
              Path.home() / "OneDrive - AGP GROUP"):
        if c and Path(c).is_dir() and str(Path(c).resolve()).lower() not in vistas:
            vistas.add(str(Path(c).resolve()).lower())
            salida.append(Path(c))
    return salida


# Cada fuente se busca primero en la ruta del .env; si no está, por nombre dentro de OneDrive,
# prefiriendo las carpetas que suenan a la biblioteca de SharePoint donde vive el original.
FUENTES = {
    "consolidado": {
        "variable": "RUTA_CONSOLIDADO",
        "archivo": "Consolidado inventario de aceros.xlsx",
        "pistas": ["Fulll kit de aceros", "Full kit de aceros", "Aceros"],
    },
    "pedidos": {
        "variable": "RUTA_PEDIDOS",
        "archivo": "Control de pedidos.xlsx",
        "pistas": ["Fulll kit de aceros", "Full kit de aceros", "Aceros"],
    },
    "x5": {
        "variable": "RUTA_X5",
        "archivo": "Inventario Aceros X5.xlsx",
        "pistas": ["Tecnico de Herramentales", "Fulll kit de aceros", "Aceros"],
    },
    "fila_moldes": {
        "variable": "RUTA_FILA_MOLDES",
        "archivo": "Fila de moldes.xlsx",
        "pistas": ["Full kit", "Herramentales"],
    },
}

CARPETAS_IGNORADAS = {"archivos de chat de microsoft teams", "papelera", "$recycle.bin"}


def ruta_fuente(clave):
    f = FUENTES[clave]
    explicita = os.environ.get(f["variable"])
    if explicita:
        return Path(explicita)
    candidatos = []
    for raiz in raices_onedrive():
        for ruta in _buscar(raiz, f["archivo"], profundidad=5):
            texto = str(ruta).lower()
            puntaje = sum(1 for p in f["pistas"] if p.lower() in texto)
            candidatos.append((puntaje, ruta.stat().st_mtime, ruta))
    if not candidatos:
        return None
    candidatos.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return candidatos[0][2]


def _buscar(raiz, nombre, profundidad):
    try:
        for hijo in raiz.iterdir():
            if hijo.name.lower() in CARPETAS_IGNORADAS:
                continue
            if hijo.is_file() and hijo.name.lower() == nombre.lower():
                yield hijo
            elif hijo.is_dir() and profundidad > 0 and not hijo.name.startswith("."):
                yield from _buscar(hijo, nombre, profundidad - 1)
    except (PermissionError, OSError):
        return
