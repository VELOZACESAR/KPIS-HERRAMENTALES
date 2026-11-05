import datetime as dt
import unittest
from unittest import mock

from tablero import config, fuentes  # fuentes primero: arma LECTORES y evita el ciclo de importación
from tablero import calculo_serigrafia as cs
from tablero import fuentes_serigrafia as fs


class LogosDesdeLaApp(unittest.TestCase):
    """Los logos ya no salen del Excel: se leen de las vistas HRRM.VW_* que publica la app Herramienta Logos."""

    def setUp(self):
        fs._cache_logos.update(marca=None, tablas=None, extra=None)

    def _consultar(self, sql, *params):
        if "VW_HERRAMIENTA_LOGOS" in sql and "MAX(ACTUALIZADO)" not in sql:
            return [{"PedidoGenesis": "P-118", "Orden": 11291277, "TRAZABILIDAD": "CO-1001", "Logo": "CO-1001",
                     "TIPO_DE_LOGO": "INTERNO NEGRO", "STATUS_LOGO": "DISPONIBLE", "ZFER": "700179259",
                     "Vehiculo": "Sentinel", "Puestodetrabajo": "Planeacion", "FechaLiberacionTOC": dt.date(2026, 12, 19),
                     "NOMBRE_ARCHIVO": None, "PRIORIDAD": "SABADO", "ESTADO": None, "RESPONSABLE": None,
                     "PLAN_DE_CORTE": "Sabado 2-4421", "Cliente": "CLIENTE", "SITUACION": "Listo para cargar"}]
        if "MAX(ACTUALIZADO)" in sql:
            return [{"ultimo": dt.datetime(2026, 10, 30, 8, 36, 15)}]
        if "VW_GRAFICA" in sql:
            return [{"Fecha": dt.date(2026, 10, 30), "CARGA": 44, "CAPACIDAD": 50, "faltantes": 292}]
        if "VW_HISTORICO" in sql:
            return [{"FechaGrafica": dt.date(2026, 10, 30), "ORDEN": 11291277, "RESPONSABLE": "CAMILO"}]
        return []

    def test_mapea_las_vistas_de_la_app(self):
        with mock.patch.object(fs.db, "consultar", side_effect=self._consultar):
            tablas, extra = fs.leer_logos()
        cols, filas = tablas["cesar.seri_logos"]
        self.assertEqual(len(filas), 1)
        fila = dict(zip(cols, filas[0]))
        self.assertEqual(fila["orden"], "11291277")
        self.assertEqual(fila["inv_status"], "DISPONIBLE")
        self.assertEqual(fila["fecha_lib_toc"], dt.date(2026, 12, 19))
        self.assertEqual(fila["plan_corte"], "Sabado 2-4421")
        self.assertEqual(fila["situacion"], "Listo para cargar")
        self.assertIsNone(fila["fullkit"])
        self.assertEqual(tablas["cesar.seri_logos_grafica"][1][0][1:], (dt.date(2026, 10, 30), 44.0, 50.0, 292.0))
        self.assertEqual(tablas["cesar.seri_logos_historico"][1][0][1:], (dt.date(2026, 10, 30), "11291277", "CAMILO"))
        self.assertEqual(len(extra["huella"]), 64)
        self.assertEqual(extra["origen"], "Herramienta Logos (app)")
        self.assertEqual(extra["modificado"], dt.datetime(2026, 10, 30, 8, 36, 15))

    def test_la_huella_cambia_solo_si_cambian_los_datos(self):
        with mock.patch.object(fs.db, "consultar", side_effect=self._consultar):
            h1 = fs.leer_logos()[1]["huella"]
            h2 = fs.leer_logos()[1]["huella"]
        self.assertEqual(h1, h2)

    def test_no_relee_si_la_app_no_publico(self):
        llamadas = []

        def consultar(sql, *params):
            llamadas.append(sql)
            return self._consultar(sql, *params)

        with mock.patch.object(fs.db, "consultar", side_effect=consultar):
            fs.leer_logos()
            n = len(llamadas)
            fs.leer_logos()
        self.assertEqual(len(llamadas), n + 1)
        self.assertIn("MAX(ACTUALIZADO)", llamadas[-1])

    def test_ya_no_es_una_fuente_de_archivo(self):
        self.assertNotIn("logos", config.FUENTES)
        self.assertIn("logos", config.FUENTES_BD)
        self.assertIn("logos", fuentes.LECTORES)


