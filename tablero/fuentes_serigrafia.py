"""Lectores de Serigrafía. Mismo contrato que fuentes.py: {tabla: (columnas, filas)}, extra.
Los logos ya no salen de un Excel: se leen de la app Herramienta Logos (vistas HRRM.VW_* de esta misma base)."""
import hashlib
from pathlib import Path

import openpyxl

from . import config, db
from .excel import buscar_encabezado, fecha, norm, numero, texto, ubicar_columnas
from .fuentes import _celda, _filas, _hoja


def _leer(ruta, *hojas):
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        return [_filas(_hoja(wb, *h)) if isinstance(h, tuple) else _filas(_hoja(wb, h)) for h in hojas]
    finally:
        wb.close()


def _tabla(filas, requeridos, mapa, obligatorias, contiene=None):
    """contiene: {campo: texto o función(encabezado normalizado) -> bool} para columnas cuyo nombre puede variar
    (ej. cualquier encabezado con "CAPACIDAD")."""
    h, enc = buscar_encabezado(filas, requeridos)
    c = ubicar_columnas(enc, mapa, obligatorias=obligatorias)
    for campo, texto_ in (contiene or {}).items():
        if campo not in c:
            for i, nombre in enumerate(enc):
                if (texto_(norm(nombre)) if callable(texto_) else texto_ in norm(nombre)) and i not in c.values():
                    c[campo] = i
                    break
    return h, c


COLUMNAS_LOGOS = ["fila", "pedido_genesis", "orden", "trazabilidad", "logo", "tipo_logo", "inv_status", "zfer", "vehiculo",
                  "cliente", "puesto_trabajo", "fecha_lib_toc", "nombre_archivo", "prioridad", "estado", "responsable",
                  "plan_corte", "situacion", "fullkit"]

# Los nombres de las vistas son los del Excel viejo (las publica herramienta_logos en app/sql/hrrm_esquema.sql),
# así el tablero no tiene que cambiar el resto del cálculo.
SQL_LOGOS = """
SELECT PedidoGenesis, Orden, TRAZABILIDAD, Logo, TIPO_DE_LOGO, STATUS_LOGO, ZFER, Vehiculo, Puestodetrabajo,
       FechaLiberacionTOC, NOMBRE_ARCHIVO, PRIORIDAD, ESTADO, RESPONSABLE, PLAN_DE_CORTE, Cliente, SITUACION
FROM HRRM.VW_HERRAMIENTA_LOGOS
ORDER BY Orden"""
SQL_LOGOS_GRAFICA = """
SELECT Fecha, CARGA, CAPACIDAD, [FALTANTES PCP] AS faltantes
FROM HRRM.VW_GRAFICA
WHERE Fecha IS NOT NULL
ORDER BY Fecha"""
SQL_LOGOS_HISTORICO = """
SELECT FechaGrafica, ORDEN, RESPONSABLE
FROM HRRM.VW_HISTORICO
WHERE ESTADO = 'CARGADO' AND FechaGrafica IS NOT NULL
ORDER BY FechaCreacion, ORDEN"""


_cache_logos = {"marca": None, "tablas": None, "extra": None}   # la app publica en bloque: se relee solo si cambió


