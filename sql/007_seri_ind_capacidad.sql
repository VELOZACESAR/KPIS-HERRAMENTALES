-- Indicadores diarios.xlsx: tabla diaria Fecha | Capacidad Vitros Logo | Capacidad Vitros Estandar |
-- Capacidad Vitros Pasta de Plata | Retenidas Vitros Logos | Retenidas Vitros Estandar | Retenidas Vitros Pasta de Plata.
-- Se busca en cualquier hoja del libro (la que tenga Fecha y una columna de capacidad de pasta de plata).
IF OBJECT_ID('cesar.seri_ind_capacidad') IS NULL
CREATE TABLE cesar.seri_ind_capacidad (
    fila          INT    NOT NULL,
    id_cargue     INT    NOT NULL,
    hoja          NVARCHAR(100) NULL,
    fecha         DATE   NULL,
    cap_logos     FLOAT  NULL,
    cap_estandar  FLOAT  NULL,
    cap_pp        FLOAT  NULL,
    ret_logos     FLOAT  NULL,
    ret_estandar  FLOAT  NULL,
    ret_pp        FLOAT  NULL
);
GO