class HechosLogosDesdeLaApp(unittest.TestCase):
    def test_lee_la_tabla_copiada_de_la_app(self):
        respuestas = {
            "OBJECT_ID('cesar.seri_logos_historico')": [{"n": 1}],
            "MAX(id_cargue)": [{"n": 7}],
            "FROM cesar.seri_logos_historico": [{"fecha": dt.date(2026, 10, 30), "orden": "11291277",
                                                 "responsable": "CAMILO"}],
        }

        def consultar(sql, *params):
            for clave, valor in respuestas.items():
                if clave in sql:
                    return valor
            return []

        cs._cache_hechos_logos.update(cargue=None, hoy=None, datos=[])
        with mock.patch.object(cs.db, "consultar", side_effect=consultar):
            hechos = cs._hechos_logos(dt.date(2026, 10, 30))
        self.assertEqual(hechos, [(dt.date(2026, 10, 30), "Camilo", "11291277")])


class CapacidadLogos(unittest.TestCase):
    def test_prevalece_capacidad_app_y_usa_indicadores_como_respaldo(self):
        app = {
            "2026-10-30": {"capacidad": 50},
            "2026-10-29": {"capacidad": None},
        }

        def consultar(sql, *params):
            if "OBJECT_ID('cesar.seri_ind_capacidad')" in sql:
                return [{"n": 1}]
            if "SELECT fecha, cap_logos" in sql:
                return [
                    {"fecha": dt.date(2026, 10, 30), "cap_logos": 64},
                    {"fecha": dt.date(2026, 10, 29), "cap_logos": 64},
                ]
            return []

        with mock.patch.object(cs, "_grafica_logos", return_value=app), \
                mock.patch.object(cs.db, "consultar", side_effect=consultar):
            capacidades = cs._capacidad_logos(dt.date(2026, 10, 30))

        self.assertEqual(capacidades[dt.date(2026, 10, 30)], 50)
        self.assertEqual(capacidades[dt.date(2026, 10, 29)], 64)


class SituacionLogos(unittest.TestCase):
    def test_solo_cuenta_ordenes_listas_para_cargar(self):
        filas = [
            {"inv_status": "DISPONIBLE", "nombre_archivo": None, "situacion": "Listo para cargar"},
            {"inv_status": "DISPONIBLE", "nombre_archivo": None, "situacion": "CARGADO"},
            {"inv_status": "DISPONIBLE", "nombre_archivo": None, "situacion": "SIN_VITRO_SAP"},
            {"inv_status": "DISPONIBLE", "nombre_archivo": "archivo.pdf", "situacion": "Listo para cargar"},
        ]
        self.assertEqual(cs._logos_listos(filas), filas[:1])

    def test_conserva_asignado_separado_de_sin_responsable(self):
        self.assertEqual(cs._responsable_historico("ASIGNADO"), "Asignado")
        self.assertEqual(cs._responsable_historico(None), "Sin responsable")

    def test_logos_listos_coinciden_con_conteo_de_situacion_de_la_app(self):
        app_rows = [
            {"StatusLogo": "DISPONIBLE", "NombreArchivo": None, "Situacion": "Listo para cargar", "PlanCorte": "Lunes"},
            {"StatusLogo": "DISPONIBLE", "NombreArchivo": None, "Situacion": "Cargado", "PlanCorte": "Lunes"},
            {"StatusLogo": "DISPONIBLE", "NombreArchivo": None, "Situacion": "Sin vitro en SAP", "PlanCorte": None},
        ]
        filas = [{"inv_status": r["StatusLogo"], "nombre_archivo": r["NombreArchivo"], "situacion": r["Situacion"],
                  "plan_corte": r["PlanCorte"]} for r in app_rows]
        listos = cs._logos_listos(filas)
        p1 = sum(bool(r["plan_corte"]) for r in listos)
        p2 = len(listos) - p1
        self.assertEqual((p1, p2, len(listos)), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
