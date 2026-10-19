"""Serigrafía: carga y productividad de logos, vitros normales (Vitrojet) y pasta de plata,
más piezas retenidas y screens a pedir del Excel de indicadores diarios."""
import datetime as dt
from collections import Counter, defaultdict

from . import db
from .excel import norm

# En las columnas de responsable también se escriben estados; esos no son personas.
NO_PERSONAS = {"", "REALIZADO", "REALIZANDO", "POR HACER", "EN ESPERA", "PENDIENTE"}
PUESTOS_PASTA_PLATA = {"01CORTE", "02CNC", "03SERIG", "PLANEACION"}
DIAS_MATRIZ = 14


def _persona(v):
    n = norm(v)
    return None if n in NO_PERSONAS else n.title()


def _matriz(hechos, hoy):
    """hechos: [(fecha, persona)] -> filas persona x últimos 14 días."""
    dias = [hoy - dt.timedelta(days=k) for k in range(DIAS_MATRIZ - 1, -1, -1)]
    cuenta = defaultdict(Counter)
    for f, p in hechos:
        if p and dias[0] <= f <= hoy:
            cuenta[p][f] += 1
    personas = [{"nombre": p, "celdas": [c[d] for d in dias], "total": sum(c.values())} for p, c in cuenta.items()]
    personas.sort(key=lambda x: -x["total"])
    totales = Counter(f for f, p in hechos if p)
    return {"dias": [d.isoformat() for d in dias], "personas": personas,
            "diaria": [{"fecha": d.isoformat(), "total": totales[d]} for d in dias]}


def _ultimo(filas, hoy):
    previas = [r for r in filas if r["fecha"] and r["fecha"] <= hoy]
    return max(previas, key=lambda r: (r["fecha"], r["fila"])) if previas else None


def logos(hoy):
    filas = db.consultar("""SELECT orden, logo, tipo_logo, inv_status, vehiculo, cliente, puesto_trabajo, fecha_lib_toc,
                                   nombre_archivo, prioridad, estado, responsable, plan_corte FROM cesar.seri_logos""")
    if not filas:
        return None
    carga = [r for r in filas if norm(r["inv_status"]) == "DISPONIBLE" and not (r["nombre_archivo"] or "").strip()]
    prioritaria = [r for r in carga if (r["plan_corte"] or "").strip()]
    hechos = Counter(_persona(r["responsable"]) for r in filas if (r["nombre_archivo"] or "").strip())
    hechos.pop(None, None)
    fotos = db.consultar("SELECT fecha, indicador, valor FROM cesar.foto_diaria WHERE indicador LIKE 'logos_hechos:%' AND fecha >= ?",
                         hoy - dt.timedelta(days=DIAS_MATRIZ + 1))
    por_dia = defaultdict(dict)
    for f in fotos:
        por_dia[f["fecha"]][f["indicador"].split(":", 1)[1]] = f["valor"] or 0
    diarios = []
    fechas = sorted(por_dia)
    for antes, despues in zip(fechas, fechas[1:]):
        for p, n in por_dia[despues].items():
            delta = n - por_dia[antes].get(p, n)
            diarios.extend([(despues, p)] * int(max(0, delta)))
    return {
        "carga": len(carga), "prioridad": len(prioritaria), "sin_prioridad": len(carga) - len(prioritaria),
        "por_responsable": [{"nombre": n, "n": c} for n, c in hechos.most_common()],
        "por_cliente": [{"nombre": n, "n": c} for n, c in Counter((r["cliente"] or "Sin cliente") for r in carga).most_common(8)],
        "detalle": sorted(({"orden": r["orden"], "logo": r["logo"], "vehiculo": r["vehiculo"], "cliente": r["cliente"],
                            "puesto": r["puesto_trabajo"], "plan_corte": r["plan_corte"], "prioridad": bool((r["plan_corte"] or "").strip()),
                            "toc": r["fecha_lib_toc"].isoformat() if r["fecha_lib_toc"] else None} for r in carga),
                          key=lambda x: (not x["prioridad"], x["toc"] or "9")),
        "hechos_por_persona": dict(hechos),
        **_matriz(diarios, hoy),
    }


