# -*- coding: utf-8 -*-
"""
Genera "Tablero de Indicadores.html" con los KPIs del área de Herramentales.

Fuentes (Excel sincronizados desde SharePoint con OneDrive):
  - Aceros: "Consolidado inventario de aceros.xlsx"  -> hojas 3.Consolidado y 9. Rechazos
  - Aceros: "Inventario Aceros X5.xlsx"              -> segunda hoja (inventario BMW X5)
  - Aceros: "Control de pedidos.xlsx" (hoja Historial Cortes) -> aceros enviados a cortar (Prioridad1 + Prioridad2)
  - Aceros: valores manuales (en fabricación, X5 en fabricación) se escriben en el tablero
  - Mantenimiento de moldes, Fabricación de moldes, Serigrafía -> pendientes de conectar

Uso:  python generar_tablero.py
Se ejecuta cada hora con el Programador de tareas (ver "Programar actualizacion cada hora.bat").
Las reglas de cálculo replican el módulo de KPIs del mockup "mockup_aceros_co01.html".
"""
import ctypes
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import unicodedata
from collections import defaultdict
from pathlib import Path

import openpyxl

# ============================== CONFIGURACIÓN ==============================
CARPETA = Path(__file__).resolve().parent
ONEDRIVE = Path(os.environ.get("OneDriveCommercial") or (Path.home() / "OneDrive - AGP GROUP"))

RUTA_CONSOLIDADO = ONEDRIVE / "GRP - INGENIERIA PROYECTOS 2022 - Colombia - Fulll kit de aceros" / "Consolidado inventario de aceros.xlsx"
RUTA_X5 = ONEDRIVE / "Tecnico de Herramentales" / "Inventario Aceros X5.xlsx"
RUTA_PEDIDOS = ONEDRIVE / "GRP - INGENIERIA PROYECTOS 2022 - Colombia - Fulll kit de aceros" / "Control de pedidos.xlsx"
PLANTILLA = CARPETA / "plantilla_tablero.html"
SALIDA = CARPETA / "Tablero de Indicadores.html"
LOG = CARPETA / "generar_tablero.log"
HISTORIAL = CARPETA / "historial_indicadores.json"   # foto diaria de indicadores que el consolidado no guarda (piezas retenidas, fila)

META_ACEROS_DIA = 50           # meta diaria de aceros (valor inicial; se puede cambiar a mano en el tablero)
META_ACEROS_POR_TURNO = 20     # meta por matricero por turno de 8 h (3 matriceros = 60 aceros/día)
DIAS_PROMEDIO_PRODUCTIVIDAD = 7   # promedio de los últimos 7 días con producción
DIAS_LABORALES = {0, 1, 2, 3, 4, 5}   # lunes a sábado (0 = lunes)

FESTIVOS = {dt.date(2026, m, d) for m, d in [
    (1, 1), (1, 12), (3, 23), (4, 2), (4, 3), (5, 1), (5, 18), (6, 8), (6, 15), (6, 29),
    (7, 13), (7, 20), (8, 7), (8, 17), (10, 12), (11, 2), (11, 16), (12, 8), (12, 25)]}

MATERIALES = {  # texto en columna L (mayúsculas) -> nombre mostrado
    "BOHLER": "Böhler", "INOX 2,5MM": "Inox 2,5mm", "GALVANIAZO 0,3MM": "Galvanizado 0,3mm",
    "GALVANIZADO 0,3MM": "Galvanizado 0,3mm", "GALVANIZADO": "Galvanizado 0,3mm",
    "INOX 1MM": "Inox 1mm", "INOX 3MM": "Inox 3mm", "GURKHA": "Gurkha",
}
ORDEN_MATERIALES = ["Böhler", "Inox 2,5mm", "Galvanizado 0,3mm", "Inox 3mm", "Inox 1mm", "Gurkha", "Otro"]

# Factor de acero equivalente por material y número de pieza (columna J). Si no está -> 1.
EQUIVALENCIAS = {
    "Böhler": {1: 1, 2: 1, 3: 1, 4: 1},
    "Inox 2,5mm": {5: .5, 6: .5, 7: .5, 8: .5, 19: .5, 20: .5, 9: 3, 11: 1.2, 12: 1.2},
    "Gurkha": {41: 3, 1: 5, 2: 5, 3: 5, 4: 5, 9: 5},
    "Galvanizado 0,3mm": {1: .5, 2: .5, 3: .5, 4: .5, 11: .5, 12: .5, 0: 1},
}

