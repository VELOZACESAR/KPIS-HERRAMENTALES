"""Plan de hornos de SmartBending: cuánto del plan se cargó, si el turno va a tiempo, qué moldes pide el plan y qué tan
confiable es el plan (cuándo deja de replanear).

Todo se lee de SmartFactory (solo lectura):
- Hornos_Buffer_Plan: una versión nueva del plan cada ~30 min, con la historia completa.
- Hornos_Buffer_PlanPosicion: los carros de cada versión (hora, horno, zona y órdenes).
- Hornos_Buffer_Cumplimiento: el cumplimiento que SmartBending calcula al cerrar cada turno (el número oficial).
- Hornos_Buffer_PlanVista: el molde de cada orden en la última foto del plan.
- SF_Cargue_SAP_Hornos: los cargues reales.

Un hilo lo recalcula cada 2 minutos y el tablero solo lee el resultado en memoria: abrir la pestaña nunca espera a
SmartFactory. Los días cerrados se leen una sola vez.
"""
import datetime as dt
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

from . import config, db

log = logging.getLogger("plan_hornos")

SEGUNDOS_REFRESCO = 120
DIAS_HISTORIA = 30
DIAS_LINEA_TIEMPO = 14
DIAS_SIN_MOLDE = 7
CICLO_MIN = 30          # SmartBending promete un replaneo cada 30 min
AL_DIA_MIN = 45         # con margen: un plan de hace menos de 45 min está al día
CAIDA_MIN = 75          # más de 75 min sin plan nuevo = se saltó dos o más replaneos
HORAS_PENDIENTES = 3    # moldes del plan que se listan hacia adelante
TURNOS_MIN_DIA = 3       # días cerrados con menos turnos oficiales quedan incompletos (inicio de SmartBending)
DIAS_RETROACTIVO = 2      # cumplimiento calculado días después (recálculos de octubre) sale incompleto: no se usa
FALLOS_API = 2          # fallos seguidos de la API para darla por caída (al publicar versión tropieza unos segundos)

PLANEADO = ("IDENTICO", "EQUIVALENTE", "PARCIAL", "DESVIADO", "NO_EJECUTADO")
EJECUTADO = ("IDENTICO", "EQUIVALENTE", "PARCIAL", "DESVIADO", "ADICIONAL")
PIEZA_OK = ("CUMPLIDO", "CUMPLIDO_SUSTITUCION_EQUIVALENTE")
CORRECCION = "Correccion del cargue"


def norm_molde(texto):
    return " ".join(str(texto or "").split()).upper()


def _iso(x):
    return x.isoformat(timespec="minutes") if x else None


def _fecha(x):
    if isinstance(x, dt.datetime):
        return x.replace(tzinfo=None, microsecond=0)
    return dt.datetime.fromisoformat(str(x)).replace(tzinfo=None, microsecond=0)


def _minutos(a, b):
    return (b - a).total_seconds() / 60


# ---- salud del plan: huecos entre versiones

def huecos(generaciones, ahora):
    """Intervalos sin plan al día y caídas a partir de las horas en que salió cada versión (ordenadas).
    Sin plan al día = desde los 45 min después de una versión hasta la siguiente. Caída = hueco de más de 75 min."""
    sin_plan, caidas = [], []
    pares = list(zip(generaciones, generaciones[1:])) + ([(generaciones[-1], None)] if generaciones else [])
    for previa, siguiente in pares:
        fin = siguiente or ahora
        hueco = _minutos(previa, fin)
        if hueco > AL_DIA_MIN:
            sin_plan.append((previa + dt.timedelta(minutes=AL_DIA_MIN), fin))
        if hueco > CAIDA_MIN:
            caidas.append({"desde": previa, "hasta": siguiente, "minutos": round(hueco), "abierta": siguiente is None})
    return sin_plan, caidas


def minutos_en(intervalos, desde, hasta):
    return sum(max(0.0, _minutos(max(a, desde), min(b, hasta))) for a, b in intervalos)


def confiabilidad(intervalos, desde, hasta):
    total = _minutos(desde, hasta)
    if total <= 0:
        return None
    return max(0.0, 1 - minutos_en(intervalos, desde, hasta) / total)