def leer_logos(_ruta=None):
    """Tablero, gráfica e histórico de logos desde la app Herramienta Logos (vistas HRRM.VW_*).
    Devuelve las mismas tablas cesar.* que antes se armaban con el Excel; el resto del tablero no cambia.
    `_ruta` queda por compatibilidad con el contrato de los lectores de Excel: esta fuente no es un archivo.
    La app reescribe HRRM.TABLERO completa al publicar (y de ahí salen las tres vistas): si MAX(ACTUALIZADO) no
    cambió, se devuelve lo leído antes sin volver a bajar las 26 mil filas cada minuto."""
    publicado = db.consultar("SELECT MAX(ACTUALIZADO) AS ultimo FROM HRRM.VW_HERRAMIENTA_LOGOS")
    marca = publicado[0]["ultimo"] if publicado else None
    if _cache_logos["tablas"] is not None and _cache_logos["marca"] == marca:
        return _cache_logos["tablas"], _cache_logos["extra"]
    salida = []
    for i, r in enumerate(db.consultar(SQL_LOGOS), start=2):
        orden, logo = texto(r["Orden"], 40), texto(r["Logo"], 60)
        if orden is None and logo is None:
            continue
        salida.append((i, texto(r["PedidoGenesis"], 40), orden, texto(r["TRAZABILIDAD"], 80), logo,
                       texto(r["TIPO_DE_LOGO"], 60), texto(r["STATUS_LOGO"], 40), texto(r["ZFER"], 40),
                       texto(r["Vehiculo"], 200), texto(r["Cliente"], 200), texto(r["Puestodetrabajo"], 40),
                       fecha(r["FechaLiberacionTOC"]), texto(r["NOMBRE_ARCHIVO"], 400), texto(r["PRIORIDAD"], 40),
                       texto(r["ESTADO"], 40), texto(r["RESPONSABLE"], 80), texto(r["PLAN_DE_CORTE"], 80),
                       texto(r["SITUACION"], 40), None))
    grafica = [(i, fecha(r["Fecha"]), numero(r["CARGA"]), numero(r["CAPACIDAD"]), numero(r["faltantes"]))
               for i, r in enumerate(db.consultar(SQL_LOGOS_GRAFICA), start=2)]
    historico = []
    for i, r in enumerate(db.consultar(SQL_LOGOS_HISTORICO), start=2):
        f = fecha(r["FechaGrafica"])
        if f is not None:
            historico.append((i, f, texto(r["ORDEN"], 40), texto(r["RESPONSABLE"], 80)))
    extra = {
        # no hay archivo que hashear: la huella sale de los datos leídos (así no se recarga si nada cambió)
        "huella": hashlib.sha256(repr((salida, grafica, historico)).encode("utf-8")).hexdigest(),
        "origen": config.FUENTES_BD["logos"],
        "modificado": marca,
    }
    tablas = {
        "cesar.seri_logos": (COLUMNAS_LOGOS, salida),
        "cesar.seri_logos_grafica": (["fila", "fecha", "carga", "capacidad", "faltantes"], grafica),
        "cesar.seri_logos_historico": (["fila", "fecha", "orden", "responsable"], historico),
    }
    _cache_logos.update(marca=marca, tablas=tablas, extra=extra)
    return tablas, extra


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
# Capacidad diaria: "CAPACIDAD" = vitros estándar; con "PP" o "PLATA" en el nombre = vitros pasta de plata
_ES_PP = lambda n: "PP" in n.split() or "PLATA" in n
CAP_VITROS = lambda n: "CAPACIDAD" in n and not _ES_PP(n)
CAP_PP = lambda n: "CAPACIDAD" in n and _ES_PP(n)


def _leer_capacidades(ruta: Path):
    """Tabla diaria de capacidades y retenidas por tipo de vitro (Fecha | Capacidad Vitros Logo | Capacidad Vitros Estandar |
    Capacidad Vitros Pasta de Plata | Retenidas Vitros Logos | ...). Puede estar en cualquier hoja: se toma la primera que
    tenga "Fecha" y una columna de capacidad de pasta de plata."""
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            filas = _filas(ws)
            for h, enc in enumerate(filas[:15]):
                nombres = [norm(x) for x in enc]
                if "FECHA" not in nombres or not any(CAP_PP(n) for n in nombres):
                    continue
                col = lambda pred: next((i for i, n in enumerate(nombres) if pred(n)), None)
                c = {"fecha": nombres.index("FECHA"),
                     "cap_logos": col(lambda n: "CAPACIDAD" in n and "LOGO" in n),
                     "cap_estandar": col(lambda n: "CAPACIDAD" in n and "ESTANDAR" in n),
                     "cap_pp": col(CAP_PP),
                     "ret_logos": col(lambda n: "RETENIDA" in n and "LOGO" in n),
                     "ret_estandar": col(lambda n: "RETENIDA" in n and "ESTANDAR" in n),
                     "ret_pp": col(lambda n: "RETENIDA" in n and _ES_PP(n))}
                salida = []
                for i, r in enumerate(filas[h + 1:], start=h + 2):
                    f = fecha(_celda(r, c["fecha"]))
                    if f is not None:
                        salida.append((i, ws.title[:100], f, *(numero(_celda(r, c[k])) for k in
                                       ("cap_logos", "cap_estandar", "cap_pp", "ret_logos", "ret_estandar", "ret_pp"))))
                return salida
        return []
    finally:
        wb.close()


