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
