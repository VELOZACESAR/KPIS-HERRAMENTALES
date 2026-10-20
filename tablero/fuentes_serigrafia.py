"""Lectores de los Excel de Serigrafía. Mismo contrato que fuentes.py: {tabla: (columnas, filas)}, extra."""
from pathlib import Path

import openpyxl

from .excel import buscar_encabezado, fecha, norm, numero, texto, ubicar_columnas
from .fuentes import _celda, _filas, _hoja


def _leer(ruta, *hojas):
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        return [_filas(_hoja(wb, *h)) if isinstance(h, tuple) else _filas(_hoja(wb, h)) for h in hojas]
    finally:
        wb.close()


def _tabla(filas, requeridos, mapa, obligatorias):
    h, enc = buscar_encabezado(filas, requeridos)
    return h, ubicar_columnas(enc, mapa, obligatorias=obligatorias)


COLUMNAS_LOGOS = ["fila", "pedido_genesis", "orden", "trazabilidad", "logo", "tipo_logo", "inv_status", "zfer", "vehiculo",
                  "cliente", "puesto_trabajo", "fecha_lib_toc", "nombre_archivo", "prioridad", "estado", "responsable",
                  "plan_corte", "fullkit"]


def leer_logos(ruta: Path):
    (filas,) = _leer(ruta, "HERRAMIENTA_LOGOS")
    h, c = _tabla(filas, ["INV_LOGO.STATUS", "NOMBRE_ARCHIVO"], {
        "pedido_genesis": ["PedidoGenesis"], "orden": ["Orden"], "trazabilidad": ["TRAZABILIDAD"], "logo": ["Logo"],
        "tipo_logo": ["TIPO_DE_LOGO"], "inv_status": ["INV_LOGO.STATUS"], "zfer": ["ZFER"], "vehiculo": ["Vehiculo"],
        "cliente": ["Cliente"], "puesto_trabajo": ["Puestodetrabajo"], "fecha_lib_toc": ["FechaLiberacionTOC"],
        "nombre_archivo": ["NOMBRE_ARCHIVO"], "prioridad": ["PRIORIDAD"], "estado": ["ESTADO"], "responsable": ["RESPONSABLE"],
        "plan_corte": ["Plan de corte.Dia turno", "Plan de corte"], "fullkit": ["FullKit Interna"],
    }, obligatorias=["inv_status", "nombre_archivo", "responsable", "plan_corte"])
    salida = []
    for i, r in enumerate(filas[h + 1:], start=h + 2):
        g = lambda campo, largo=None: texto(_celda(r, c.get(campo)), largo)
        if g("orden") is None and g("logo") is None:
            continue
        salida.append((i, g("pedido_genesis", 40), g("orden", 40), g("trazabilidad", 80), g("logo", 60), g("tipo_logo", 60),
                       g("inv_status", 40), g("zfer", 40), g("vehiculo", 200), g("cliente", 200), g("puesto_trabajo", 40),
                       fecha(_celda(r, c.get("fecha_lib_toc"))), g("nombre_archivo", 400), g("prioridad", 40), g("estado", 40),
                       g("responsable", 80), g("plan_corte", 80), g("fullkit", 60)))
    return {"cesar.seri_logos": (COLUMNAS_LOGOS, salida)}, {}


COLUMNAS_VITRO_CAL = ["fila", "pedido_genesis", "orden", "zfer", "puesto_trabajo", "fecha_lib_toc", "vehiculo", "descripcion",
                      "componente", "denominacion", "codigo_vitro", "status_vitrojet"]
COLUMNAS_VITRO_HECHOS = ["fila", "fecha", "vitro", "vehiculo", "codigo", "tipo", "estatus", "responsable"]