OPERARIOS_EXCLUIDOS = {  # no son producción real (motivos o personas fuera de la meta)
    "MANUEL GOMEZ", "JOHAN FRANCO", "AVANZADA SIN MOTIVO", "CIERRE TECNICO", "JEFFERSON MAECHA",
    "JEFFERSON MAHECHA", "NMI", "ERROR DE INGENIERIA", "NMI ERROR DE INGENIERIA", "PIEZA CANCELADA",
    "ALEX ACOSTA", "CANCELADO",
}
OPERARIOS_VACIOS = {"-", "‐", "—", "N/A", "NA", "NAN", "NULL", "NONE", "S/N", "0"}
ALIAS_OPERARIOS = {"OSWALDO CASTEBLANCO": "OSWALDO CASTELBLANCO"}

PUESTOS = [("01CORTE", "Corte"), ("02CNC", "CNC"), ("03SERIG", "Serigrafía"), ("04SER_VT", "Vitrificado"),
           ("05EMPAL", "Empalme"), ("06CURVAD", "Curvado"), ("07RECORT", "Recorte")]

# Servicios aún sin fuente de datos: se muestran como "Pendiente de conectar"
SERVICIOS_PENDIENTES = [
    {"id": "mantenimiento", "nombre": "Mantenimiento y ajuste de moldes",
     "necesita": ["Registro de órdenes de trabajo: molde, tipo (preventivo/correctivo), falla, inicio y fin, técnico, estado",
                  "Plan diario o semanal de órdenes"]},
    {"id": "moldes", "nombre": "Fabricación de moldes",
     "necesita": ["Proyectos con fecha compromiso y etapa actual", "Horas estimadas vs. reales por etapa y retrabajos"]},
    {"id": "serigrafia", "nombre": "Serigrafía",
     "necesita": ["Solicitudes y entregas de pantallas con fecha", "Rechazos y bajas de pantallas con su causa"]},
]
# ===========================================================================


def log(msg):
    linea = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linea)
    try:
        previo = LOG.read_text(encoding="utf-8").splitlines()[-300:] if LOG.exists() else []
        LOG.write_text("\n".join(previo + [linea]) + "\n", encoding="utf-8")
    except OSError:
        pass


def copia_temporal(ruta: Path) -> Path:
    """Copia el Excel a una carpeta temporal. Así se puede leer aunque alguien lo tenga abierto en Excel."""
    destino = Path(tempfile.gettempdir()) / f"tablero_{ruta.name}"
    if os.name == "nt":
        if not ctypes.windll.kernel32.CopyFileW(str(ruta), str(destino), False):
            raise OSError(f"No se pudo copiar {ruta.name} (código {ctypes.GetLastError()})")
    else:
        shutil.copyfile(ruta, destino)
    return destino


