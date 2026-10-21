-- Herramienta Logos Actual.xlsx, hoja "Gráfica": tabla diaria Fecha | CARGA | CAPACIDAD | FALTANTES PCP.
-- Alimenta la gráfica de Vitros logos (lo hecho por día y la capacidad del día).
IF OBJECT_ID('cesar.seri_logos_grafica') IS NULL
CREATE TABLE cesar.seri_logos_grafica (
    fila        INT    NOT NULL PRIMARY KEY,
    id_cargue   INT    NOT NULL,
    fecha       DATE   NULL,
    carga       FLOAT  NULL,
    capacidad   FLOAT  NULL,
    faltantes   FLOAT  NULL
);
GO
