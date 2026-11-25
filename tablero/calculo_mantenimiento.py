"""Mantenimiento y ajuste de moldes/galgas, en vivo desde la app Control Inventarios (cesar.vw_mantenimiento).
Un mantenimiento cuenta el día en que se finalizó; la persona es quien lo entrega."""
import datetime as dt
import json
import logging
import re
import statistics
from collections import Counter, defaultdict

from . import db

log = logging.getLogger("tablero.mantenimiento")

CATEGORIAS_BASE = ["BMW X5", "Land Rover Sentinel", "Express Van", "BMW Serie 7", "Retrofit"]


def _dia(r):
    return (r["fin"] or r["inicio"]).date()


# Horario de turnos de la planta (12 h): T1 noche, T2 mañana, T3 tarde. El T1 de un día empieza la noche anterior
# (cuando termina el T3) y acaba a las 5:00 a. m.: el T1 del martes va del lunes 8:30 p. m. al martes 5:00 a. m.;
# el del sábado, del viernes 9:00 p. m. al sábado 5:00 a. m. No hay T1 el lunes (domingo en la noche) ni turnos el
# domingo, ni T3 el sábado. lunes=0 … domingo=6.
FIN_T2 = {0: dt.time(13, 0), 1: dt.time(12, 0), 2: dt.time(12, 0), 3: dt.time(12, 0), 4: dt.time(12, 0), 5: dt.time(11, 0)}
FIN_T3 = {0: dt.time(20, 30), 1: dt.time(20, 30), 2: dt.time(20, 30), 3: dt.time(20, 30), 4: dt.time(21, 0)}   # = inicio del T1 del día siguiente
CON_T1 = {1, 2, 3, 4, 5}   # martes a sábado
INICIO_T2 = dt.time(5, 0)


def turno(momento):
    """(día de producción, turno) del momento en que se finalizó: 'T1', 'T2', 'T3' o 'Adicional' (fuera del horario:
    domingo, sábado en la tarde, lunes antes de las 5:00; se suma en su misma fecha)."""
    d, h, w = momento.date(), momento.time(), momento.weekday()
    if h < INICIO_T2:
        return d, ("T1" if w in CON_T1 else "Adicional")
    if w in FIN_T2 and h < FIN_T2[w]:
        return d, "T2"
    if w in FIN_T3 and h < FIN_T3[w]:
        return d, "T3"
    if w in FIN_T3 and (w + 1) % 7 in CON_T1:   # después del T3: es el T1 del día siguiente
        return d + dt.timedelta(days=1), "T1"
    return d, "Adicional"


def _pad(valor, n):
    t = str(valor or "").strip().upper()
    return t.zfill(n) if t.isdigit() and len(t) < n else t


def _llave(cod, version, pieza, repeticion):
    """Misma repetición aunque una tabla guarde '606'/'00' y la otra '0606'/'000'."""
    rep = str(repeticion or "").strip().upper()
    return _pad(cod, 4), _pad(version, 3), _pad(pieza, 3), str(int(rep)) if rep.isdigit() else rep