def texto_norm(v):
    s = unicodedata.normalize("NFD", str(v if v is not None else ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def fecha(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,})", v)
        if m:
            d, mes, a = int(m[1]), int(m[2]), m[3]
            a = int(a[-4:]) if len(a) >= 4 else dt.date.today().year
            try:
                return dt.date(a, mes, d)
            except ValueError:
                return None
    return None


def material(v):
    return MATERIALES.get(str(v or "").strip().upper(), "Otro")


def factor_equivalente(mat, pieza):
    try:
        return EQUIVALENCIAS.get(mat, {}).get(int(float(pieza)), 1)
    except (TypeError, ValueError):
        return 1


def clasificar_operario(v):
    """('vacio'|'excluido'|'ok', nombre en formato Título)."""
    clave = texto_norm(v)
    if not clave or clave in OPERARIOS_VACIOS:
        return "vacio", None
    clave = ALIAS_OPERARIOS.get(clave, clave)
    if clave in OPERARIOS_EXCLUIDOS:
        return "excluido", None
    return "ok", clave.title()


def es_motivo_fuera_de_meta(v):
    t = texto_norm(v)
    return "CIERRE TECNICO" in t or "AVANZADA SIN MOTIVO" in t


def es_laboral(d):
    return d.weekday() in DIAS_LABORALES and d not in FESTIVOS


def filas(ws):
    for r in ws.iter_rows(values_only=True):
        yield list(r) + [None] * 30


def celda(r, i):
    return r[i] if i < len(r) else None


# ------------------------------------------------------------------ ACEROS
def calcular_aceros(hoy):
    avisos = []
    archivo = copia_temporal(RUTA_CONSOLIDADO)
    modificado = dt.datetime.fromtimestamp(RUTA_CONSOLIDADO.stat().st_mtime)
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)

    fab_events, fila_pend, compromisos, comp_detalle = [], [], [], []
    fila_nmi = 0
    por_orden = defaultdict(list)
    for i, r in enumerate(filas(wb["3.Consolidado"])):
        if i == 0 or r[2] is None:
            continue
        mat = material(r[11])
        corte = str(r[10] or "")
        nmi = "NMI" in corte.upper()
        entrega, fab = fecha(r[12]), fecha(r[21])
        if fab and not (dt.date(2020, 1, 1) <= fab <= hoy):
            fab = None                                   # fechas mal digitadas (0206, 2029…) no cuentan
        tipo_op, nombre_op = clasificar_operario(r[22])
        eq = factor_equivalente(mat, r[9])

        if r[22] is None or str(r[22]).strip() == "":   # fila en fabricación = columna W (Operario) vacía…
            if nmi:
                fila_nmi += 1                              # …sin contar "Corte NMI" (no es fila real; mismas reglas que productividad)
            else:
                fila_pend.append((entrega, mat))
        if entrega and not nmi and tipo_op != "excluido" and not es_motivo_fuera_de_meta(r[22]):
            # cumplido = fabricado en la fecha comprometida o antes (no importa qué día); después de la fecha ya no cumple.
            # Filas con operario excluido (canceladas, errores, personas fuera de la meta) no son compromiso.
            hecho = fab is not None and fab <= entrega
            compromisos.append((entrega, mat, hecho))
            if hoy - dt.timedelta(days=10) <= entrega < hoy:   # detalle para la tarjeta de ayer
                comp_detalle.append({"entrega": entrega, "hecho": hecho, "mat": mat, "orden": r[2], "acero": r[5],
                                     "vehiculo": r[6], "fab": fab.isoformat() if fab else None,
                                     "puesto": str(r[13] or "").strip()})
        if fab and tipo_op != "excluido" and not nmi:
            fab_events.append({"fecha": fab, "mat": mat, "eq": eq, "op": nombre_op,
                               "rechazo": "RECHAZ" in corte.upper()})
        if not nmi:   # "Corte NMI" no hace parte de ningún indicador
            por_orden[r[2]].append({"entrega": entrega, "fab": fab, "op": r[22], "puesto": str(r[13] or "").strip(),
                                    "mat": mat, "corte": corte, "zhal": r[4], "acero": r[5], "vehiculo": r[6]})

    # ---- día de referencia ("ayer"): día anterior; si fue domingo/festivo sin producción, retrocede
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

    # ---- serie diaria: todos los días desde el 1 de enero (o 12 semanas atrás) hasta ayer.
    #      El tablero muestra los últimos 14 y la usa para el zoom de semanas y meses.
    #      "lab" = día laboral; la meta la pone el usuario en el tablero (meta diaria × días laborales).
    lunes_ayer = ayer - dt.timedelta(days=ayer.weekday())
    inicio = min(dt.date(ayer.year, 1, 1), lunes_ayer - dt.timedelta(weeks=11))
    diaria, d = [], inicio
    while d <= ayer:
        ev = prod_por_dia.get(d, [])
        diaria.append({"fecha": d.isoformat(), "segs": segs(ev), "total": len(ev),
                       "eq": round(sum(e["eq"] for e in ev), 1), "lab": es_laboral(d),
                       "nota": "Festivo" if d in FESTIVOS else ("Domingo" if d.weekday() == 6 else "")})
        d += dt.timedelta(days=1)

    # ---- serie semanal (12 semanas ISO) y mensual (año actual); días laborales transcurridos hasta ayer
    def dias_lab(ini, fin):
        n, d = 0, ini
        while d <= min(fin, ayer):
            n += es_laboral(d)
            d += dt.timedelta(days=1)
        return n

    def meta_rango(ini, fin):
        return dias_lab(ini, fin) * META_ACEROS_DIA

    semanal = []
    for k in range(11, -1, -1):
        ini = lunes_ayer - dt.timedelta(weeks=k)
        fin = ini + dt.timedelta(days=6)
        ev = [e for e in fab_events if ini <= e["fecha"] <= min(fin, ayer)]
        semanal.append({"etiqueta": f"Sem {ini.isocalendar()[1]}", "desde": ini.isoformat(), "hasta": fin.isoformat(),
                        "segs": segs(ev), "total": len(ev), "eq": round(sum(e["eq"] for e in ev), 1),
                        "meta": meta_rango(ini, fin), "dias_lab": dias_lab(ini, fin),
                        "dias_lab_total": sum(es_laboral(ini + dt.timedelta(days=k)) for k in range(7)),
                        "en_curso": fin > ayer})
    mensual = []
    for mes in range(1, ayer.month + 1):
        ini = dt.date(ayer.year, mes, 1)
        fin = (dt.date(ayer.year + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1))
        ev = [e for e in fab_events if ini <= e["fecha"] <= min(fin, ayer)]
        mensual.append({"etiqueta": ini.strftime("%m"), "desde": ini.isoformat(), "hasta": fin.isoformat(),
                        "segs": segs(ev), "total": len(ev), "eq": round(sum(e["eq"] for e in ev), 1),
                        "meta": meta_rango(ini, fin), "dias_lab": dias_lab(ini, fin), "en_curso": fin > ayer})

    # ---- cumplimiento de compromisos (por fecha de entrega, col. M), día por día: ~11 meses hacia atrás
    #      (días laborales o con compromisos) + los próximos 30 días que ya tienen aceros asignados.
    #      El tablero agrupa por semana/mes y muestra 10 barras.
    comp_dia = defaultdict(lambda: {"total": 0, "hechos": 0, "segs": defaultdict(int)})
    for d, mat, hecho in compromisos:
        c = comp_dia[d]
        c["total"] += 1
        if hecho:
            c["hechos"] += 1
            c["segs"][mat] += 1
    # solo hasta 30 días adelante: hay fechas de relleno muy lejanas (ej. 31-dic-2028) que no son compromisos reales
    cumplimiento, d = [], hoy - dt.timedelta(days=335)
    while d <= hoy + dt.timedelta(days=30):
        c = comp_dia.get(d)
        if (c and c["total"]) or (d <= ayer and es_laboral(d)):
            cumplimiento.append({"fecha": d.isoformat(), "comprometidos": c["total"] if c else 0,
                                 "hechos": c["hechos"] if c else 0, "segs": dict(c["segs"]) if c else {},
                                 "futuro": d > ayer})
        d += dt.timedelta(days=1)

    # ---- fila de corte (columna W vacía), por fecha de compromiso (columna M)
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
    # días de fila = días distintos con aceros pendientes desde hoy (incluido) en adelante
    dias_fila = len({d for d, _ in fila_pend if d and d >= hoy})

    # ---- productividad promedio: media de los últimos 7 días con producción
    dias_con_prod = sorted((d for d in prod_por_dia if d <= ayer), reverse=True)[:DIAS_PROMEDIO_PRODUCTIVIDAD]
    prom = sum(len(prod_por_dia[d]) for d in dias_con_prod) / len(dias_con_prod) if dias_con_prod else 0

    # ---- productividad por persona: ayer y semana en curso (meta 22 por turno)
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
          "meta_semana": META_ACEROS_POR_TURNO * max(1, len(v["dias"]))}
         for n, v in personas.items() if v["ayer"] or v["semana"]],
        key=lambda x: (-x["ayer"], -x["semana"]))

    # ---- piezas sin acero en planta (por orden: la entrega real más reciente o el compromiso más reciente)
    cuellos = {c: [] for c, _ in PUESTOS}
    for orden, regs in por_orden.items():
        reales = [x for x in regs if x["fab"] and texto_norm(x["op"])]
        if reales:
            continue
        x = max(regs, key=lambda x: x["entrega"] or dt.date.min)
        if x["puesto"] in cuellos:
            cuellos[x["puesto"]].append({"orden": orden, "compromiso": x["entrega"].isoformat() if x["entrega"] else None,
                                         "zhal": x["zhal"], "acero": x["acero"], "material": x["mat"],
                                         "corte": x["corte"], "vehiculo": x["vehiculo"]})
    cuellos_out = [{"codigo": c, "puesto": n, "n": len(cuellos[c]),
                    "detalle": sorted(cuellos[c], key=lambda x: x["compromiso"] or "9")} for c, n in PUESTOS]

    # ---- rechazos (hoja 9. Rechazos)
    rechazos = []
    for i, r in enumerate(filas(wb["9. Rechazos"])):
        f = fecha(r[6])
        if i == 0 or r[0] is None or not f:
            continue
        rechazos.append({"orden": r[0], "zhal": r[2], "acero": r[3], "vehiculo": r[4], "plano": r[5], "fecha": f})
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
    wb.close()

    ev_ayer = prod_por_dia.get(ayer, [])
    # aceros entregados ayer por cada matricero (col. W + col. V); los que no tienen nombre se muestran aparte
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
        "fuente": {"archivo": RUTA_CONSOLIDADO.name, "modificado": modificado.isoformat(timespec="minutes")},
        "ayer": {
            "fecha": ayer.isoformat(), "fabricados": len(ev_ayer), "eq": round(sum(e["eq"] for e in ev_ayer), 1),
            "segs": segs(ev_ayer), "meta": META_ACEROS_DIA,
            "comprometidos": comp_dia[ayer]["total"], "comprometidos_hechos": comp_dia[ayer]["hechos"],
            "comprometidos_segs": dict(comp_dia[ayer]["segs"]),
            "no_cumplidos": sorted(({k: v for k, v in c.items() if k not in ("entrega", "hecho")}
                                    for c in comp_detalle if c["entrega"] == ayer and not c["hecho"]),
                                   key=lambda x: (x["fab"] is None, x["fab"] or "", str(x["orden"]))),
            "matriceros": matriceros_ayer,
            "rechazos": sum(1 for x in rechazos if x["fecha"] == ayer),
            "rechazos_prom": round(len(rech_30) / max(1, dias_lab_30), 1),
            "personas_meta": sum(1 for p in personas_out if p["ayer"] >= META_ACEROS_POR_TURNO),
            "personas": sum(1 for p in personas_out if p["ayer"]),
        },
        "kpis": {
            "fila": len(fila_pend), "dias_fila": dias_fila, "fila_nmi": fila_nmi,
            "vencidos": fila_buckets[0]["total"],
            "productividad": round(prom, 1), "dias_prom": DIAS_PROMEDIO_PRODUCTIVIDAD,
            "retenidas": sum(c["n"] for c in cuellos_out),
            "pct_rechazo_30": round(100 * sum(e["rechazo"] for e in fab_30) / len(fab_30), 1) if fab_30 else 0,
            "rechazos_30": len(rech_30),
        },
        "diaria": diaria, "semanal": semanal, "mensual": mensual, "cumplimiento": cumplimiento,
        "fila": fila_buckets, "personas": personas_out, "meta_turno": META_ACEROS_POR_TURNO,
        "meta_dia_defecto": META_ACEROS_DIA,   # valor inicial; la meta diaria se cambia a mano en el tablero
        "cuellos": cuellos_out,
        "rechazos_semanal": rech_sem,
        # rechazos de las 12 semanas de la gráfica, para el zoom por días de cada semana
        "rechazos_12s": [dict(x, fecha=x["fecha"].isoformat())
                         for x in sorted(rechazos, key=lambda x: x["fecha"], reverse=True)
                         if x["fecha"] >= lunes_ayer - dt.timedelta(weeks=11)],
        "avisos": avisos,
    }