def cadena(versiones):
    """La sucesión real del plan: el número de versión solo sube dentro del día. A veces SmartBending genera escenarios
    de estudio con números que ya pasaron (tres "v2" a la misma hora); nunca fueron el plan vigente y se descartan."""
    tope, salida = {}, []
    for v in versiones:
        if v["Version"] > tope.get(v["DiaLogico"], 0):
            tope[v["DiaLogico"]] = v["Version"]
            salida.append(v)
    return salida


def cambios_bruscos(versiones, congelados):
    """Cambios que no deberían pasar entre dos versiones seguidas: escenario distinto el mismo día, o carros de la zona
    CONGELADA (aún por cargar) que cambian de órdenes o desaparecen.
    congelados: {Id de versión: {PosicionId: (hora, composición)}}."""
    salida = []
    for a, b in zip(versiones, versiones[1:]):
        if a["DiaLogico"] != b["DiaLogico"]:
            continue
        motivos = []
        if a["Escenario"] != b["Escenario"]:
            motivos.append(f"cambió de escenario: {a['Escenario']} → {b['Escenario']}")
        previos = {k: v for k, v in (congelados.get(a["Id"]) or {}).items() if v[0] > b["GeneradoEn"]}
        nuevos = congelados.get(b["Id"]) or {}
        movidos = sum(1 for k, v in previos.items() if nuevos.get(k, (None, None))[1] != v[1])
        if movidos:
            motivos.append(f"{movidos} de {len(previos)} carros congelados cambiaron")
        if motivos:
            salida.append({"en": b["GeneradoEn"], "version": b["Version"], "dia": b["DiaLogico"], "detalle": "; ".join(motivos),
                           "congelados_movidos": movidos})
    return salida


# ---- cumplimiento por turno

def turno_oficial(detalles):
    """Suma el cumplimiento que SmartBending guarda por horno (DetalleJson) en un solo turno."""
    res = Counter()
    moldes_plan, moldes_ok, sin_molde = {}, set(), []
    inicio = fin = version = None
    for x in detalles:
        turno = x.get("turno") or {}
        inicio, fin = turno.get("inicio") or inicio, turno.get("fin") or fin
        version = (x.get("plan") or {}).get("plan_version") or version
        for f in x.get("filas") or []:
            resultado = f.get("resultado")
            res[resultado] += 1
            if resultado not in PLANEADO:
                continue
            planeado = f.get("planeado") or {}
            for p in f.get("piezas") or []:
                clave = norm_molde(p.get("molde"))
                if clave:
                    moldes_plan.setdefault(clave, p.get("molde"))
                    if p.get("resultado") in PIEZA_OK:
                        moldes_ok.add(clave)
            if f.get("categoria") == "MOLDE_NO_DISPONIBLE":
                sin_molde.append({"hora": planeado.get("hora"), "horno": (f.get("horno") or "").upper(),
                                  "moldes": sorted({p.get("molde") for p in planeado.get("piezas") or [] if p.get("molde")}),
                                  "comentario": f.get("comentario") or "", "resultado": resultado})
    planeados = sum(res[r] for r in PLANEADO)
    cargados = sum(res[r] for r in EJECUTADO)
    return {"inicio": inicio, "fin": fin, "version": version, "oficial": True, "planeados": planeados, "cargados": cargados,
            "a_la_hora": planeados, "identicos": res["IDENTICO"], "equivalentes": res["EQUIVALENTE"], "parciales": res["PARCIAL"],
            "desviados": res["DESVIADO"], "no_ejecutados": res["NO_EJECUTADO"], "adicionales": res["ADICIONAL"],
            "moldes_plan": moldes_plan, "moldes_ok": moldes_ok, "sin_molde": sin_molde}


