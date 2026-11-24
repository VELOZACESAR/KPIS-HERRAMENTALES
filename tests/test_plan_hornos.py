import datetime as dt
import unittest

from tablero import calculo_plan_hornos as ph

H = lambda hh, mm=0, d=24: dt.datetime(2026, 11, d, hh, mm)  # noqa: E731


class SaludDelPlan(unittest.TestCase):
    def test_replaneo_cada_30_min_es_plan_al_dia(self):
        gens = [H(8), H(8, 31), H(9, 2), H(9, 33)]
        sin_plan, caidas = ph.huecos(gens, H(9, 50))
        self.assertEqual((sin_plan, caidas), ([], []))
        self.assertEqual(ph.confiabilidad(sin_plan, H(8), H(9, 50)), 1.0)

    def test_un_replaneo_saltado_desactualiza_pero_no_es_caida(self):
        sin_plan, caidas = ph.huecos([H(8), H(9, 1)], H(9, 10))
        self.assertEqual(sin_plan, [(H(8, 45), H(9, 1))])
        self.assertEqual(caidas, [])

    def test_cinco_horas_sin_plan_es_caida(self):
        sin_plan, caidas = ph.huecos([H(2, 38, 19), H(7, 45, 19)], H(8, 0, 19))
        self.assertEqual(caidas, [{"desde": H(2, 38, 19), "hasta": H(7, 45, 19), "minutos": 307, "abierta": False}])
        self.assertAlmostEqual(ph.minutos_en(sin_plan, H(0, 0, 19), H(23, 0, 19)), 307 - 45)

    def test_caida_en_curso_queda_abierta(self):
        _, caidas = ph.huecos([H(10)], H(11, 30))
        self.assertTrue(caidas[0]["abierta"])
        self.assertIsNone(caidas[0]["hasta"])

    def test_confiabilidad_cuenta_solo_lo_que_cae_en_la_ventana(self):
        intervalos = [(H(5), H(7))]
        self.assertAlmostEqual(ph.confiabilidad(intervalos, H(6), H(10)), 0.75)

    def test_escenarios_de_estudio_no_son_el_plan_vigente(self):
        v = lambda i, ver, hh, mm=0, esc="CUMPLIMIENTO": {"Id": i, "DiaLogico": dt.date(2026, 10, 26), "Version": ver,  # noqa: E731
                                                          "GeneradoEn": H(hh, mm, 26), "Escenario": esc}
        versiones = [v(1, 21, 2), v(2, 22, 2, 1), v(3, 2, 2, 31), v(4, 2, 2, 31, "HIBRIDO"), v(5, 23, 2, 38)]
        self.assertEqual([x["Version"] for x in ph.cadena(versiones)], [21, 22, 23])

    def test_carros_congelados_que_cambian_son_cambio_brusco(self):
        dia = dt.date(2026, 11, 20)
        a = {"Id": 1, "DiaLogico": dia, "Version": 26, "GeneradoEn": H(12, 40, 20), "Escenario": "CUMPLIMIENTO"}
        b = {"Id": 2, "DiaLogico": dia, "Version": 27, "GeneradoEn": H(13, 10, 20), "Escenario": "CUMPLIMIENTO"}
        congelados = {1: {"h1-1400": (H(14, 0, 20), '{"A": "1"}'), "h1-1500": (H(15, 0, 20), '{"A": "2"}'),
                          "h1-1200": (H(12, 0, 20), '{"A": "9"}')},
                      2: {"h1-1400": (H(14, 0, 20), '{"A": "1"}'), "h1-1500": (H(15, 0, 20), '{"A": "3"}')}}
        cambios = ph.cambios_bruscos([a, b], congelados)
        self.assertEqual(cambios[0]["congelados_movidos"], 1, "el carro de las 12:00 ya pasó: no cuenta")
        self.assertIn("1 de 2 carros congelados", cambios[0]["detalle"])
        self.assertEqual(ph.cambios_bruscos([a, {**b, "Id": 1}], congelados), [])