def leer_inventario_x5():
    """Segunda hoja de 'Inventario Aceros X5.xlsx': FECHA | PIEZA | INVENTARIO MATRICERIA | INVENTARIO CALIDAD | TOTAL."""
    wb = openpyxl.load_workbook(copia_temporal(RUTA_X5), read_only=True, data_only=True)
    ws = wb.worksheets[1]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    for h, r in enumerate(rows):
        t = [texto_norm(x) for x in r]
        if "PIEZA" in t and any("MATRICERIA" in x for x in t):
            cp, cm = t.index("PIEZA"), next(i for i, x in enumerate(t) if "MATRICERIA" in x)
            cc = next((i for i, x in enumerate(t) if "CALIDAD" in x), None)
            cf = t.index("FECHA") if "FECHA" in t else None
            break
    else:
        raise ValueError(f'No encontré la tabla PIEZA / INVENTARIO MATRICERIA en la hoja "{ws.title}"')

    num = lambda v: float(v) if isinstance(v, (int, float)) else 0
    out, f = [], None
    for r in rows[h + 1:]:
        pieza = r[cp] if cp < len(r) else None
        if pieza is None or str(pieza).strip() == "" or texto_norm(pieza) == "TOTAL":
            break
        if cf is not None and not f:
            f = fecha(r[cf])
        mat, cal = num(r[cm]), num(r[cc]) if cc is not None else 0
        out.append({"pieza": str(pieza).strip(), "matriceria": mat, "calidad": cal})
    return {"fecha": f.isoformat() if f else None, "hoja": ws.title, "filas": out}