def leer_vitrojet(ruta: Path):
    cal, carga = _leer(ruta, "CAL. VITROJET", "CARGA VITROS")
    h, c = _tabla(cal, ["Puestodetrabajo", "STATUS VITROJET"], {
        "pedido_genesis": ["PedidoGenesis"], "orden": ["Orden"], "zfer": ["ZFER"], "puesto_trabajo": ["Puestodetrabajo"],
        "fecha_lib_toc": ["FechaLiberacionTOC"], "vehiculo": ["Vehiculo"], "descripcion": ["DESCRIPCION"],
        "componente": ["COMPONENTE"], "denominacion": ["DENOMINACION_COMPONENTE"], "codigo_vitro": ["CODIGO_MALLAyVITRO"],
        "status_vitrojet": ["STATUS VITROJET"],
    }, obligatorias=["puesto_trabajo", "status_vitrojet"])
    salida_cal = []
    for i, r in enumerate(cal[h + 1:], start=h + 2):
        g = lambda campo, largo=None: texto(_celda(r, c.get(campo)), largo)
        estado = g("status_vitrojet", 40)
        # "NO CREADA" son componentes que no llevan vitro (aceros, moldes...): no son carga ni inventario de vitros.
        if estado is None or norm(estado) == "NO CREADA":
            continue
        salida_cal.append((i, g("pedido_genesis", 40), g("orden", 40), g("zfer", 40), g("puesto_trabajo", 40),
                           fecha(_celda(r, c.get("fecha_lib_toc"))), g("vehiculo", 200), g("descripcion", 60),
                           g("componente", 40), g("denominacion", 120), g("codigo_vitro", 60), estado))

    h, c = _tabla(carga, ["FECHA", "RESPONSABLE"], {
        "fecha": ["FECHA"], "vitro": ["VITRO"], "vehiculo": ["VEHICULO"], "codigo": ["CODIGO"], "tipo": ["TIPO"],
        "estatus": ["ESTATUS"], "responsable": ["RESPONSABLE"],
    }, obligatorias=["fecha", "responsable"])
    salida_hechos = []
    for i, r in enumerate(carga[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        g = lambda campo, largo=None: texto(_celda(r, c.get(campo)), largo)
        salida_hechos.append((i, f, g("vitro", 60), g("vehiculo", 200), g("codigo", 60), g("tipo", 30), g("estatus", 30),
                              g("responsable", 60)))
    return {"cesar.seri_vitro_cal": (COLUMNAS_VITRO_CAL, salida_cal),
            "cesar.seri_vitro_hechos": (COLUMNAS_VITRO_HECHOS, salida_hechos)}, {}


COLUMNAS_PP_CONSULTA = ["fila", "pedido_genesis", "orden", "zfer", "vehiculo", "cliente", "puesto_trabajo", "componente",
                        "descripcion", "denominacion", "inventario_1", "inventario_2", "inventario_3"]
COLUMNAS_PP_ARCHIVOS = ["fila", "fecha", "zfer", "vehiculo", "herramental", "estatus_vitro", "responsable", "archivo_s", "caso"]


def leer_pasta_plata(ruta: Path):
    consulta, archivos = _leer(ruta, "CONSULTA_MALLAS", "ARCHIVOS PP")
    h, c = _tabla(consulta, ["Puestodetrabajo", "INVENTARIO_3"], {
        "pedido_genesis": ["PedidoGenesis"], "orden": ["Orden"], "zfer": ["ZFER"], "vehiculo": ["Vehiculo"],
        "cliente": ["Cliente"], "puesto_trabajo": ["Puestodetrabajo"], "componente": ["COMPONENTE"],
        "descripcion": ["DESCRIPCION"], "denominacion": ["DENOMINACION_COMPONENTE"], "inventario_1": ["INVENTARIO_1"],
        "inventario_2": ["INVENTARIO_2"], "inventario_3": ["INVENTARIO_3"],
    }, obligatorias=["puesto_trabajo", "inventario_3"])
    salida_c = []
    for i, r in enumerate(consulta[h + 1:], start=h + 2):
        g = lambda campo, largo=None: texto(_celda(r, c.get(campo)), largo)
        if g("orden") is None and g("componente") is None:
            continue
        salida_c.append((i, g("pedido_genesis", 40), g("orden", 40), g("zfer", 40), g("vehiculo", 200), g("cliente", 200),
                         g("puesto_trabajo", 40), g("componente", 40), g("descripcion", 60), g("denominacion", 120),
                         g("inventario_1", 40), g("inventario_2", 40), g("inventario_3", 40)))

    h, c = _tabla(archivos, ["Fecha", "Responsable"], {
        "fecha": ["Fecha"], "zfer": ["Zfer"], "vehiculo": ["Vehiculo"], "herramental": ["Herramental"],
        "estatus_vitro": ["Estatus Vitro"], "responsable": ["Responsable"], "archivo_s": ["Archivo S"], "caso": ["Caso"],
    }, obligatorias=["fecha", "responsable", "estatus_vitro"])
    salida_a = []
    for i, r in enumerate(archivos[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        g = lambda campo, largo=None: texto(_celda(r, c.get(campo)), largo)
        salida_a.append((i, f, g("zfer", 40), g("vehiculo", 200), g("herramental", 120), g("estatus_vitro", 40),
                         g("responsable", 60), g("archivo_s", 60), g("caso", 40)))
    return {"cesar.seri_pp_consulta": (COLUMNAS_PP_CONSULTA, salida_c),
            "cesar.seri_pp_archivos": (COLUMNAS_PP_ARCHIVOS, salida_a)}, {}


# Carga del día de pasta de plata, escrita por el equipo en Indicadores diarios (columna opcional, en VITROJET o MALLAS)
VITROS_PP = ["Vitros PP", "Vitro PP", "Carga vitros PP", "Vitros pasta de plata"]


def leer_indicadores_diarios(ruta: Path):
    vitro, mallas = _leer(ruta, "VITROJET", "MALLAS")
    # En oct-2026 "Vitros nuevos" se partió en Vitros Estandar / Vitros Logo / Vitros PP: los normales son los estándar.
    h, c = _tabla(vitro, ["Fecha", "Piezas quietas"], {
        "fecha": ["Fecha"], "vitros_nuevos": ["Vitros nuevos", "Vitros Estandar", "Vitros estándar"], "piezas_quietas": ["Piezas quietas"], "capacidad": ["Capacidad"],
        "vitros_pp": VITROS_PP,
    }, obligatorias=["fecha", "vitros_nuevos", "piezas_quietas"])
    salida_v = []
    for i, r in enumerate(vitro[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        salida_v.append((i, f, numero(_celda(r, c["vitros_nuevos"])), numero(_celda(r, c["piezas_quietas"])),
                         numero(_celda(r, c.get("capacidad"))), numero(_celda(r, c.get("vitros_pp")))))
    h, c = _tabla(mallas, ["Fecha", "Piezas quietas"], {
        "fecha": ["Fecha"], "mallas": ["Mallas en fabricacion"], "logos": ["Logos en fabricacion"],
        "trazabilidades": ["Trazabilidades en fabricacion"], "piezas_quietas": ["Piezas quietas"],
        "vitros_pp": VITROS_PP,
    }, obligatorias=["fecha", "mallas", "logos", "trazabilidades", "piezas_quietas"])
    salida_m = []
    for i, r in enumerate(mallas[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        salida_m.append((i, f, numero(_celda(r, c["mallas"])), numero(_celda(r, c["logos"])),
                         numero(_celda(r, c["trazabilidades"])), numero(_celda(r, c["piezas_quietas"])),
                         numero(_celda(r, c.get("vitros_pp")))))
    return {"cesar.seri_ind_vitrojet": (["fila", "fecha", "vitros_nuevos", "piezas_quietas", "capacidad", "vitros_pp"], salida_v),
            "cesar.seri_ind_mallas": (["fila", "fecha", "mallas", "logos", "trazabilidades", "piezas_quietas", "vitros_pp"],
                                      salida_m)}, {}


LECTORES_SERIGRAFIA = {
    "logos": leer_logos,
    "vitrojet": leer_vitrojet,
    "pasta_plata": leer_pasta_plata,
    "indicadores_diarios": leer_indicadores_diarios,
}
