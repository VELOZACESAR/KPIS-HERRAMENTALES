-- Copia de HRRM.VW_GRAFICA de Herramienta Logos: Fecha | CARGA | CAPACIDAD | FALTANTES PCP.
-- Alimenta la gráfica de producción y capacidad diaria de Vitros logos.
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