def guardar_alertas(momento=None):
    """Foto de los moldes POR MANTENIMIENTO en este momento. INV.MANTENIMIENTO_MOLDES_GRUPO solo guarda el
    estado actual; con esta foto (cada pocos minutos) queda qué estuvo en alerta cada día. Devuelve cuántas hay."""
    momento = momento or db.ahora()
    hoy = momento.date()
    alertas = {}
    for r in db.consultar("""SELECT CodHer, Version, Pieza, Repeticion, PuntajeTotalCalculado
                             FROM INV.MANTENIMIENTO_MOLDES_GRUPO
                             WHERE Estado = 'POR MANTENIMIENTO' AND NULLIF(LTRIM(RTRIM(Repeticion)), '') IS NOT NULL"""):
        puntaje = r["PuntajeTotalCalculado"]
        alertas[_llave(r["CodHer"], r["Version"], r["Pieza"], r["Repeticion"])] = float(puntaje) if puntaje is not None else None
    with db.transaccion() as cur:
        if alertas:
            cur.execute("""CREATE TABLE #alerta (cod_her NVARCHAR(20), version NVARCHAR(10), pieza NVARCHAR(10),
                                                 repeticion NVARCHAR(20), puntaje FLOAT)""")
            cur.fast_executemany = True
            cur.executemany("INSERT INTO #alerta VALUES (?, ?, ?, ?, ?)", [k + (p,) for k, p in alertas.items()])
            cur.fast_executemany = False
            cur.execute("""MERGE cesar.mant_alerta AS t
                           USING #alerta AS s
                              ON t.fecha = ? AND t.cod_her = s.cod_her AND t.version = s.version
                             AND t.pieza = s.pieza AND t.repeticion = s.repeticion
                           WHEN MATCHED THEN UPDATE SET hasta = ?, puntaje = s.puntaje
                           WHEN NOT MATCHED THEN INSERT (fecha, cod_her, version, pieza, repeticion, puntaje, desde, hasta)
                                VALUES (?, s.cod_her, s.version, s.pieza, s.repeticion, s.puntaje, ?, ?);""",
                        hoy, momento, hoy, momento, momento)
        # Marca que ese día sí se fotografió (aunque no haya alertas): sin ella el día queda sin dato, no en 0.
        cur.execute("UPDATE cesar.foto_diaria SET valor = ?, actualizado = ? WHERE fecha = ? AND indicador = 'mant_alertas'",
                    len(alertas), momento, hoy)
        if cur.rowcount == 0:
            cur.execute("INSERT INTO cesar.foto_diaria (fecha, indicador, valor, actualizado) VALUES (?, 'mant_alertas', ?, ?)",
                        hoy, len(alertas), momento)
    return len(alertas)


def _pedidos_atendidos(fin, desde, categorias):
    """Por día fotografiado: alertas nuevas (lo que se pidió) y finalizados que atendieron una alerta, por categoría.
    Nueva = no estaba en alerta el día anterior. Atendido = el molde estaba en alerta antes de finalizar ese día, o
    seguía en alerta el día anterior (la alerta se quita al finalizar). Un día cuenta solo si él y el anterior se
    fotografiaron (servidor encendido): el primer día de fotos no sabe qué alertas ya venían de antes."""
    un_dia = dt.timedelta(days=1)
    vistas = defaultdict(dict)
    for a in db.consultar("SELECT fecha, cod_her, version, pieza, repeticion, desde FROM cesar.mant_alerta WHERE fecha >= ?",
                          desde - un_dia):
        vistas[a["fecha"]][_llave(a["cod_her"], a["version"], a["pieza"], a["repeticion"])] = a["desde"]
    fotografiados = set(vistas) | {r["fecha"] for r in db.consultar(
        "SELECT fecha FROM cesar.foto_diaria WHERE indicador = 'mant_alertas' AND fecha >= ?", desde - un_dia)}
    cat_molde = {}
    for r in db.consultar("SELECT cod_molde, categoria FROM cesar.vw_molde_categoria WHERE tipo = 'M'"):
        cat_molde.setdefault(_pad(r["cod_molde"], 4), r["categoria"])

    pedidos, atendidos = {}, {}
    for d in fotografiados:
        if d - un_dia not in fotografiados:
            continue
        antes = vistas.get(d - un_dia, {})
        nuevas = [k for k in vistas.get(d, {}) if k not in antes]
        pedidos[d] = Counter(cat_molde.get(k[0], "Retrofit") for k in nuevas)
        atendidos[d] = Counter()
    for r in fin:
        d = _dia(r)
        if r["tipo"] != "M" or d not in atendidos:
            continue
        k = _llave(r["cod_her"], r["version"], r["pieza"], r["repeticion"])
        visto = vistas.get(d, {}).get(k)
        if (visto is not None and visto <= (r["fin"] or r["inicio"])) or k in vistas.get(d - un_dia, {}):
            atendidos[d][r["categoria"]] += 1

    def por_cat(c):
        return {k: c[k] for k in categorias if c[k]}
    return {d: por_cat(c) for d, c in pedidos.items()}, {d: por_cat(c) for d, c in atendidos.items()}


