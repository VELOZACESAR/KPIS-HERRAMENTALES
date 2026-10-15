"""Festivos de Colombia (Ley 51 de 1983 / Ley Emiliani): fijos, trasladados al lunes y los que dependen de la Pascua."""
import datetime as dt


def pascua(anio):
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(anio, mes, dia)


def _al_lunes(f):
    return f + dt.timedelta(days=(7 - f.weekday()) % 7)


def festivos(anio):
    p = pascua(anio)
    fijos = [((1, 1), "Año Nuevo"), ((5, 1), "Día del Trabajo"), ((7, 20), "Independencia"),
             ((8, 7), "Batalla de Boyacá"), ((12, 8), "Inmaculada Concepción"), ((12, 25), "Navidad")]
    trasladables = [((1, 6), "Reyes Magos"), ((3, 19), "San José"), ((6, 29), "San Pedro y San Pablo"),
                    ((8, 15), "Asunción de la Virgen"), ((10, 12), "Día de la Raza"), ((11, 1), "Todos los Santos"),
                    ((11, 11), "Independencia de Cartagena")]
    salida = {dt.date(anio, m, d): n for (m, d), n in fijos}
    salida.update({_al_lunes(dt.date(anio, m, d)): n for (m, d), n in trasladables})
    salida[p - dt.timedelta(days=3)] = "Jueves Santo"
    salida[p - dt.timedelta(days=2)] = "Viernes Santo"
    salida[_al_lunes(p + dt.timedelta(days=39))] = "Ascensión del Señor"
    salida[_al_lunes(p + dt.timedelta(days=60))] = "Corpus Christi"
    salida[_al_lunes(p + dt.timedelta(days=68))] = "Sagrado Corazón"
    return dict(sorted(salida.items()))