def turno_en_vivo(posiciones, inicio, fin, ahora, cargues, molde_de):
    """Lo mismo que calcula SmartBending, pero para el turno que aún no ha cerrado (ellos lo publican ~2 h después).
    posiciones: carros del plan con órdenes [{hora, horno, ordenes}]; cargues: [{orden, cargue, hora, razon}]."""
    del_turno = [p for p in posiciones if inicio <= p["hora"] < fin]
    vencidos = [p for p in del_turno if p["hora"] <= ahora]
    corte = min(fin, ahora)
    cargados = {c["cargue"] for c in cargues if inicio <= c["hora"] < corte and not str(c["razon"] or "").startswith(CORRECCION)}
    ordenes_cargadas = {c["orden"] for c in cargues}
    moldes_plan, moldes_ok, piezas = {}, set(), []
    for p in del_turno:
        for orden in p["ordenes"]:
            info = molde_de.get(orden) or {}
            molde = info.get("molde")
            cargada = orden in ordenes_cargadas
            if molde and p["hora"] <= ahora:
                moldes_plan.setdefault(norm_molde(molde), molde)
                if cargada:
                    moldes_ok.add(norm_molde(molde))
            piezas.append({"hora": p["hora"], "horno": p["horno"], "orden": orden, "molde": molde,
                           "vehiculo": info.get("vehiculo"), "cargada": cargada})
    return {"inicio": inicio, "fin": fin, "oficial": False, "en_curso": inicio <= ahora < fin,
            "planeados": len(del_turno), "a_la_hora": len(vencidos), "cargados": len(cargados),
            "moldes_plan": moldes_plan, "moldes_ok": moldes_ok, "piezas": piezas, "sin_molde": []}


def ventanas_turnos(posiciones, inicio_dia):
    """Inicio y fin de cada turno del día lógico según el plan: cada turno va hasta que empieza el siguiente."""
    fin_dia = inicio_dia + dt.timedelta(days=1)
    inicios = {}
    for p in posiciones:
        if p["turno"] and inicio_dia <= p["hora"] < fin_dia:
            inicios[p["turno"]] = min(inicios.get(p["turno"], p["hora"]), p["hora"])
    orden = sorted(inicios.items(), key=lambda x: x[1])
    return [(nombre, ini, orden[i + 1][1] if i + 1 < len(orden) else fin_dia) for i, (nombre, ini) in enumerate(orden)]


def estado_dia(planeados, cargados):
    if not planeados:
        return "sin_plan"
    if cargados > planeados:
        return "sobre"
    if cargados >= planeados * 0.95:
        return "al_dia"
    return "atras"


# ---- lectura de SmartFactory

class _Memoria:
    def __init__(self):
        self.lock = threading.Lock()
        self.datos = None
        self.error = None
        self.error_en = None
        self.oficial = {}          # DiaLogico -> {Turno: turno_oficial}
        self.oficial_hasta = None  # último refresco completo de días cerrados
        self.congelados = {}       # Id de versión -> {PosicionId: (hora, composición)}
        self.vista = (None, {})    # (PlanDbId, molde por orden)
        self.token = None
        self.api_fallos = 0
        self.api_caida_desde = None
        self.api_caidas = []       # caídas de la API vistas por este servidor (se pierden al reiniciar)


_m = _Memoria()


def _versiones(desde):
    return [{**v, "GeneradoEn": _fecha(v["GeneradoEn"])} for v in db.consultar_smart(
        "SELECT Id, DiaLogico, Version, GeneradoEn, Escenario FROM dbo.Hornos_Buffer_Plan WITH (NOLOCK) "
        "WHERE GeneradoEn >= ? ORDER BY GeneradoEn, Id", desde)]


def _leer_oficial(desde_dia):
    filas = db.consultar_smart(
        "SELECT DiaLogico, Turno, Horno, DetalleJson FROM dbo.Hornos_Buffer_Cumplimiento WITH (NOLOCK) "
        "WHERE DiaLogico >= ? AND CalculadoEn < DATEADD(day, ?, CAST(DiaLogico AS datetime2))", desde_dia, DIAS_RETROACTIVO + 1)
    por_turno = {}
    for f in filas:
        try:
            por_turno.setdefault((f["DiaLogico"], f["Turno"]), []).append(json.loads(f["DetalleJson"] or "{}"))
        except ValueError:
            log.warning("Cumplimiento ilegible: %s %s %s", f["DiaLogico"], f["Turno"], f["Horno"])
    salida = {}
    for (dia, turno), detalles in por_turno.items():
        salida.setdefault(dia, {})[turno] = turno_oficial(detalles)
    return salida