def leer_enviados_a_cortar(hoy):
    """Aceros enviados a cortar: hoja "Historial Cortes" de "Control de pedidos.xlsx".
    Columnas: Servicio | Fecha | Material | Comentario | #Marcos | ... Solo cuentan los comentarios Prioridad1 y Prioridad2;
    se suma #Marcos por fecha."""
    wb = openpyxl.load_workbook(copia_temporal(RUTA_PEDIDOS), read_only=True, data_only=True)
    ws = wb["Historial Cortes"]
    por_dia = defaultdict(lambda: {"total": 0, "prioridad": defaultdict(int), "material": defaultdict(int)})
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not r or len(r) < 5:
            continue
        m = re.search(r"PRIORIDAD\s*([12])\b", texto_norm(r[3]))
        f, n = fecha(r[1]), r[4]
        if not m or not f or not isinstance(n, (int, float)):
            continue
        d = por_dia[f]
        d["total"] += n
        d["prioridad"]["Prioridad" + m.group(1)] += n
        d["material"][str(r[2] or "Sin material").strip()] += n
    wb.close()
    def resumen(f):
        d = por_dia.get(f)
        return {"fecha": f.isoformat(), "total": d["total"] if d else 0,
                "prioridad": dict(d["prioridad"]) if d else {}, "material": dict(d["material"]) if d else {}}
    anteriores = sorted(f for f in por_dia if f < hoy)
    return {"hoy": resumen(hoy), "ultimo_anterior": resumen(anteriores[-1]) if anteriores else None,
            "modificado": dt.datetime.fromtimestamp(RUTA_PEDIDOS.stat().st_mtime).isoformat(timespec="minutes")}