def _sumar(dias, por_dia):
    """Suma de los días fotografiados del periodo (None si no se fotografió ninguno) y cuántos días tienen dato."""
    con_dato = [por_dia[d] for d in dias if d in por_dia]
    if not con_dato:
        return None, 0
    total = Counter()
    for x in con_dato:
        total.update(x)
    return dict(total), len(con_dato)


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

    # Lo pedido (alertas nuevas) y lo atendido de lo pedido. Si falla, la gráfica sale como antes, sin esas líneas.
    try:
        pedidos, atendidos = _pedidos_atendidos([r for r in fin if _dia(r) >= desde], desde, categorias)
    except Exception:
        log.exception("Pedidos de mantenimiento (cesar.mant_alerta)")
        pedidos, atendidos = {}, {}

    def lo_pedido(dias):
        dias = [d for d in dias if d <= hoy]
        ped, n = _sumar(dias, pedidos)
        ate, _ = _sumar(dias, atendidos)
        return {"ped": ped, "ate": ate, "dias_ped": n, "dias": len(dias)}

    diaria = []
    for k in range(29, -1, -1):
        d = hoy - dt.timedelta(days=k)
        lista = por_dia.get(d, [])
        diaria.append({"fecha": d.isoformat(), "segs": segs(lista), "total": len(lista), "hoy": d == hoy,
                       "lab": R.es_laboral(d), **lo_pedido([d])})
    lunes = hoy - dt.timedelta(days=hoy.weekday())
    semanal = []
    for k in range(11, -1, -1):
        ini = lunes - dt.timedelta(weeks=k)
        dias = [ini + dt.timedelta(days=d) for d in range(7)]
        lista = [r for d in dias for r in por_dia.get(d, [])]
        semanal.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(),
                        "hasta": (ini + dt.timedelta(days=6)).isoformat(), "segs": segs(lista), "total": len(lista),
                        "en_curso": k == 0, **lo_pedido(dias)})
    mensual = []
    for k in range(11, -1, -1):
        a, m = hoy.year, hoy.month - k
        while m < 1:
            a, m = a - 1, m + 12
        lista = [r for r in fin if (_dia(r).year, _dia(r).month) == (a, m)]
        ini = dt.date(a, m, 1)
        dias = [ini + dt.timedelta(days=d) for d in range(31) if (ini + dt.timedelta(days=d)).month == m]
        mensual.append({"etiqueta": f"{a}-{m:02d}", "segs": segs(lista), "total": len(lista), "en_curso": k == 0,
                        **lo_pedido(dias)})

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

    # Registros compactos de lo finalizado (~13 meses) para que el tablero arme cualquier periodo (día, semana,
    # mes) por matricero, tipo de mantenimiento y molde. Cada texto va una sola vez en su lista y las filas
    # guardan índices: [fecha, persona, categoría, tipo de mantenimiento, molde, vehículo, día de producción, turno,
    # versión, pieza, repetición]
    # (día de producción y turno salen de la hora en que se finalizó y el horario de turnos de la planta).
    registros = {"personas": [], "categorias": [], "tipos": [], "moldes": [], "vehiculos": [], "filas": []}
    indices = {k: {} for k in registros if k != "filas"}

    def indice(lista, valor):
        if valor not in indices[lista]:
            indices[lista][valor] = len(registros[lista])
            registros[lista].append(valor)
        return indices[lista][valor]

    for r in sorted(fin, key=_dia):
        dia_prod, tur = turno(r["fin"] or r["inicio"])
        registros["filas"].append([_dia(r).isoformat(), indice("personas", r["persona"]),
                                   indice("categorias", r["categoria"]), indice("tipos", r["tipo_mant"] or "Sin tipo"),
                                   indice("moldes", r["molde"]), indice("vehiculos", r["vehiculo"] or ""),
                                   dia_prod.isoformat(), tur, _pad(r["version"], 3), _pad(r["pieza"], 3),
                                   _llave(None, None, None, r["repeticion"])[3]])

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
        "registros": registros,
        "abiertos": sorted(({"id": r["id"], "molde": r["molde"], "vehiculo": r["vehiculo"], "categoria": r["categoria"],
                             "persona": r["persona"], "estatus": r["estatus"], "tipo_mant": r["tipo_mant"],
                             "inicio": r["inicio"].isoformat(timespec="minutes") if r["inicio"] else None}
                            for r in abiertos_recientes), key=lambda x: x["inicio"] or "", reverse=True),
    }


