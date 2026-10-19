"""Piezas retenidas / refundidas en piso (Aceros): registro manual por número de orden.

La tabla cesar.aceros_retenidas_piso solo guarda la orden, el día del registro y un estatus. El compromiso, ZHAL,
acero, fecha de entrega (fabricación) y matricero se leen del consolidado al mostrarlas, así siempre están al día.
Cuántas se registran cada día es la línea "Piezas retenidas" de la gráfica de producción de aceros."""
import datetime as dt

from . import db

ESTATUS = ["Retenida", "Refundida", "En reproceso", "Liberada"]


def _detalle(ordenes):
    """orden → datos del consolidado (una orden puede tener varios aceros)."""
    ordenes = sorted({o for o in ordenes if o})
    salida = {}
    for i in range(0, len(ordenes), 500):
        lote = ordenes[i:i + 500]
        filas = db.consultar(f"""SELECT orden, zhal, acero, vehiculo, entrega_produccion, fecha_fabricacion, operario, puesto_trabajo
                                 FROM cesar.aceros_consolidado WHERE orden IN ({', '.join('?' * len(lote))})""", *lote)
        for r in filas:
            salida.setdefault(r["orden"], []).append(r)
    unir = lambda xs: ", ".join(dict.fromkeys(str(x).strip() for x in xs if x not in (None, "")))
    datos = {}
    for o, rs in salida.items():
        compromisos = [r["entrega_produccion"] for r in rs if r["entrega_produccion"]]
        entregas = [r["fecha_fabricacion"] for r in rs if r["fecha_fabricacion"]]
        datos[o] = {"compromiso": min(compromisos).isoformat() if compromisos else None,
                    "entrega": max(entregas).isoformat() if entregas else None,
                    "zhal": unir(r["zhal"] for r in rs), "acero": unir(r["acero"] for r in rs),
                    "vehiculo": unir(r["vehiculo"] for r in rs), "matricero": unir(r["operario"] for r in rs),
                    "puesto": unir(r["puesto_trabajo"] for r in rs)}
    return datos


def buscar(orden):
    """Datos de una orden en el consolidado (para mostrarlos antes de guardarla)."""
    return _detalle([orden]).get(orden)


def listar(hoy, dias=400):
    if not db.consultar("SELECT OBJECT_ID('cesar.aceros_retenidas_piso') AS id")[0]["id"]:
        return None   # la tabla aún no existe: falta correr instalar_bd.py
    filas = db.consultar("""SELECT id, orden, fecha, estatus, usuario FROM cesar.aceros_retenidas_piso
                            WHERE fecha >= ? ORDER BY fecha DESC, id DESC""", hoy - dt.timedelta(days=dias))
    det = _detalle(f["orden"] for f in filas)
    return {"estatus": ESTATUS,
            "filas": [{"id": f["id"], "orden": f["orden"], "fecha": f["fecha"].isoformat(), "estatus": f["estatus"],
                       "usuario": f["usuario"], "encontrada": f["orden"] in det, **det.get(f["orden"], {})} for f in filas]}


def agregar(orden, estatus, usuario, ip):
    ahora = db.ahora()
    with db.transaccion() as cur:
        cur.execute("""INSERT INTO cesar.aceros_retenidas_piso (orden, fecha, estatus, creado, usuario, ip)
                       OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)""", orden, ahora.date(), estatus, ahora, usuario, ip)
        return cur.fetchone()[0]


def actualizar(id_, estatus, usuario):
    with db.transaccion() as cur:
        cur.execute("UPDATE cesar.aceros_retenidas_piso SET estatus = ?, actualizado = ?, usuario = ? WHERE id = ?",
                    estatus, db.ahora(), usuario, id_)
        return cur.rowcount > 0


def borrar(id_):
    with db.transaccion() as cur:
        cur.execute("DELETE FROM cesar.aceros_retenidas_piso WHERE id = ?", id_)
        return cur.rowcount > 0
