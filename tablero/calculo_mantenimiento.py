"""Mantenimiento y ajuste de moldes/galgas, en vivo desde la app Control Inventarios (cesar.vw_mantenimiento).
Un mantenimiento cuenta el día en que se finalizó; la persona es quien lo entrega."""
import datetime as dt
import statistics
from collections import Counter, defaultdict

from . import db

CATEGORIAS_BASE = ["BMW X5", "Land Rover Sentinel", "Express Van", "BMW Serie 7", "Retrofit"]


def _dia(r):
    return (r["fin"] or r["inicio"]).date()


def calcular(hoy, R):
    desde = hoy - dt.timedelta(days=400)
    filas = db.consultar("""SELECT id, tipo, cod_her, version, pieza, repeticion, estatus, tipo_mant, persona, recibe,
                                   inicio, fin, minutos, vehiculo, categoria, patron
                            FROM cesar.vw_mantenimiento
                            WHERE (inicio >= ? OR fin >= ? OR estatus IN ('Pendiente', 'En proceso'))
                              AND estatus <> 'Cancelado'""", desde, desde)
    categorias = [c["categoria"] for c in db.consultar(
        "SELECT categoria FROM cesar.categoria_vehiculo GROUP BY categoria ORDER BY MIN(orden)")] + ["Retrofit"]
    viejo = R.entero("mant_dias_abierto_viejo", 3)
    meta = R.num("mant_meta_persona_dia", 0)

    for r in filas:
        r["persona"] = (r["persona"] or "Sin registrar").strip().title()
        r["molde"] = f"{r['tipo'] or ''} {r['cod_her'] or ''}".strip()
    fin = [r for r in filas if r["estatus"] == "Finalizado" and (r["fin"] or r["inicio"])]
    abiertos = [r for r in filas if r["estatus"] in ("Pendiente", "En proceso")]
    limite_viejo = dt.datetime.combine(hoy - dt.timedelta(days=viejo), dt.time())
    abiertos_recientes = [r for r in abiertos if r["inicio"] and r["inicio"] >= limite_viejo]

    ayer = hoy - dt.timedelta(days=1)
    hace30 = hoy - dt.timedelta(days=30)
    por_dia = defaultdict(list)
    for r in fin:
        por_dia[_dia(r)].append(r)

    def segs(lista):
        c = Counter(r["categoria"] for r in lista)
        return {k: c[k] for k in categorias if c[k]}

    def mediana(lista):
        m = [r["minutos"] for r in lista if r["minutos"] is not None and 0 < r["minutos"] <= 24 * 60]
        return round(statistics.median(m)) if m else None

    ult30 = [r for r in fin if hace30 <= _dia(r) < hoy]
    dias_con = len({_dia(r) for r in ult30}) or 1

    diaria = []
    for k in range(29, -1, -1):
        d = hoy - dt.timedelta(days=k)
        lista = por_dia.get(d, [])
        diaria.append({"fecha": d.isoformat(), "segs": segs(lista), "total": len(lista), "hoy": d == hoy,
                       "lab": R.es_laboral(d)})
    lunes = hoy - dt.timedelta(days=hoy.weekday())
    semanal = []
    for k in range(11, -1, -1):
        ini = lunes - dt.timedelta(weeks=k)
        lista = [r for d in range(7) for r in por_dia.get(ini + dt.timedelta(days=d), [])]
        semanal.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(),
                        "hasta": (ini + dt.timedelta(days=6)).isoformat(), "segs": segs(lista), "total": len(lista),
                        "en_curso": k == 0})
    mensual = []
    for k in range(11, -1, -1):
        a, m = hoy.year, hoy.month - k
        while m < 1:
            a, m = a - 1, m + 12
        lista = [r for r in fin if (_dia(r).year, _dia(r).month) == (a, m)]
        mensual.append({"etiqueta": f"{a}-{m:02d}", "segs": segs(lista), "total": len(lista), "en_curso": k == 0})

    # Matriz persona x día (últimos 14 días, incluye hoy en vivo)
    dias14 = [hoy - dt.timedelta(days=k) for k in range(13, -1, -1)]
    matriz = defaultdict(lambda: defaultdict(list))
    for d in dias14:
        for r in por_dia.get(d, []):
            matriz[r["persona"]][d].append(r)
    personas = []
    for p, dias in matriz.items():
        celdas = [{"fecha": d.isoformat(), "n": len(dias.get(d, [])), "segs": segs(dias.get(d, [])),
                   "min": mediana(dias.get(d, []))} for d in dias14]
        total = sum(c["n"] for c in celdas)
        activos = sum(1 for c in celdas if c["n"])
        personas.append({"nombre": p, "celdas": celdas, "total": total, "dias_activos": activos,
                         "prom": round(total / activos, 1) if activos else 0,
                         "ayer": len(dias.get(ayer, [])), "hoy": len(dias.get(hoy, []))})
    personas.sort(key=lambda x: -x["total"])

    por_categoria = []
    for c in categorias:
        f30 = [r for r in ult30 if r["categoria"] == c]
        ab = [r for r in abiertos_recientes if r["categoria"] == c]
        top = Counter(r["molde"] for r in f30).most_common(5)
        vehiculos = Counter(r["vehiculo"] or "Sin vehículo" for r in f30).most_common(3)
        por_categoria.append({"categoria": c, "fin_30": len(f30), "abiertos": len(ab), "mediana_min": mediana(f30),
                              "ayer": sum(1 for r in por_dia.get(ayer, []) if r["categoria"] == c),
                              "hoy": sum(1 for r in por_dia.get(hoy, []) if r["categoria"] == c),
                              "galgas": sum(1 for r in f30 if r["tipo"] == "G"),
                              "top_moldes": [{"molde": m, "n": n} for m, n in top],
                              "vehiculos": [{"vehiculo": v, "n": n} for v, n in vehiculos]})

    tipos = Counter((r["tipo_mant"] or "Sin tipo") for r in ult30).most_common()
    reincidentes = Counter((r["molde"], r["categoria"], r["vehiculo"]) for r in ult30).most_common(10)

    return {
        "categorias": categorias,
        "kpis": {
            "hoy": len(por_dia.get(hoy, [])), "ayer": len(por_dia.get(ayer, [])), "fecha_ayer": ayer.isoformat(),
            "personas_ayer": len({r["persona"] for r in por_dia.get(ayer, [])}),
            "personas_hoy": len({r["persona"] for r in por_dia.get(hoy, [])}),
            "prom_dia_30": round(len(ult30) / dias_con, 1), "fin_30": len(ult30),
            "mediana_min_30": mediana(ult30), "abiertos": len(abiertos_recientes),
            "abiertos_viejos": len(abiertos) - len(abiertos_recientes), "dias_viejo": viejo,
            "galgas_30": sum(1 for r in ult30 if r["tipo"] == "G"), "meta_persona_dia": meta or None,
        },
        "diaria": diaria, "semanal": semanal, "mensual": mensual,
        "personas": personas, "dias14": [d.isoformat() for d in dias14],
        "por_categoria": por_categoria,
        "tipos_30": [{"tipo": t, "n": n} for t, n in tipos],
        "reincidentes_30": [{"molde": m, "categoria": c, "vehiculo": v, "n": n} for (m, c, v), n in reincidentes if n > 1],
        "abiertos": sorted(({"id": r["id"], "molde": r["molde"], "vehiculo": r["vehiculo"], "categoria": r["categoria"],
                             "persona": r["persona"], "estatus": r["estatus"], "tipo_mant": r["tipo_mant"],
                             "inicio": r["inicio"].isoformat(timespec="minutes") if r["inicio"] else None}
                            for r in abiertos_recientes), key=lambda x: x["inicio"] or "", reverse=True),
    }