def vitros(hoy):
    cal = db.consultar("""SELECT orden, zfer, puesto_trabajo, fecha_lib_toc, vehiculo, descripcion, componente, denominacion,
                                 codigo_vitro, status_vitrojet FROM cesar.seri_vitro_cal""")
    hechos = db.consultar("SELECT fecha, vitro, vehiculo, tipo, estatus, responsable FROM cesar.seri_vitro_hechos")
    ind = db.consultar("SELECT fila, fecha, vitros_nuevos, piezas_quietas, capacidad FROM cesar.seri_ind_vitrojet")
    if not cal and not hechos:
        return None
    carga = [r for r in cal if norm(r["puesto_trabajo"]) != "INGENIERIA" and norm(r["status_vitrojet"]) == "NO EXISTE"]
    ok = [(r["fecha"], _persona(r["responsable"])) for r in hechos if norm(r["estatus"]) == "OK"]
    capacidad = {r["fecha"]: r["capacidad"] for r in ind if r["fecha"] and r["capacidad"] is not None}
    m = _matriz(ok, hoy)
    for d in m["diaria"]:
        d["capacidad"] = capacidad.get(dt.date.fromisoformat(d["fecha"]))
    return {
        "carga": len(carga), "carga_vitros": len({r["codigo_vitro"] for r in carga}),
        "en_curso": sum(1 for r in hechos if norm(r["estatus"]) == "REALIZADO"),
        "inventario_vitros": len({r["codigo_vitro"] for r in cal if norm(r["status_vitrojet"]) == "EXISTE"}),
        "detalle": sorted(({"orden": r["orden"], "vitro": r["codigo_vitro"], "componente": r["denominacion"],
                            "vehiculo": r["vehiculo"], "puesto": r["puesto_trabajo"],
                            "toc": r["fecha_lib_toc"].isoformat() if r["fecha_lib_toc"] else None} for r in carga),
                          key=lambda x: x["toc"] or "9"),
        "por_tipo": [{"nombre": n, "n": c} for n, c in Counter(norm(r["descripcion"]).capitalize() for r in carga).most_common()],
        **m,
    }


def pasta_plata(hoy):
    consulta = db.consultar("""SELECT orden, zfer, vehiculo, cliente, puesto_trabajo, componente, descripcion, denominacion,
                                      inventario_3 FROM cesar.seri_pp_consulta""")
    archivos = db.consultar("SELECT fecha, herramental, estatus_vitro, responsable FROM cesar.seri_pp_archivos")
    if not consulta and not archivos:
        return None
    carga = [r for r in consulta if norm(r["puesto_trabajo"]) in PUESTOS_PASTA_PLATA and norm(r["inventario_3"]) == "CREAR_VITRO"]
    por_vitro = defaultdict(list)
    for r in carga:
        por_vitro[r["denominacion"] or r["componente"]].append(r)
    ok = [(r["fecha"], _persona(r["responsable"])) for r in archivos if norm(r["estatus_vitro"]) == "OK"]
    return {
        "carga": len(carga), "carga_vitros": len(por_vitro),
        "en_curso": sum(1 for r in archivos if norm(r["estatus_vitro"]) == "REALIZANDO"),
        "por_puesto": [{"nombre": n, "n": c} for n, c in Counter(r["puesto_trabajo"] for r in carga).most_common()],
        "vitros": sorted(({"vitro": v, "tipo": rs[0]["descripcion"], "ordenes": len(rs),
                           "vehiculos": sorted({r["vehiculo"] or "—" for r in rs}),
                           "puestos": sorted({r["puesto_trabajo"] for r in rs})} for v, rs in por_vitro.items()),
                         key=lambda x: -x["ordenes"]),
        **_matriz(ok, hoy),
    }


def retenidas(hoy):
    vit = db.consultar("SELECT fila, fecha, vitros_nuevos, piezas_quietas, capacidad FROM cesar.seri_ind_vitrojet WHERE fecha IS NOT NULL")
    mal = db.consultar("SELECT fila, fecha, mallas, logos, trazabilidades, piezas_quietas FROM cesar.seri_ind_mallas WHERE fecha IS NOT NULL")
    if not vit and not mal:
        return None
    uv, um = _ultimo(vit, hoy), _ultimo(mal, hoy)
    desde = hoy - dt.timedelta(days=45)
    serie = defaultdict(dict)
    for r in vit:
        if desde <= r["fecha"] <= hoy:
            serie[r["fecha"]].update(vitro_quietas=r["piezas_quietas"] or 0, vitros_nuevos=r["vitros_nuevos"] or 0,
                                     capacidad=r["capacidad"])
    for r in mal:
        if desde <= r["fecha"] <= hoy:
            serie[r["fecha"]].update(malla_quietas=r["piezas_quietas"] or 0, mallas=r["mallas"] or 0, logos=r["logos"] or 0,
                                     trazabilidades=r["trazabilidades"] or 0)
    v = lambda fila, campo: (fila or {}).get(campo) or 0
    return {
        "fecha_vitrojet": uv["fecha"].isoformat() if uv else None, "fecha_mallas": um["fecha"].isoformat() if um else None,
        "falta_archivo": v(uv, "piezas_quietas"), "falta_malla": v(um, "piezas_quietas"),
        "total": v(uv, "piezas_quietas") + v(um, "piezas_quietas"),
        "screens": {"mallas": v(um, "mallas"), "logos": v(um, "logos"), "trazabilidades": v(um, "trazabilidades")},
        "screens_total": v(um, "mallas") + v(um, "logos") + v(um, "trazabilidades"),
        "vitros_nuevos": v(uv, "vitros_nuevos"), "capacidad_vitros": (uv or {}).get("capacidad"),
        "serie": [{"fecha": f.isoformat(), **d} for f, d in sorted(serie.items())],
    }


def calcular(hoy):
    salida = {"logos": logos(hoy), "vitros": vitros(hoy), "pasta_plata": pasta_plata(hoy), "retenidas": retenidas(hoy)}
    return salida if any(salida.values()) else None