# ---- Moldes POR MANTENIMIENTO cruzados con el plan de hornos de SmartBending y con las piezas en proceso.
#      Andrés sincroniza SmartBending en la base compartida: AppControlInventarios_PlanDiaSync (el plan del día con
#      sus carros) y AppControlInventarios_EmpalmeSync (piezas en Empalme y en los puestos anteriores con su molde).
#      Rojo = el plan lo va a cargar; naranja = hay piezas esperándolo en un puesto (Empalme primero: es el más cerca
#      del horno); sin puesto = alerta solo por los ciclos que se ha usado.
PUESTOS_PLAN = [("05EMPAL", "Empalme"), ("04SER_VT", "Vitrificado"), ("03SERIG", "Serigrafía"), ("02CNC", "CNC"),
                ("01CORTE", "Corte"), ("PLANEACION", "Planeación")]
MIN_ATRAS_PLAN = 60   # carros del plan de hasta 1 h atrás sin registrar aún cuentan como por cargar


def llave_molde(texto):
    """'M 1244 00 02 Molde de Anillo' -> ('1244', '000', '002')"""
    m = re.match(r"\s*M\s+(\d+)\s+(\d+)\s+(\d+)", str(texto or ""))
    return (_pad(m.group(1), 4), _pad(m.group(2), 3), _pad(m.group(3), 3)) if m else None


def _sync(tabla):
    fila = db.consultar(f"SELECT CAST(Datos AS NVARCHAR(MAX)) AS datos, SincronizadoEn FROM dbo.AppControlInventarios_{tabla}")
    if not fila or not fila[0]["datos"]:
        return {}, None
    sinc = fila[0]["SincronizadoEn"]   # Azure guarda la hora en UTC: se pasa a la hora del PC (Colombia)
    if sinc:
        desfase = dt.datetime.now() - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        sinc = sinc + dt.timedelta(hours=round(desfase.total_seconds() / 3600))
    return json.loads(fila[0]["datos"]), sinc


def _hora(x):
    try:
        return dt.datetime.fromisoformat(str(x)).replace(tzinfo=None)
    except ValueError:
        return None


def _iso(x):
    return x.isoformat(timespec="minutes") if x else None


