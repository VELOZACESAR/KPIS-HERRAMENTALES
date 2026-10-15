"""Reglas de negocio que viven en tablas (cesar.*) para poder ajustarlas sin tocar código."""
import threading
import time
from dataclasses import dataclass, field

from . import db
from .excel import norm


@dataclass
class Reglas:
    parametros: dict
    materiales: dict
    orden_materiales: list
    colores_materiales: dict
    equivalencias: dict
    excluidos: set
    vacios: set
    alias: dict
    festivos: dict
    dias_laborales: set = field(default_factory=set)

    def num(self, clave, defecto=0.0):
        try:
            return float(self.parametros.get(clave, defecto))
        except (TypeError, ValueError):
            return defecto

    def entero(self, clave, defecto=0):
        return int(self.num(clave, defecto))

    def material(self, v):
        return self.materiales.get(str(v or "").strip().upper(), "Otro")

    def factor(self, material, pieza):
        try:
            return self.equivalencias.get(material, {}).get(int(float(pieza)), 1)
        except (TypeError, ValueError):
            return 1

    def operario(self, v):
        """('vacio'|'excluido'|'ok', nombre en formato Título)."""
        clave = norm(v)
        if not clave or clave in self.vacios:
            return "vacio", None
        clave = self.alias.get(clave, clave)
        if clave in self.excluidos:
            return "excluido", None
        return "ok", clave.title()

    def es_laboral(self, d):
        return d.weekday() in self.dias_laborales and d not in self.festivos


_cache = {"t": 0, "reglas": None}
_lock = threading.Lock()


def cargar(segundos=300):
    with _lock:
        if _cache["reglas"] and time.time() - _cache["t"] < segundos:
            return _cache["reglas"]
        parametros = {r["clave"]: r["valor"] for r in db.consultar("SELECT clave, valor FROM cesar.parametro")}
        orden = db.consultar("SELECT material, color FROM cesar.material_orden ORDER BY orden")
        equivalencias = {}
        for r in db.consultar("SELECT material, pieza, factor FROM cesar.equivalencia"):
            equivalencias.setdefault(r["material"], {})[r["pieza"]] = r["factor"]
        ops = db.consultar("SELECT nombre, accion, alias FROM cesar.operario_regla")
        reglas = Reglas(
            parametros=parametros,
            materiales={r["texto"].strip().upper(): r["material"] for r in db.consultar("SELECT texto, material FROM cesar.material")},
            orden_materiales=[r["material"] for r in orden],
            colores_materiales={r["material"]: r["color"] for r in orden},
            equivalencias=equivalencias,
            excluidos={norm(r["nombre"]) for r in ops if r["accion"] == "excluir"},
            vacios={norm(r["nombre"]) for r in ops if r["accion"] == "vacio"},
            alias={norm(r["nombre"]): norm(r["alias"]) for r in ops if r["accion"] == "alias" and r["alias"]},
            festivos={r["fecha"]: r["nombre"] for r in db.consultar("SELECT fecha, nombre FROM cesar.festivo")},
        )
        reglas.dias_laborales = {int(x) for x in parametros.get("dias_laborales", "0,1,2,3,4,5").split(",") if x.strip()}
        _cache.update(t=time.time(), reglas=reglas)
        return reglas


def invalidar():
    with _lock:
        _cache["t"] = 0
