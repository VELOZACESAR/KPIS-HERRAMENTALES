"""Indicadores de aceros a partir de cesar.aceros_consolidado / aceros_rechazos / pedidos_corte / x5_inventario.
Las reglas son las mismas del tablero original de Herramentales; solo cambió de dónde salen los datos."""
import datetime as dt
import re
from collections import defaultdict

from . import db
from .excel import norm

PUESTOS = [("01CORTE", "Corte"), ("02CNC", "CNC"), ("03SERIG", "Serigrafía"), ("04SER_VT", "Vitrificado"),
           ("05EMPAL", "Empalme"), ("06CURVAD", "Curvado"), ("07RECORT", "Recorte")]


def _fuera_de_meta(v):
    t = norm(v)
    return "CIERRE TECNICO" in t or "AVANZADA SIN MOTIVO" in t


def calcular(hoy, R):
    meta_dia = R.entero("meta_aceros_dia", 50)
    meta_turno = R.entero("meta_aceros_turno", 20)
    dias_prom = R.entero("dias_promedio_productividad", 7)
    es_laboral = R.es_laboral

    filas = db.consultar("""SELECT orden, zhal, acero, vehiculo, pieza, corte, material, entrega_produccion,
                                   puesto_trabajo, fecha_fabricacion, operario
                            FROM cesar.aceros_consolidado ORDER BY fila""")
    fab_events, fila_pend, compromisos, comp_detalle = [], [], [], []
    fila_nmi = 0
    por_orden = defaultdict(list)
    for r in filas:
        mat = R.material(r["material"])
        corte = r["corte"] or ""
        nmi = "NMI" in corte.upper()
        entrega, fab = r["entrega_produccion"], r["fecha_fabricacion"]
        if fab and not (dt.date(2020, 1, 1) <= fab <= hoy):
            fab = None
        tipo_op, nombre_op = R.operario(r["operario"])
        eq = R.factor(mat, r["pieza"])
        puesto = (r["puesto_trabajo"] or "").strip()

        if r["operario"] is None:
            if nmi:
                fila_nmi += 1
            else:
                fila_pend.append((entrega, mat))
        if entrega and not nmi and tipo_op != "excluido" and not _fuera_de_meta(r["operario"]):
            hecho = fab is not None and fab <= entrega
            compromisos.append((entrega, mat, hecho, fab is not None and fab > entrega))   # último: entregado tarde
            if hoy - dt.timedelta(days=10) <= entrega < hoy:
                comp_detalle.append({"entrega": entrega, "hecho": hecho, "mat": mat, "orden": r["orden"], "acero": r["acero"],
                                     "vehiculo": r["vehiculo"], "fab": fab.isoformat() if fab else None, "puesto": puesto})
        if fab and tipo_op != "excluido" and not nmi:
            fab_events.append({"fecha": fab, "mat": mat, "eq": eq, "op": nombre_op, "rechazo": "RECHAZ" in corte.upper()})
        if not nmi:
            por_orden[r["orden"]].append({"entrega": entrega, "fab": fab, "op": r["operario"], "puesto": puesto, "mat": mat,
                                          "corte": corte, "zhal": r["zhal"], "acero": r["acero"], "vehiculo": r["vehiculo"]})

    prod_por_dia = defaultdict(list)
    for e in fab_events:
        prod_por_dia[e["fecha"]].append(e)
    ayer = hoy - dt.timedelta(days=1)
    while not es_laboral(ayer) and not prod_por_dia.get(ayer):
        ayer -= dt.timedelta(days=1)

    def segs(eventos):
        s = defaultdict(int)
        for e in eventos:
            s[e["mat"]] += 1
        return dict(s)

    lunes_ayer = ayer - dt.timedelta(days=ayer.weekday())
    inicio = min(dt.date(ayer.year, 1, 1), lunes_ayer - dt.timedelta(weeks=11))
    diaria, d = [], inicio
    while d <= ayer:
        ev = prod_por_dia.get(d, [])
        diaria.append({"fecha": d.isoformat(), "segs": segs(ev), "total": len(ev),
                       "eq": round(sum(e["eq"] for e in ev), 1), "lab": es_laboral(d),
                       "nota": "Festivo" if d in R.festivos else ("Domingo" if d.weekday() == 6 else "")})
        d += dt.timedelta(days=1)

    def dias_lab(ini, fin):
        n, d = 0, ini
        while d <= min(fin, ayer):
            n += es_laboral(d)
            d += dt.timedelta(days=1)
        return n

    semanal = []
    for k in range(11, -1, -1):
        ini = lunes_ayer - dt.timedelta(weeks=k)
        fin = ini + dt.timedelta(days=6)
        ev = [e for e in fab_events if ini <= e["fecha"] <= min(fin, ayer)]
        semanal.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(), "hasta": fin.isoformat(),
                        "segs": segs(ev), "total": len(ev), "eq": round(sum(e["eq"] for e in ev), 1),
                        "meta": dias_lab(ini, fin) * meta_dia, "dias_lab": dias_lab(ini, fin),
                        "dias_lab_total": sum(es_laboral(ini + dt.timedelta(days=j)) for j in range(7)),
                        "en_curso": fin > ayer})
    mensual = []
    for mes in range(1, ayer.month + 1):
        ini = dt.date(ayer.year, mes, 1)
        fin = dt.date(ayer.year + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1)
        ev = [e for e in fab_events if ini <= e["fecha"] <= min(fin, ayer)]
        mensual.append({"etiqueta": ini.strftime("%m"), "desde": ini.isoformat(), "hasta": fin.isoformat(),
                        "segs": segs(ev), "total": len(ev), "eq": round(sum(e["eq"] for e in ev), 1),
                        "meta": dias_lab(ini, fin) * meta_dia, "dias_lab": dias_lab(ini, fin), "en_curso": fin > ayer})

    comp_dia = defaultdict(lambda: {"total": 0, "hechos": 0, "tarde": 0, "segs": defaultdict(int)})
    for d, mat, hecho, tarde in compromisos:
        c = comp_dia[d]
        c["total"] += 1
        if hecho:
            c["hechos"] += 1
            c["segs"][mat] += 1
        elif tarde:          # se fabricó, pero después de la fecha comprometida: cierra la barra con otro color
            c["tarde"] += 1
    # Solo hasta 30 días adelante: hay fechas de relleno muy lejanas (ej. 31-dic-2028) que no son compromisos reales.
    cumplimiento, d = [], hoy - dt.timedelta(days=335)
    while d <= hoy + dt.timedelta(days=30):
        c = comp_dia.get(d)
        if (c and c["total"]) or (d <= ayer and es_laboral(d)):
            cumplimiento.append({"fecha": d.isoformat(), "comprometidos": c["total"] if c else 0,
                                 "hechos": c["hechos"] if c else 0, "tarde": c["tarde"] if c else 0,
                                 "segs": dict(c["segs"]) if c else {},
                                 "futuro": d > ayer})
        d += dt.timedelta(days=1)

    fila_buckets = [{"etiqueta": "Vencidos", "clave": "vencidos", "segs": defaultdict(int), "total": 0}]
    for k in range(7):
        d = hoy + dt.timedelta(days=k)
        fila_buckets.append({"etiqueta": d.isoformat(), "clave": d.isoformat(), "segs": defaultdict(int), "total": 0})
    fila_buckets.append({"etiqueta": "Después", "clave": "despues", "segs": defaultdict(int), "total": 0})
    sin_fecha = {"etiqueta": "Sin fecha", "clave": "sinfecha", "segs": defaultdict(int), "total": 0}
    for d, mat in fila_pend:
        b = sin_fecha if d is None else fila_buckets[min(0 if d < hoy else (d - hoy).days + 1, len(fila_buckets) - 1)]
        b["segs"][mat] += 1
        b["total"] += 1
    if sin_fecha["total"]:
        fila_buckets.append(sin_fecha)
    for b in fila_buckets:
        b["segs"] = dict(b["segs"])
    dias_fila = len({d for d, _ in fila_pend if d and d >= hoy})

    dias_con_prod = sorted((d for d in prod_por_dia if d <= ayer), reverse=True)[:dias_prom]
    prom = sum(len(prod_por_dia[d]) for d in dias_con_prod) / len(dias_con_prod) if dias_con_prod else 0

    personas = defaultdict(lambda: {"ayer": 0, "ayer_eq": 0.0, "semana": 0, "dias": set()})
    for e in fab_events:
        if not e["op"]:
            continue
        p = personas[e["op"]]
        if e["fecha"] == ayer:
            p["ayer"] += 1
            p["ayer_eq"] += e["eq"]
        if lunes_ayer <= e["fecha"] <= ayer:
            p["semana"] += 1
            p["dias"].add(e["fecha"])
    personas_out = sorted(
        [{"nombre": n, "ayer": v["ayer"], "ayer_eq": round(v["ayer_eq"], 1), "semana": v["semana"],
          "meta_semana": meta_turno * max(1, len(v["dias"]))}
         for n, v in personas.items() if v["ayer"] or v["semana"]],
        key=lambda x: (-x["ayer"], -x["semana"]))

    cuellos = {c: [] for c, _ in PUESTOS}
    for orden, regs in por_orden.items():
        if any(x["fab"] and norm(x["op"]) for x in regs):
            continue
        x = max(regs, key=lambda x: x["entrega"] or dt.date.min)
        if x["puesto"] in cuellos:
            cuellos[x["puesto"]].append({"orden": orden, "compromiso": x["entrega"].isoformat() if x["entrega"] else None,
                                         "zhal": x["zhal"], "acero": x["acero"], "material": x["mat"],
                                         "corte": x["corte"], "vehiculo": x["vehiculo"]})
    cuellos_out = [{"codigo": c, "puesto": n, "n": len(cuellos[c]),
                    "detalle": sorted(cuellos[c], key=lambda x: x["compromiso"] or "9")} for c, n in PUESTOS]

    rechazos = [r for r in db.consultar("SELECT orden, zhal, acero, vehiculo, plano, fecha FROM cesar.aceros_rechazos "
                                        "WHERE fecha IS NOT NULL ORDER BY fila") ]
    rech_sem = []
    for k in range(11, -1, -1):
        ini = lunes_ayer - dt.timedelta(weeks=k)
        rech_sem.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(),
                         "total": sum(1 for x in rechazos if ini <= x["fecha"] <= ini + dt.timedelta(days=6)),
                         "en_curso": ini + dt.timedelta(days=6) > ayer})
    hace30 = ayer - dt.timedelta(days=29)
    rech_30 = [x for x in rechazos if hace30 <= x["fecha"] <= ayer]
    dias_lab_30 = sum(es_laboral(hace30 + dt.timedelta(days=k)) for k in range(30))
    fab_30 = [e for e in fab_events if hace30 <= e["fecha"] <= ayer]

    ev_ayer = prod_por_dia.get(ayer, [])
    por_matricero = defaultdict(lambda: {"n": 0, "eq": 0.0, "segs": defaultdict(int)})
    for e in ev_ayer:
        m = por_matricero[e["op"] or "Sin matricero registrado"]
        m["n"] += 1
        m["eq"] += e["eq"]
        m["segs"][e["mat"]] += 1
    matriceros_ayer = sorted([{"nombre": k, "n": v["n"], "eq": round(v["eq"], 1), "segs": dict(v["segs"])}
                              for k, v in por_matricero.items()],
                             key=lambda x: (x["nombre"] == "Sin matricero registrado", -x["n"]))
    return {
        "ayer": {
            "fecha": ayer.isoformat(), "fabricados": len(ev_ayer), "eq": round(sum(e["eq"] for e in ev_ayer), 1),
            "segs": segs(ev_ayer), "meta": meta_dia,
            "comprometidos": comp_dia[ayer]["total"], "comprometidos_hechos": comp_dia[ayer]["hechos"],
            "comprometidos_segs": dict(comp_dia[ayer]["segs"]), "comprometidos_tarde": comp_dia[ayer]["tarde"],
            "no_cumplidos": sorted(({k: v for k, v in c.items() if k not in ("entrega", "hecho")}
                                    for c in comp_detalle if c["entrega"] == ayer and not c["hecho"]),
                                   key=lambda x: (x["fab"] is None, x["fab"] or "", str(x["orden"]))),
            "matriceros": matriceros_ayer,
            "rechazos": sum(1 for x in rechazos if x["fecha"] == ayer),
            "rechazos_prom": round(len(rech_30) / max(1, dias_lab_30), 1),
            "personas_meta": sum(1 for p in personas_out if p["ayer"] >= meta_turno),
            "personas": sum(1 for p in personas_out if p["ayer"]),
        },
        "kpis": {
            "fila": len(fila_pend), "dias_fila": dias_fila, "fila_nmi": fila_nmi,
            "vencidos": fila_buckets[0]["total"],
            "productividad": round(prom, 1), "dias_prom": dias_prom,
            "retenidas": sum(c["n"] for c in cuellos_out),
            "pct_rechazo_30": round(100 * sum(e["rechazo"] for e in fab_30) / len(fab_30), 1) if fab_30 else 0,
            "rechazos_30": len(rech_30),
        },
        "diaria": diaria, "semanal": semanal, "mensual": mensual, "cumplimiento": cumplimiento,
        "fila": fila_buckets, "personas": personas_out, "meta_turno": meta_turno, "meta_dia_defecto": meta_dia,
        "cuellos": cuellos_out, "rechazos_semanal": rech_sem,
        "rechazos_12s": [dict(x, fecha=x["fecha"].isoformat())
                         for x in sorted(rechazos, key=lambda x: x["fecha"], reverse=True)
                         if x["fecha"] >= lunes_ayer - dt.timedelta(weeks=11)],
        "avisos": [],
    }