class Cumplimiento(unittest.TestCase):
    def test_turno_oficial_suma_los_hornos_como_smartbending(self):
        pieza = lambda molde, res: {"molde": molde, "resultado": res}  # noqa: E731
        h1 = {"turno": {"inicio": "2026-11-24T05:00:00", "fin": "2026-11-24T11:00:00"}, "plan": {"plan_version": 34}, "filas": [
            {"resultado": "IDENTICO", "piezas": [pieza("M 1715 007 001 Molde Anillo", "CUMPLIDO")]},
            {"resultado": "DESVIADO", "categoria": "MOLDE_NO_DISPONIBLE", "comentario": "molde rotando", "horno": "h1",
             "planeado": {"hora": "2026-11-24T07:00:00", "piezas": [{"molde": "M 1244 00 01 Molde de Anillo"}]},
             "piezas": [pieza("M 1244 00 01 Molde de Anillo", "DESVIACION_COMPOSICION")]},
            {"resultado": "ADICIONAL"}]}
        h2 = {"turno": h1["turno"], "plan": h1["plan"], "filas": [{"resultado": "NO_EJECUTADO", "piezas": [pieza("R2600 Molde Lleno", "NO_CUBIERTA")]}]}
        t = ph.turno_oficial([h1, h2])
        self.assertEqual((t["planeados"], t["cargados"], t["identicos"], t["adicionales"]), (3, 3, 1, 1))
        self.assertEqual(len(t["moldes_plan"]), 3)
        self.assertEqual(t["moldes_ok"], {"M 1715 007 001 MOLDE ANILLO"})
        self.assertEqual(t["sin_molde"][0]["moldes"], ["M 1244 00 01 Molde de Anillo"])
        self.assertEqual(t["sin_molde"][0]["horno"], "H1")

    def test_turno_en_vivo_cuenta_lo_que_va_a_esta_hora(self):
        posiciones = [{"hora": H(11), "horno": "H1", "ordenes": ["1", "2"]}, {"hora": H(12), "horno": "H2", "ordenes": ["3"]},
                      {"hora": H(15), "horno": "H1", "ordenes": ["4"]}, {"hora": H(17), "horno": "H1", "ordenes": ["5"]}]
        cargues = [{"orden": "1", "cargue": "C1", "hora": H(11, 10), "razon": "Generado por operario"},
                   {"orden": "2", "cargue": "C1", "hora": H(11, 10), "razon": "Generado por operario"},
                   {"orden": "9", "cargue": "C2", "hora": H(11, 40), "razon": "Web SmartBending"},
                   {"orden": "9", "cargue": "C3", "hora": H(11, 50), "razon": "Correccion del cargue C2 - intento 1/3"}]
        molde_de = {"1": {"molde": "M 1 A"}, "2": {"molde": "M 1 A"}, "3": {"molde": "M 2"}, "4": {"molde": "M 3"}}
        t = ph.turno_en_vivo(posiciones, H(11), H(16), H(12, 30), cargues, molde_de)
        self.assertEqual((t["planeados"], t["a_la_hora"], t["cargados"]), (3, 2, 2), "la corrección no es otro carro")
        self.assertTrue(t["en_curso"])
        self.assertEqual((len(t["moldes_plan"]), len(t["moldes_ok"])), (2, 1))
        self.assertEqual([p["orden"] for p in t["piezas"] if not p["cargada"]], ["3", "4"])

    def test_ventanas_de_turno_salen_del_plan(self):
        posiciones = [{"turno": "T1_OP", "hora": H(21, 0, 23)}, {"turno": "T2_OP", "hora": H(5)}, {"turno": "T3_OP", "hora": H(11)},
                      {"turno": "T3_OP", "hora": H(12)}, {"turno": "T1_OP", "hora": H(23)}, {"turno": None, "hora": H(22)}]
        self.assertEqual(ph.ventanas_turnos(posiciones, H(21, 0, 23)),
                         [("T1_OP", H(21, 0, 23), H(5)), ("T2_OP", H(5), H(11)), ("T3_OP", H(11), H(21))])

    def test_estado_del_dia(self):
        self.assertEqual(ph.estado_dia(60, 72), "sobre")
        self.assertEqual(ph.estado_dia(60, 58), "al_dia")
        self.assertEqual(ph.estado_dia(60, 50), "atras")
        self.assertEqual(ph.estado_dia(0, 5), "sin_plan")


if __name__ == "__main__":
    unittest.main()