def guardar_historial(hoy, kpis):
    """Guarda (y devuelve) la foto del día: la última ejecución del día sobrescribe la anterior.
    Así se arma la historia de piezas retenidas y fila, que el consolidado no conserva."""
    try:
        hist = json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else {}
    except (OSError, ValueError):
        hist = {}
    hist[hoy.isoformat()] = {"retenidas": kpis["retenidas"], "fila": kpis["fila"], "dias_fila": kpis["dias_fila"]}
    HISTORIAL.write_text(json.dumps(hist, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    limite = (hoy - dt.timedelta(days=120)).isoformat()
    return {k: v for k, v in hist.items() if k >= limite}


def main():
    hoy = dt.date.today()
    datos = {"generado": dt.datetime.now().isoformat(timespec="minutes"), "hoy": hoy.isoformat(),
             "orden_materiales": ORDEN_MATERIALES, "pendientes": SERVICIOS_PENDIENTES, "errores": [],
             "festivos": sorted(f.isoformat() for f in FESTIVOS)}

    try:
        datos["aceros"] = calcular_aceros(hoy)
        datos["aceros"]["historial"] = guardar_historial(hoy, datos["aceros"]["kpis"])
    except Exception as e:
        datos["aceros"] = None
        datos["errores"].append(f"Aceros (consolidado): {e}")
        log(traceback.format_exc())
    for clave, fn, nombre in [("x5", leer_inventario_x5, "Inventario X5"),
                              ("cortes", lambda: leer_enviados_a_cortar(hoy), "Control de pedidos (enviados a cortar)")]:
        try:
            datos[clave] = fn()
        except Exception as e:
            datos[clave] = None
            datos["errores"].append(f"{nombre}: {e}")
            log(traceback.format_exc())

    html = PLANTILLA.read_text(encoding="utf-8")
    js = json.dumps(datos, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = html.replace("/*__DATOS__*/null", js)
    tmp = SALIDA.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, SALIDA)   # reemplazo atómico: el navegador nunca ve un archivo a medio escribir
    log(f"Tablero generado ({len(datos['errores'])} errores) -> {SALIDA.name}")
    for err in datos["errores"]:
        log("  ERROR " + err)
    return 1 if datos["aceros"] is None else 0


if __name__ == "__main__":
    sys.exit(main())