def _oficial(ahora):
    """Los días cerrados se leen una vez; hoy y ayer se vuelven a leer en cada refresco."""
    hoy = ahora.date()
    if _m.oficial_hasta is None:
        _m.oficial = _leer_oficial(hoy - dt.timedelta(days=DIAS_HISTORIA + 1))
    else:
        recientes = _leer_oficial(hoy - dt.timedelta(days=1))
        _m.oficial = {d: t for d, t in _m.oficial.items() if d < hoy - dt.timedelta(days=1)}
        _m.oficial.update(recientes)
    _m.oficial_hasta = ahora
    limite = hoy - dt.timedelta(days=DIAS_HISTORIA + 1)
    _m.oficial = {d: t for d, t in _m.oficial.items() if d >= limite}
    return _m.oficial


def _posiciones(plan_id):
    salida = []
    for p in db.consultar_smart(
            "SELECT PosicionId, Turno, HornoCorto, HoraEstimada, Zona, EsSeparador, ComposicionSnapshot "
            "FROM dbo.Hornos_Buffer_PlanPosicion WITH (NOLOCK) WHERE PlanDbId = ?", plan_id):
        try:
            ordenes = [str(o) for o in json.loads(p["ComposicionSnapshot"] or "{}").values() if o]
        except ValueError:
            ordenes = []
        if p["EsSeparador"] or not ordenes:
            continue
        salida.append({"id": p["PosicionId"], "turno": p["Turno"], "horno": (p["HornoCorto"] or "").upper(),
                       "hora": _fecha(p["HoraEstimada"]), "ordenes": ordenes})
    return salida


def _inicio_dia(plan_id, dia):
    fila = db.consultar_smart("SELECT ParametrosJson FROM dbo.Hornos_Buffer_Plan WITH (NOLOCK) WHERE Id = ?", plan_id)
    try:
        return _fecha(json.loads(fila[0]["ParametrosJson"])["segmentos"][0]["desde"])
    except (IndexError, KeyError, TypeError, ValueError):
        return dt.datetime.combine(dia - dt.timedelta(days=1), dt.time(21))


def _molde_por_orden(dia):
    fila = db.consultar_smart(
        "SELECT TOP 1 PlanDbId FROM dbo.Hornos_Buffer_PlanVista WITH (NOLOCK) WHERE DiaLogico = ? ORDER BY PlanDbId DESC", dia)
    if not fila:
        return {}
    plan_id = fila[0]["PlanDbId"]
    if _m.vista[0] == plan_id:
        return _m.vista[1]
    cargues = json.loads(db.consultar_smart(
        "SELECT CarguesJson FROM dbo.Hornos_Buffer_PlanVista WITH (NOLOCK) WHERE PlanDbId = ?", plan_id)[0]["CarguesJson"] or "[]")
    salida = {}
    for carro in cargues if isinstance(cargues, list) else []:
        for p in (carro.get("posiciones") or {}).values():
            if p and p.get("orden"):
                salida[str(p["orden"])] = {"molde": p.get("molde_curvado"), "vehiculo": p.get("vehiculo")}
    _m.vista = (plan_id, salida)
    return salida


def _cargues(desde):
    return [{"orden": str(c["Orden"]), "cargue": c["Cargue_Unico"], "hora": _fecha(c["Fecha_cargue_PowerAPP"]),
             "razon": c["Razon"], "molde": c["Molde"]}
            for c in db.consultar_smart(
                "SELECT Orden, Cargue_Unico, Fecha_cargue_PowerAPP, Razon, Molde FROM dbo.SF_Cargue_SAP_Hornos WITH (NOLOCK) "
                "WHERE Fecha_cargue_PowerAPP >= ?", desde)
            if c["Fecha_cargue_PowerAPP"]]


def _congelados(versiones):
    """Carros de la zona CONGELADA de cada versión; solo se leen las versiones nuevas."""
    faltan = [v["Id"] for v in versiones if v["Id"] not in _m.congelados]
    for i in range(0, len(faltan), 400):
        lote = faltan[i:i + 400]
        for v in lote:
            _m.congelados[v] = {}
        for p in db.consultar_smart(
                f"SELECT PlanDbId, PosicionId, HoraEstimada, ComposicionSnapshot FROM dbo.Hornos_Buffer_PlanPosicion WITH (NOLOCK) "
                f"WHERE Zona = 'CONGELADA' AND PlanDbId IN ({','.join('?' * len(lote))})", *lote):
            _m.congelados[p["PlanDbId"]][p["PosicionId"]] = (_fecha(p["HoraEstimada"]), p["ComposicionSnapshot"])
    vigentes = {v["Id"] for v in versiones}
    _m.congelados = {k: v for k, v in _m.congelados.items() if k in vigentes}
    return _m.congelados


