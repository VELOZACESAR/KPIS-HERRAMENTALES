import datetime as dt
import unittest

from tablero.excel import fecha, numero, texto, ubicar_columnas
from tablero.festivos import festivos
from tablero.reglas import Reglas


class Festivos(unittest.TestCase):
    def test_2026_oficial(self):
        esperados = {(1, 1), (1, 12), (3, 23), (4, 2), (4, 3), (5, 1), (5, 18), (6, 8), (6, 15), (6, 29),
                     (7, 20), (8, 7), (8, 17), (10, 12), (11, 2), (11, 16), (12, 8), (12, 25)}
        self.assertEqual({(f.month, f.day) for f in festivos(2026)}, esperados)

    def test_2027_cae_en_lunes_lo_trasladable(self):
        f = festivos(2027)
        self.assertIn(dt.date(2027, 1, 11), f)
        self.assertIn(dt.date(2027, 3, 25), f)
        self.assertIn(dt.date(2027, 3, 26), f)


class Excel(unittest.TestCase):
    def test_fechas(self):
        self.assertEqual(fecha(dt.datetime(2026, 4, 19, 8)), dt.date(2026, 4, 19))
        self.assertEqual(fecha(46131), dt.date(2026, 4, 19))
        self.assertEqual(fecha("19/04/2026"), dt.date(2026, 4, 19))
        self.assertIsNone(fecha("A-3"))
        self.assertIsNone(fecha("31/02/2026"))

    def test_texto_y_numero(self):
        self.assertEqual(texto(11285973.0), "11285973")
        self.assertIsNone(texto("#N/A"))
        self.assertEqual(numero(" $ 389.232,00 "), 389232.0)

    def test_columnas_por_nombre_no_por_posicion(self):
        viejo = ["Orden fabricacion", "Zfer", "Zhal", "Acero", "Vehiculo", "Plano", "Fecha"]
        nuevo = ["Orden fabricacion", "20000", "Zfer", "Zhal", "Acero", "Vehiculo", "Plano", "Fecha"]
        mapa = {"orden": ["Orden fabricacion"], "fecha": ["Fecha"]}
        self.assertEqual(ubicar_columnas(viejo, mapa)["fecha"], 6)
        self.assertEqual(ubicar_columnas(nuevo, mapa)["fecha"], 7)
        with self.assertRaises(ValueError):
            ubicar_columnas(["Orden"], mapa, obligatorias=["fecha"])


class Operarios(unittest.TestCase):
    def setUp(self):
        self.r = Reglas(parametros={}, materiales={"BOHLER": "Böhler"}, orden_materiales=[], colores_materiales={},
                        equivalencias={"Gurkha": {1: 5}}, excluidos={"CANCELADO"}, vacios={"-", "N/A"},
                        alias={"OSWALDO CASTEBLANCO": "OSWALDO CASTELBLANCO"}, festivos={}, dias_laborales={0, 1, 2, 3, 4, 5})

    def test_operario(self):
        self.assertEqual(self.r.operario(" oswaldo  casteblanco "), ("ok", "Oswaldo Castelblanco"))
        self.assertEqual(self.r.operario("Cancelado"), ("excluido", None))
        self.assertEqual(self.r.operario("-"), ("vacio", None))

    def test_material_y_factor(self):
        self.assertEqual(self.r.material(" bohler "), "Böhler")
        self.assertEqual(self.r.material("ACERO RARO"), "Otro")
        self.assertEqual(self.r.factor("Gurkha", "1"), 5)
        self.assertEqual(self.r.factor("Gurkha", "SRF"), 1)


if __name__ == "__main__":
    unittest.main()


class PedidosMantenimiento(unittest.TestCase):
    """Alertas nuevas por día y finalizados que atendieron una alerta, con la BD simulada."""

    def _calcular(self, alertas, dias_foto, fin):
        from unittest import mock
        from tablero import calculo_mantenimiento as cm

        def consultar(sql, *params):
            if "cesar.mant_alerta" in sql:
                return [{"fecha": f, "cod_her": c, "version": v, "pieza": p, "repeticion": r, "desde": t}
                        for f, c, v, p, r, t in alertas]
            if "foto_diaria" in sql:
                return [{"fecha": d} for d in dias_foto]
            return [{"cod_molde": "1244", "categoria": "BMW X5"}]
        with mock.patch.object(cm.db, "consultar", side_effect=consultar):
            return cm._pedidos_atendidos(fin, dt.date(2026, 10, 1), ["BMW X5", "Retrofit"])

    def test_nuevas_y_atendidas(self):
        d1, d2 = dt.date(2026, 10, 26), dt.date(2026, 10, 27)
        h = lambda d, hora: dt.datetime.combine(d, dt.time(hora))
        alertas = [(d1, "1244", "000", "000", "1", h(d1, 8)),          # venía de ayer
                   (d2, "1244", "000", "000", "1", h(d2, 0)),
                   (d2, "0606", "170", "000", "4", h(d2, 9))]           # nueva hoy
        fin = [{"tipo": "M", "cod_her": "1244", "version": "00", "pieza": "0", "repeticion": "01",
                "fin": h(d2, 7), "inicio": h(d2, 6), "categoria": "BMW X5"},    # atendió la de ayer
               {"tipo": "M", "cod_her": "606", "version": "170", "pieza": "000", "repeticion": "4",
                "fin": h(d2, 8), "inicio": h(d2, 7), "categoria": "Retrofit"},  # antes de la alerta: no cuenta
               {"tipo": "M", "cod_her": "1500", "version": "000", "pieza": "000", "repeticion": "1",
                "fin": h(d2, 10), "inicio": h(d2, 9), "categoria": "Retrofit"}]  # sin alerta
        pedidos, atendidos = self._calcular(alertas, [d1, d2], fin)
        self.assertNotIn(d1, pedidos)                      # primer día de fotos: sin dato
        self.assertEqual(pedidos[d2], {"Retrofit": 1})
        self.assertEqual(atendidos[d2], {"BMW X5": 1})

    def test_dia_sin_foto_queda_sin_dato(self):
        d1, d3 = dt.date(2026, 10, 26), dt.date(2026, 10, 28)
        pedidos, atendidos = self._calcular([], [d1, d3], [])
        self.assertEqual(pedidos, {})
        self.assertEqual(atendidos, {})
