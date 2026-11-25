"""Lo que SmartBending pide mantener (regla de "Hacer primero") y cuánto de eso se atendió."""
import datetime as dt
import unittest

from tablero.calculo_mantenimiento import hacer_primero, sumar_necesidad


def _rep(uso=False, matriceria=False):
    return {"uso": uso, "matriceria": matriceria}


class HacerPrimero(unittest.TestCase):
    def test_disponibles_cubren_el_plan_no_pide_nada(self):
        reps = {"1": _rep(), "2": _rep(), "3": _rep()}
        r = hacer_primero(2, reps, {"3": 10.0})
        self.assertEqual((r["disponibles"], r["faltan"], r["hacer"]), (2, 0, []))

    def test_pide_las_de_mas_puntaje_hasta_cubrir_lo_que_falta(self):
        reps = {"1": _rep(), "2": _rep(), "3": _rep(), "4": _rep()}
        r = hacer_primero(3, reps, {"2": 10.0, "3": 20.0, "4": 12.5})
        self.assertEqual((r["disponibles"], r["faltan"]), (1, 2))
        self.assertEqual(r["hacer"], ["3", "4"])

    def test_en_uso_o_en_matriceria_no_se_puede_pedir(self):
        reps = {"1": _rep(uso=True), "2": _rep(matriceria=True), "3": _rep()}
        r = hacer_primero(5, reps, {"1": 10.0, "2": 10.0, "3": 10.0})
        self.assertEqual((r["disponibles"], r["faltan"], r["hacer"]), (0, 5, ["3"]))


class SumarNecesidad(unittest.TestCase):
    def test_atendidas_son_las_pedidas_que_se_finalizaron_ese_dia(self):
        hoy = dt.date(2026, 11, 25)
        M = {"diaria": [{"fecha": "2026-11-24"}, {"fecha": "2026-11-25"}], "semanal": [], "mensual": [],
             "registros": {"moldes": ["M 1244", "G 0100"],
                           "filas": [["2026-11-25", 0, 0, 0, 0, 0, "2026-11-25", "T2", "000", "001", "3"],
                                     ["2026-11-25", 0, 0, 0, 0, 0, "2026-11-25", "T2", "000", "001", "9"],
                                     ["2026-11-25", 0, 0, 0, 1, 0, "2026-11-25", "T2", "000", "000", "1"]]}}
        P = {"necesidad_historia": [["2026-11-25", "1244", "000", "001", "3", "BMW X5"],
                                    ["2026-11-25", "1244", "000", "001", "4", "BMW X5"]],
             "necesidad_vivo": [{"cod": "1379", "version": "000", "pieza": "001", "rep": "3", "categoria": "Retrofit"}]}
        sumar_necesidad(M, P, hoy)
        ayer, dia = M["diaria"]
        self.assertIsNone(ayer["nec"])
        self.assertEqual(dia["nec"], {"BMW X5": 2, "Retrofit": 1})
        self.assertEqual(dia["nec_ok"], {"BMW X5": 1})


if __name__ == "__main__":
    unittest.main()
