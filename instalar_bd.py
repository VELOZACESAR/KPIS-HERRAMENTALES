"""Crea/actualiza el esquema cesar en AGP_Ingenieria y siembra la configuración inicial.
Se puede correr cuantas veces sea: no pisa lo que ya se haya ajustado a mano en las tablas."""
import datetime as dt
import json
import re
import sys

from tablero import config, db
from tablero.festivos import festivos

MATERIALES = {
    "BOHLER": "Böhler", "INOX 2,5MM": "Inox 2,5mm", "GALVANIAZO 0,3MM": "Galvanizado 0,3mm",
    "GALVANIZADO 0,3MM": "Galvanizado 0,3mm", "GALVANIZADO": "Galvanizado 0,3mm",
    "INOX 1MM": "Inox 1mm", "INOX 3MM": "Inox 3mm", "GURKHA": "Gurkha",
}
ORDEN_MATERIALES = [("Böhler", "#7FB0AE"), ("Inox 2,5mm", "#8FA8C7"), ("Galvanizado 0,3mm", "#D9BC6C"),
                    ("Inox 3mm", "#B98089"), ("Inox 1mm", "#9BB894"), ("Gurkha", "#CA9682"), ("Otro", "#8A9499")]
EQUIVALENCIAS = {
    "Böhler": {1: 1, 2: 1, 3: 1, 4: 1},
    "Inox 2,5mm": {5: .5, 6: .5, 7: .5, 8: .5, 19: .5, 20: .5, 9: 3, 11: 1.2, 12: 1.2},
    "Gurkha": {41: 3, 1: 5, 2: 5, 3: 5, 4: 5, 9: 5},
    "Galvanizado 0,3mm": {1: .5, 2: .5, 3: .5, 4: .5, 11: .5, 12: .5, 0: 1},
}
OPERARIOS_EXCLUIDOS = ["MANUEL GOMEZ", "JOHAN FRANCO", "AVANZADA SIN MOTIVO", "CIERRE TECNICO", "JEFFERSON MAECHA",
                       "JEFFERSON MAHECHA", "NMI", "ERROR DE INGENIERIA", "NMI ERROR DE INGENIERIA", "PIEZA CANCELADA",
                       "ALEX ACOSTA", "CANCELADO"]
OPERARIOS_VACIOS = ["-", "‐", "—", "N/A", "NA", "NAN", "NULL", "NONE", "S/N", "0"]
ALIAS = {"OSWALDO CASTEBLANCO": "OSWALDO CASTELBLANCO"}
CATEGORIAS = [("BMW X5", "BMW X5%", 1), ("Land Rover Sentinel", "%SENTINEL%", 2),
              ("Express Van", "%EXPRESS%VAN%", 3), ("BMW Serie 7", "BMW SERIE 7%", 4)]
PARAMETROS = [
    ("meta_aceros_dia", "50", "Meta diaria de aceros (capacidad por defecto si la semana no tiene una propia)"),
    ("meta_aceros_turno", "20", "Meta de aceros por matricero por turno de 8 h"),
    ("dias_promedio_productividad", "7", "Días con producción que entran al promedio de productividad"),
    ("dias_laborales", "0,1,2,3,4,5", "Días laborales (0 = lunes ... 6 = domingo)"),
    ("meta_dias_fila", "2", "Meta de días de fila de aceros (valor inicial, se ajusta en el tablero)"),
    ("moldes_horas_turno", "8", "Horas por turno para la cola de fabricación de moldes"),
    ("mant_meta_persona_dia", "0", "Meta de mantenimientos finalizados por persona por día (0 = sin meta)"),
    ("seri_capacidad_logos", "0", "Capacidad diaria de logos (0 = se escribe en el tablero)"),
    ("mant_dias_abierto_viejo", "3", "Solo se muestran los mantenimientos abiertos en los últimos N días"),
]


def correr_sql(archivo):
    texto = open(archivo, encoding="utf-8").read()
    bloques = [b.strip() for b in re.split(r"^\s*GO\s*$", texto, flags=re.M | re.I) if b.strip()]
    with db.transaccion() as cur:
        for b in bloques:
            cur.execute(b)
    print(f"  {len(bloques)} bloques de {archivo}")


def insertar_faltantes(cur, tabla, columnas, llave, filas):
    n = 0
    for f in filas:
        datos = dict(zip(columnas, f))
        donde = " AND ".join(f"{c} = ?" for c in llave)
        cur.execute(f"SELECT 1 FROM {tabla} WHERE {donde}", *[datos[c] for c in llave])
        if cur.fetchone():
            continue
        cur.execute(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})", *f)
        n += 1
    print(f"  {tabla}: {n} nuevos")


def sembrar():
    with db.transaccion() as cur:
        insertar_faltantes(cur, "cesar.parametro", ["clave", "valor", "descripcion"], ["clave"], PARAMETROS)
        insertar_faltantes(cur, "cesar.material", ["texto", "material"], ["texto"], list(MATERIALES.items()))
        insertar_faltantes(cur, "cesar.material_orden", ["material", "orden", "color"], ["material"],
                           [(m, i, c) for i, (m, c) in enumerate(ORDEN_MATERIALES, start=1)])
        insertar_faltantes(cur, "cesar.equivalencia", ["material", "pieza", "factor"], ["material", "pieza"],
                           [(m, p, f) for m, d in EQUIVALENCIAS.items() for p, f in d.items()])
        insertar_faltantes(cur, "cesar.operario_regla", ["nombre", "accion", "alias"], ["nombre"],
                           [(n, "excluir", None) for n in OPERARIOS_EXCLUIDOS] +
                           [(n, "vacio", None) for n in OPERARIOS_VACIOS] +
                           [(n, "alias", a) for n, a in ALIAS.items()])
        insertar_faltantes(cur, "cesar.categoria_vehiculo", ["categoria", "patron", "orden"], ["patron"], CATEGORIAS)
        hoy = dt.date.today()
        insertar_faltantes(cur, "cesar.festivo", ["fecha", "nombre"], ["fecha"],
                           [(f, n) for a in range(2024, hoy.year + 4) for f, n in festivos(a).items()])


def migrar_historial_json():
    """Trae la foto diaria que el script viejo guardaba en historial_indicadores.json."""
    ruta = config.RAIZ / "historial_indicadores.json"
    if not ruta.exists():
        return
    hist = json.loads(ruta.read_text(encoding="utf-8"))
    with db.transaccion() as cur:
        for fecha, valores in hist.items():
            for indicador, valor in valores.items():
                cur.execute("SELECT 1 FROM cesar.foto_diaria WHERE fecha = ? AND indicador = ?", fecha, indicador)
                if not cur.fetchone():
                    cur.execute("INSERT INTO cesar.foto_diaria (fecha, indicador, valor, actualizado) VALUES (?, ?, ?, ?)",
                                fecha, indicador, valor, db.ahora())
    print(f"  historial_indicadores.json: {len(hist)} días migrados")


def main():
    print("Esquema:")
    for archivo in sorted((config.RAIZ / "sql").glob("*.sql")):
        correr_sql(archivo)
    print("Configuración inicial:")
    sembrar()
    migrar_historial_json()
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