def enviados_a_cortar(hoy):
    """Aceros enviados a cortar (Control de pedidos, hoja Historial Cortes): Prioridad1 + Prioridad2 por fecha."""
    filas = db.consultar("SELECT fecha, material, comentario, marcos FROM cesar.pedidos_corte "
                         "WHERE fecha IS NOT NULL AND marcos IS NOT NULL")
    por_dia = defaultdict(lambda: {"total": 0, "prioridad": defaultdict(int), "material": defaultdict(int)})
    for r in filas:
        m = re.search(r"PRIORIDAD\s*([12])\b", norm(r["comentario"]))
        if not m:
            continue
        d = por_dia[r["fecha"]]
        n = r["marcos"]
        n = int(n) if float(n).is_integer() else n
        d["total"] += n
        d["prioridad"]["Prioridad" + m.group(1)] += n
        d["material"][(r["material"] or "Sin material").strip()] += n

    def resumen(f):
        d = por_dia.get(f)
        return {"fecha": f.isoformat(), "total": d["total"] if d else 0,
                "prioridad": dict(d["prioridad"]) if d else {}, "material": dict(d["material"]) if d else {}}

    anteriores = sorted(f for f in por_dia if f < hoy)
    lunes = hoy - dt.timedelta(days=hoy.weekday())
    semanas = []
    for k in range(11, -1, -1):
        ini = lunes - dt.timedelta(weeks=k)
        dias = [por_dia.get(ini + dt.timedelta(days=j)) for j in range(7)]
        semanas.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(),
                        "p1": sum(x["prioridad"].get("Prioridad1", 0) for x in dias if x),
                        "p2": sum(x["prioridad"].get("Prioridad2", 0) for x in dias if x)})
    return {"hoy": resumen(hoy), "ultimo_anterior": resumen(anteriores[-1]) if anteriores else None, "semanal": semanas}


def inventario_x5():
    filas = db.consultar("SELECT pieza, matriceria, calidad FROM cesar.x5_inventario ORDER BY fila")
    if not filas:
        return None
    hist = db.consultar("""SELECT fecha, SUM(matriceria) AS matriceria, SUM(calidad) AS calidad
                           FROM cesar.x5_inventario_diario WHERE fecha >= ?
                           GROUP BY fecha ORDER BY fecha""", dt.date.today() - dt.timedelta(days=90))
    return {"filas": [{"pieza": r["pieza"], "matriceria": r["matriceria"] or 0, "calidad": r["calidad"] or 0} for r in filas],
            "historial": [{"fecha": r["fecha"].isoformat(), "matriceria": r["matriceria"], "calidad": r["calidad"]} for r in hist]}
