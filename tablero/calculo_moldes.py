"""Fabricación de moldes y galgas (Fila de moldes.xlsx). La cola usa la misma cuenta del Excel:
horas pendientes / horas por turno = turnos; turnos / matriceros = días de cola."""
import datetime as dt
from collections import defaultdict

from . import db
from .excel import norm


def calcular(hoy, R):
    filas = db.consultar("""SELECT fecha_solicitud, herramental, completo, zhal, vehiculo, fecha_entrega, fabricante,
                                   estatus, patron, tamano, tiempo_h FROM cesar.fila_moldes ORDER BY fila""")
    if not filas:
        return None
    horas_turno = R.num("moldes_horas_turno", 8) or 8
    matriceros = R.num("moldes_matriceros_excel", 0) or R.num("moldes_matriceros", 4) or 4

    for r in filas:
        r["est"] = norm(r["estatus"])
        r["herramental"] = (r["herramental"] or "Otro").strip().capitalize()
        r["vehiculo"] = (r["vehiculo"] or "Sin vehículo").strip()
    # El 26 de diciembre es una "fecha limbo" del Excel (desarrollos sin fecha real): no cuentan en la cola.
    limbo = lambda d: d is not None and (d.month, d.day) == (12, 26)
    pend = [r for r in filas if r["est"] == "PENDIENTE" and not limbo(r["fecha_entrega"])]
    hechos = [r for r in filas if r["est"] == "OK"]
    sin_estatus = sum(1 for r in filas if not r["est"])

    horas = sum(r["tiempo_h"] or 0 for r in pend)
    turnos = horas / horas_turno
    cola_dias = turnos / matriceros if matriceros else 0

    por_vehiculo = defaultdict(lambda: {"n": 0, "horas": 0.0, "grande": 0, "pequeno": 0, "moldes": 0, "galgas": 0,
                                        "entrega": None})
    for r in pend:
        v = por_vehiculo[r["vehiculo"]]
        v["n"] += 1
        v["horas"] += r["tiempo_h"] or 0
        t = norm(r["tamano"])
        v["grande"] += t == "GRANDE"
        v["pequeno"] += t == "PEQUENO"
        v["moldes"] += r["herramental"] == "Molde"
        v["galgas"] += r["herramental"] == "Galga"
        if r["fecha_entrega"] and (v["entrega"] is None or r["fecha_entrega"] < v["entrega"]):
            v["entrega"] = r["fecha_entrega"]
    vehiculos = sorted(({"vehiculo": k, **v, "turnos": round(v["horas"] / horas_turno, 1),
                         "entrega": v["entrega"].isoformat() if v["entrega"] else None}
                        for k, v in por_vehiculo.items()), key=lambda x: (x["entrega"] or "9", -x["horas"]))

    vencidos = [r for r in pend if r["fecha_entrega"] and r["fecha_entrega"] < hoy]
    detalle = sorted(({"herramental": r["herramental"], "codigo": (r["zhal"] or "").strip(), "rep": r["completo"],
                       "vehiculo": r["vehiculo"], "entrega": r["fecha_entrega"].isoformat() if r["fecha_entrega"] else None,
                       "fabricante": r["fabricante"], "tamano": r["tamano"], "horas": r["tiempo_h"],
                       "vencido": bool(r["fecha_entrega"] and r["fecha_entrega"] < hoy)} for r in pend),
                     key=lambda x: (x["entrega"] or "9", x["vehiculo"]))

    lunes = hoy - dt.timedelta(days=hoy.weekday())
    semanal = []
    for k in range(11, -1, -1):
        ini = lunes - dt.timedelta(weeks=k)
        fin = ini + dt.timedelta(days=6)
        sel = [r for r in hechos if r["fecha_entrega"] and ini <= r["fecha_entrega"] <= fin]
        semanal.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(), "hasta": fin.isoformat(),
                        "segs": _segs(sel), "total": len(sel), "horas": sum(r["tiempo_h"] or 0 for r in sel),
                        "en_curso": fin >= hoy})
    mensual = []
    for k in range(11, -1, -1):
        a, m = hoy.year, hoy.month - k
        while m < 1:
            a, m = a - 1, m + 12
        sel = [r for r in hechos if r["fecha_entrega"] and (r["fecha_entrega"].year, r["fecha_entrega"].month) == (a, m)]
        mensual.append({"etiqueta": f"{a}-{m:02d}", "segs": _segs(sel), "total": len(sel),
                        "horas": sum(r["tiempo_h"] or 0 for r in sel), "en_curso": (a, m) == (hoy.year, hoy.month)})

    # Días de fila: días laborales desde hoy hasta la última "Fecha entrega" de lo pendiente (incluye hoy).
    ultima = max((r["fecha_entrega"] for r in pend if r["fecha_entrega"]), default=None)
    dias_fila = sum(1 for k in range(((ultima - hoy).days + 1) if ultima and ultima >= hoy else 0)
                    if R.es_laboral(hoy + dt.timedelta(days=k)))
    # Serie diaria (30 días) de lo fabricado (estatus OK por fecha de entrega) y la semana en curso / la anterior
    por_dia = defaultdict(list)
    for r in hechos:
        if r["fecha_entrega"]:
            por_dia[r["fecha_entrega"]].append(r)
    diaria = [{"fecha": (hoy - dt.timedelta(days=k)).isoformat(), "segs": _segs(por_dia.get(hoy - dt.timedelta(days=k), [])),
               "total": len(por_dia.get(hoy - dt.timedelta(days=k), [])), "hoy": k == 0,
               "lab": R.es_laboral(hoy - dt.timedelta(days=k))} for k in range(29, -1, -1)]
    esta_semana = [r for d in range(7) for r in por_dia.get(lunes + dt.timedelta(days=d), [])]   # misma cuenta que la serie semanal
    semana_pasada = [r for d in range(7) for r in por_dia.get(lunes - dt.timedelta(days=7 - d), [])]

    hace90 = hoy - dt.timedelta(days=90)
    fabricantes = defaultdict(int)
    for r in hechos:
        if r["fecha_entrega"] and hace90 <= r["fecha_entrega"] <= hoy:
            fabricantes[(r["fabricante"] or "Sin registrar").strip().title()] += 1

    return {
        "kpis": {"pendientes": len(pend), "horas": horas, "turnos": round(turnos, 1), "matriceros": matriceros,
                 "cola_dias": round(cola_dias, 1), "vencidos": len(vencidos), "horas_turno": horas_turno,
                 "entregados_30": sum(1 for r in hechos if r["fecha_entrega"] and hoy - dt.timedelta(days=30) <= r["fecha_entrega"] <= hoy),
                 "sin_estatus": sin_estatus, "total_registros": len(filas),
                 "dias_fila": dias_fila, "ultima_entrega": ultima.isoformat() if ultima else None,
                 "pend_moldes": sum(1 for r in pend if r["herramental"] == "Molde"),
                 "pend_galgas": sum(1 for r in pend if r["herramental"] == "Galga"),
                 "semana": _segs(esta_semana), "semana_total": len(esta_semana), "semana_pasada": len(semana_pasada)},
        "diaria": diaria,
        "vehiculos": vehiculos, "detalle": detalle, "semanal": semanal, "mensual": mensual,
        "fabricantes_90": sorted(({"nombre": k, "n": v} for k, v in fabricantes.items()), key=lambda x: -x["n"]),
    }


def _segs(filas):
    s = defaultdict(int)
    for r in filas:
        s[r["herramental"]] += 1
    return dict(s)