def plan_alertas(ahora=None):
    ahora = ahora or db.ahora()
    alertas = {}
    for r in db.consultar("""SELECT CodHer, Version, Pieza, Repeticion, PuntajeTotalCalculado, TipoAlerta, FechaPrimeraDeteccion
                             FROM INV.MANTENIMIENTO_MOLDES_GRUPO
                             WHERE Estado = 'POR MANTENIMIENTO' AND NULLIF(LTRIM(RTRIM(Repeticion)), '') IS NOT NULL"""):
        cod, ver, pie, rep = _llave(r["CodHer"], r["Version"], r["Pieza"], r["Repeticion"])
        a = alertas.setdefault((cod, ver, pie), {"reps": [], "puntaje": 0, "desde": None, "especial": False})
        a["reps"].append(rep)
        a["puntaje"] = max(a["puntaje"], float(r["PuntajeTotalCalculado"] or 0))
        a["especial"] |= (r["TipoAlerta"] or "") == "ESPECIAL"
        d = r["FechaPrimeraDeteccion"]
        if d and (a["desde"] is None or d < a["desde"]):
            a["desde"] = d
    categoria = {}
    for r in db.consultar("SELECT cod_molde, vehiculo, categoria FROM cesar.vw_molde_categoria WHERE tipo = 'M'"):
        cat = "Retrofit" if r["categoria"] == "BMW Serie 7" else r["categoria"]
        categoria[_pad(r["cod_molde"], 4)] = (cat, r["vehiculo"])

    plan, plan_sinc = _sync("PlanDiaSync")
    en_plan = {}
    desde = ahora - dt.timedelta(minutes=MIN_ATRAS_PLAN)
    for c in plan.get("carros") or []:
        hora = _hora(c.get("hora"))
        if not hora or hora < desde or (c.get("gestion") or {}).get("estado") == "REGISTRADO":
            continue
        for cs in c.get("casillas") or []:
            k = llave_molde(cs.get("molde"))
            if k not in alertas:
                continue
            e = en_plan.setdefault(k, {"hora": hora, "horno": (c.get("horno") or "").upper(), "turno": c.get("turno"),
                                       "carros": set(), "piezas": 0, "vehiculo": cs.get("vehiculo"), "tipo": cs.get("tipo")})
            if hora < e["hora"]:
                e.update(hora=hora, horno=(c.get("horno") or "").upper(), turno=c.get("turno"))
            e["carros"].add(c.get("carro"))
            e["piezas"] += 1

    wip, wip_sinc = _sync("EmpalmeSync")
    en_puesto = {}
    for x in (wip.get("piezas") or []) + (wip.get("anteriores") or []):
        k = llave_molde(x.get("MoldeCurvado"))
        if k not in alertas or k in en_plan:
            continue
        puesto = str(x.get("Puestodetrabajo") or "").strip().upper()
        e = en_puesto.setdefault(k, {"puestos": Counter(), "vehiculo": None})
        e["puestos"][puesto] += 1
        e["vehiculo"] = e["vehiculo"] or x.get("Vehiculo")
    orden_puesto = {cod: i for i, (cod, _) in enumerate(PUESTOS_PLAN)}
    nombre_puesto = dict(PUESTOS_PLAN)

    def base(k):
        a = alertas[k]
        cat, veh = categoria.get(k[0], ("Retrofit", None))
        return {"molde": f"M {k[0]}", "version": k[1], "pieza": k[2],
                "reps": sorted(a["reps"], key=lambda x: (len(x), x)), "puntaje": round(a["puntaje"]),
                "especial": a["especial"], "categoria": cat, "vehiculo": veh,
                "alerta_desde": a["desde"].date().isoformat() if a["desde"] else None}

    rojo = []
    for k, e in en_plan.items():
        b = base(k)
        rojo.append({**b, "vehiculo": e["vehiculo"] or b["vehiculo"], "tipo": e["tipo"], "hora": _iso(e["hora"]),
                     "horno": e["horno"], "turno": e["turno"], "carros": len(e["carros"]), "piezas": e["piezas"],
                     "atrasado": e["hora"] < ahora})
    rojo.sort(key=lambda x: x["hora"])
    naranja = []
    for k, e in en_puesto.items():
        b = base(k)
        puestos = sorted(e["puestos"].items(), key=lambda x: orden_puesto.get(x[0], 99))
        naranja.append({**b, "vehiculo": b["vehiculo"] or e["vehiculo"],
                        "puesto": nombre_puesto.get(puestos[0][0], puestos[0][0].title()),
                        "orden_puesto": orden_puesto.get(puestos[0][0], 99),
                        "puestos": [{"puesto": nombre_puesto.get(p, p.title()), "n": n} for p, n in puestos]})
    naranja.sort(key=lambda x: (x["orden_puesto"], -sum(p["n"] for p in x["puestos"]), -x["puntaje"]))
    sin_puesto = sorted((base(k) for k in alertas if k not in en_plan and k not in en_puesto), key=lambda x: -x["puntaje"])
    info = plan.get("plan") or {}
    return {"generado": _iso(ahora), "rojo": rojo, "naranja": naranja, "sin_puesto": sin_puesto,
            "plan": {"version": info.get("version"), "dia": info.get("dia"), "estado": info.get("estado"),
                     "generado": (info.get("generado_en") or "")[:16] or None, "sincronizado": _iso(plan_sinc),
                     "hasta": max((c.get("hora") for c in plan.get("carros") or [] if c.get("hora")), default=None)},
            "puestos_sincronizado": _iso(wip_sinc), "orden_puestos": [n for _, n in PUESTOS_PLAN]}