def leer_indicadores_diarios(ruta: Path):
    vitro, mallas = _leer(ruta, "VITROJET", "MALLAS")
    # Oct-2026: la hoja Vitrojet pasó a capacidad/retenidas por tipo (eso lo lee _leer_capacidades); "Vitros nuevos"
    # y "Piezas quietas" ya no siempre vienen, por eso son opcionales.
    h, c = _tabla(vitro, ["Fecha"], {
        "fecha": ["Fecha"], "vitros_nuevos": ["Vitros nuevos", "Vitros Estandar"], "piezas_quietas": ["Piezas quietas"],
        "capacidad": ["Capacidad Vitros Estandar", "Capacidad Vitros Estándar", "Capacidad"], "vitros_pp": VITROS_PP,
    }, obligatorias=["fecha"], contiene={"capacidad": CAP_VITROS, "capacidad_pp": CAP_PP})
    salida_v = []
    for i, r in enumerate(vitro[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        salida_v.append((i, f, numero(_celda(r, c.get("vitros_nuevos"))), numero(_celda(r, c.get("piezas_quietas"))),
                         numero(_celda(r, c.get("capacidad"))), numero(_celda(r, c.get("vitros_pp"))),
                         numero(_celda(r, c.get("capacidad_pp")))))
    h, c = _tabla(mallas, ["Fecha", "Piezas quietas"], {
        "fecha": ["Fecha"], "mallas": ["Mallas en fabricacion"], "logos": ["Logos en fabricacion"],
        "trazabilidades": ["Trazabilidades en fabricacion"], "piezas_quietas": ["Piezas quietas"],
        "vitros_pp": VITROS_PP,
    }, obligatorias=["fecha", "mallas", "logos", "trazabilidades", "piezas_quietas"], contiene={"capacidad_pp": CAP_PP})
    salida_m = []
    for i, r in enumerate(mallas[h + 1:], start=h + 2):
        f = fecha(_celda(r, c["fecha"]))
        if f is None:
            continue
        salida_m.append((i, f, numero(_celda(r, c["mallas"])), numero(_celda(r, c["logos"])),
                         numero(_celda(r, c["trazabilidades"])), numero(_celda(r, c["piezas_quietas"])),
                         numero(_celda(r, c.get("vitros_pp"))), numero(_celda(r, c.get("capacidad_pp")))))
    return {"cesar.seri_ind_vitrojet": (["fila", "fecha", "vitros_nuevos", "piezas_quietas", "capacidad", "vitros_pp", "capacidad_pp"], salida_v),
            "cesar.seri_ind_mallas": (["fila", "fecha", "mallas", "logos", "trazabilidades", "piezas_quietas", "vitros_pp", "capacidad_pp"],
                                      salida_m),
            "cesar.seri_ind_capacidad": (["fila", "hoja", "fecha", "cap_logos", "cap_estandar", "cap_pp", "ret_logos", "ret_estandar",
                                          "ret_pp"], _leer_capacidades(ruta))}, {}


LECTORES_SERIGRAFIA = {
    "logos": leer_logos,
    "vitrojet": leer_vitrojet,
    "pasta_plata": leer_pasta_plata,
    "indicadores_diarios": leer_indicadores_diarios,
}