def _pedir(url, cuerpo=None, token=None, timeout=10):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method="POST" if cuerpo is not None else "GET",
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _probar_api(ahora):
    """¿La API de SmartBending responde? Con el rol público OPERARIO, el mismo que usa la pantalla del plan."""
    base = config.SMARTBENDING_API_URL.rstrip("/")
    t = time.time()
    try:
        for intento in range(2):
            if not _m.token:
                _m.token = _pedir(f"{base}/auth/login-public", {"rol": "OPERARIO"})["token"]
            try:
                _pedir(f"{base}/plan-buffer/vigente/version", token=_m.token)
                break
            except urllib.error.HTTPError as e:
                if e.code != 401 or intento:
                    raise
                _m.token = None
        ms = round((time.time() - t) * 1000)
        if _m.api_caida_desde:
            _m.api_caidas.append({"desde": _m.api_caida_desde, "hasta": ahora})
            _m.api_caidas = _m.api_caidas[-50:]
        _m.api_fallos, _m.api_caida_desde = 0, None
        return {"ok": True, "ms": ms, "en": _iso(ahora)}
    except Exception as e:
        _m.token = None
        _m.api_fallos += 1
        if _m.api_fallos >= FALLOS_API and not _m.api_caida_desde:
            _m.api_caida_desde = ahora - dt.timedelta(seconds=SEGUNDOS_REFRESCO * (FALLOS_API - 1))
        return {"ok": _m.api_fallos < FALLOS_API, "tropiezo": True, "error": type(e).__name__, "en": _iso(ahora),
                "fallos": _m.api_fallos}


# ---- armado

def _resumen_turno(nombre, dia, t):
    pct = t["cargados"] / t["a_la_hora"] if t["a_la_hora"] else None
    salida = {k: v for k, v in t.items() if k not in ("moldes_plan", "moldes_ok", "piezas", "sin_molde")}
    return {**salida, "turno": nombre, "dia": dia.isoformat(), "inicio": _iso(_fecha(t["inicio"])) if t["inicio"] else None,
            "fin": _iso(_fecha(t["fin"])) if t["fin"] else None, "pct": pct,
            "moldes_exigidos": len(t["moldes_plan"]), "moldes_cargados": len(t["moldes_ok"])}


def _ordenados(turnos):
    return dict(sorted(turnos.items(), key=lambda x: _fecha(x[1]["inicio"]) if x[1]["inicio"] else dt.datetime.min))


def _turnos_del_dia(dia, version, oficial, ahora, cargues, molde_de):
    """Turnos oficiales de SmartBending + los que aún no publica (en curso o recién cerrados), calculados igual."""
    turnos = dict(oficial.get(dia) or {})
    if version:
        posiciones = _posiciones(version["Id"])
        for nombre, ini, fin in ventanas_turnos(posiciones, _inicio_dia(version["Id"], dia)):
            if nombre not in turnos and ini <= ahora:
                turnos[nombre] = turno_en_vivo(posiciones, ini, fin, ahora, cargues, molde_de)
    return _ordenados(turnos)


def construir(ahora=None):
    ahora = ahora or db.ahora()
    versiones = cadena(_versiones(ahora - dt.timedelta(days=DIAS_HISTORIA + 1)))
    if not versiones:
        raise RuntimeError("SmartFactory no tiene versiones del plan en los últimos días")
    oficial = _oficial(ahora)
    vigente = versiones[-1]
    hoy = vigente["DiaLogico"]
    ayer = hoy - dt.timedelta(days=1)
    ultima_ayer = next((v for v in reversed(versiones) if v["DiaLogico"] == ayer), None)
    cargues = _cargues(ahora - dt.timedelta(days=2))
    molde_de = _molde_por_orden(hoy)

    dias = {hoy: _turnos_del_dia(hoy, vigente, oficial, ahora, cargues, molde_de),
            ayer: _turnos_del_dia(ayer, ultima_ayer, oficial, ahora, cargues, molde_de)}
    for d, t in oficial.items():
        dias.setdefault(d, _ordenados(t))

    generaciones = [v["GeneradoEn"] for v in versiones]
    sin_plan, caidas = huecos(generaciones, ahora)
    cambios = cambios_bruscos(versiones, _congelados(versiones))
    api = _probar_api(ahora)

    diario = []
    for d in sorted(dias):
        ts = list(dias[d].values())
        if d < ahora.date() - dt.timedelta(days=DIAS_HISTORIA) or (d not in (hoy, ayer) and len(ts) < TURNOS_MIN_DIA):
            continue
        ini_d = dt.datetime.combine(d - dt.timedelta(days=1), dt.time(21))
        planeados = sum(t["a_la_hora"] for t in ts)
        cargados = sum(t["cargados"] for t in ts)
        diario.append({"dia": d.isoformat(), "hoy": d == hoy, "planeados": planeados, "cargados": cargados,
                       "pct": cargados / planeados if planeados else None,
                       "identicos": sum(t.get("identicos", 0) + t.get("equivalentes", 0) for t in ts if t["oficial"]),
                       "planeados_oficiales": sum(t["planeados"] for t in ts if t["oficial"]),
                       "sin_molde": sum(len(t["sin_molde"]) for t in ts),
                       "confiabilidad": confiabilidad(sin_plan, ini_d, min(ini_d + dt.timedelta(days=1), ahora)),
                       "versiones": sum(1 for g in generaciones if ini_d <= g < ini_d + dt.timedelta(days=1))})

    turnos_hoy = dias[hoy]
    planeados = sum(t["a_la_hora"] for t in turnos_hoy.values())
    cargados = sum(t["cargados"] for t in turnos_hoy.values())
    oficiales = [t for t in turnos_hoy.values() if t["oficial"]]
    actual = next(((n, t) for n, t in turnos_hoy.items() if t.get("en_curso")), None)

    moldes_plan, moldes_ok = {}, set()
    for t in turnos_hoy.values():
        moldes_plan.update(t["moldes_plan"])
        moldes_ok |= t["moldes_ok"]
    pendientes = []
    for t in turnos_hoy.values():
        for p in t.get("piezas") or []:
            if not p["cargada"] and p["hora"] <= ahora + dt.timedelta(hours=HORAS_PENDIENTES) and p["hora"] >= ahora - dt.timedelta(hours=8):
                pendientes.append({**p, "hora": _iso(p["hora"]), "atrasada": p["hora"] < ahora})
    pendientes.sort(key=lambda p: (p["hora"], p["horno"]))
    sin_molde = []
    for d in sorted(dias, reverse=True):
        if d < hoy - dt.timedelta(days=DIAS_SIN_MOLDE - 1):
            continue
        for nombre, t in dias[d].items():
            sin_molde += [{**s, "dia": d.isoformat(), "turno": nombre} for s in t["sin_molde"]]

    edad = _minutos(vigente["GeneradoEn"], ahora)
    if edad > CAIDA_MIN:
        estado = "caido"
    elif not api["ok"]:
        estado = "api"
    elif edad > AL_DIA_MIN:
        estado = "atrasado"
    else:
        estado = "ok"
    linea_desde = dt.datetime.combine(hoy - dt.timedelta(days=DIAS_LINEA_TIEMPO), dt.time(21))
    linea = []
    for i in range(DIAS_LINEA_TIEMPO):
        a = linea_desde + dt.timedelta(days=i)
        b = a + dt.timedelta(days=1)
        linea.append({"dia": b.date().isoformat(), "desde": _iso(a),
                      "versiones": [round(_minutos(a, g)) for g in generaciones if a <= g < b],
                      "sin_plan": [[round(_minutos(a, max(x, a))), round(_minutos(a, min(y, b)))] for x, y in sin_plan if x < b and y > a],
                      "caidas": [[round(_minutos(a, max(c["desde"], a))), round(_minutos(a, min(c["hasta"] or ahora, b)))]
                                 for c in caidas if c["desde"] < b and (c["hasta"] or ahora) > a],
                      "hasta_min": round(min(_minutos(a, ahora), 1440)),
                      "confiabilidad": confiabilidad(sin_plan, a, min(b, ahora)) if a < ahora else None})

    return {
        "conectado": True, "generado": _iso(ahora), "dia": hoy.isoformat(),
        "hoy": {"planeados": planeados, "cargados": cargados, "pct": cargados / planeados if planeados else None,
                "diferencia": cargados - planeados, "estado": estado_dia(planeados, cargados),
                "identicos": sum(t["identicos"] + t["equivalentes"] for t in oficiales),
                "planeados_oficiales": sum(t["planeados"] for t in oficiales),
                "turnos_oficiales": len(oficiales), "turnos": len(turnos_hoy)},
        "turno": _resumen_turno(actual[0], hoy, actual[1]) if actual else None,
        "turnos": [_resumen_turno(n, d, t) for d in (ayer, hoy) for n, t in dias[d].items()],
        "moldes": {"exigidos": len(moldes_plan), "cargados": len(moldes_plan.keys() & moldes_ok),
                   "pendientes": pendientes[:60], "sin_molde": sin_molde[:80],
                   "sin_molde_dias": DIAS_SIN_MOLDE},
        "diario": diario,
        "salud": {
            "estado": estado, "api": api,
            "ultima_version": {"version": vigente["Version"], "generado": _iso(vigente["GeneradoEn"]),
                               "escenario": vigente["Escenario"], "hace_min": round(edad)},
            "confiabilidad_hoy": diario[-1]["confiabilidad"] if diario else None,
            "confiabilidad_7": confiabilidad(sin_plan, ahora - dt.timedelta(days=7), ahora),
            "confiabilidad_30": confiabilidad(sin_plan, ahora - dt.timedelta(days=DIAS_HISTORIA), ahora),
            "caidas_30": sum(1 for c in caidas if c["desde"] >= ahora - dt.timedelta(days=DIAS_HISTORIA)),
            "horas_caido_30": round(sum(c["minutos"] for c in caidas if c["desde"] >= ahora - dt.timedelta(days=DIAS_HISTORIA)) / 60, 1),
            "caidas": [{**c, "desde": _iso(c["desde"]), "hasta": _iso(c["hasta"])}
                       for c in reversed(caidas) if c["desde"] >= ahora - dt.timedelta(days=DIAS_HISTORIA)],
            "cambios": [{**c, "en": _iso(c["en"]), "dia": c["dia"].isoformat()}
                        for c in reversed(cambios) if c["en"] >= ahora - dt.timedelta(days=DIAS_HISTORIA)],
            "api_caidas": [{"desde": _iso(c["desde"]), "hasta": _iso(c["hasta"])} for c in reversed(_m.api_caidas)]
                          + ([{"desde": _iso(_m.api_caida_desde), "hasta": None}] if _m.api_caida_desde else []),
            "linea": linea,
            "reglas": {"ciclo_min": CICLO_MIN, "al_dia_min": AL_DIA_MIN, "caida_min": CAIDA_MIN},
        },
    }


def refrescar():
    t = time.time()
    try:
        datos = construir()
        with _m.lock:
            _m.datos, _m.error, _m.error_en = datos, None, None
        log.info("Plan de hornos en %.1fs", time.time() - t)
    except Exception as e:
        log.exception("Plan de hornos")
        with _m.lock:
            _m.error, _m.error_en = f"{type(e).__name__}: {e}"[:300], db.ahora()


def _ciclo():
    while True:
        refrescar()
        time.sleep(SEGUNDOS_REFRESCO)


def iniciar():
    if db.hay_smartfactory():
        threading.Thread(target=_ciclo, name="plan_hornos", daemon=True).start()


def calcular():
    """Lo que pinta la pestaña: nunca consulta SmartFactory, solo devuelve el último cálculo."""
    if not db.hay_smartfactory():
        return {"conectado": False}
    with _m.lock:
        if _m.datos is None:
            return {"conectado": True, "calculando": _m.error is None, "error": _m.error}
        if _m.error:
            return {**_m.datos, "aviso": _m.error, "aviso_en": _iso(_m.error_en)}
        return _m.datos
